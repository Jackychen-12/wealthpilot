"""Orchestrator — Plan → 并行 Execute → Synthesize。

流程：
    message
       │
       ▼  PlannerAgent 产出 TaskGraph + success_criteria
    ┌──┴──┬──────┬──────┐
    ▼     ▼      ▼      ▼   同一波内 asyncio.gather 并发
  market portfolio risk ...
    └──┬──┴──────┴──────┘
       ▼  SynthesizerAgent 整合 + 冲突消解 + 约束核对
     最终回答（附数值溯源指标）

单任务的简单问题走快路径：该 Agent 直接流式输出，不经过 Synthesizer，避免多一跳延迟。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.market_agent import MarketAgent
from wealthpilot.services.agents.planner_agent import Plan, PlannerAgent, Task
from wealthpilot.services.agents.portfolio_agent import PortfolioAgent
from wealthpilot.services.agents.risk_agent import RiskAgent
from wealthpilot.services.agents.synthesizer_agent import (
    SynthesizerAgent,
    check_numeric_grounding,
)
from wealthpilot.services.ai_client import create_ai_client
from wealthpilot.settings import get_settings

AGENT_LABELS = {
    "market": "📊 市场分析",
    "portfolio": "💼 持仓分析",
    "risk": "🛡️ 风险评估",
}


async def chat_stream(
    message: str,
    history: list[dict[str, str]],
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
    conversation_id: str | None = None,
    db_session: Session | None = None,
    profile: InvestorProfile | None = None,
) -> AsyncGenerator[str, None]:
    """多 Agent 协调入口，产出 SSE 文本流。"""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def pipeline() -> None:
        try:
            await _run_pipeline(
                message, history, holdings, nav_data, nav_history,
                conversation_id, db_session, profile, emit,
            )
        except Exception as e:  # noqa: BLE001
            await emit({"type": "error", "content": f"Agent 执行异常: {e}"})
        finally:
            await queue.put(None)

    task = asyncio.create_task(pipeline())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _run_pipeline(
    message, history, holdings, nav_data, nav_history,
    conversation_id, db_session, profile, emit,
) -> None:
    settings = get_settings()
    try:
        client = create_ai_client(settings)
    except ValueError as e:
        await emit({"type": "error", "content": str(e)})
        return

    model = settings.active_model

    if not history and conversation_id and db_session:
        history = _load_history(db_session, conversation_id)

    base_messages = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]

    # ── 1. Plan ──────────────────────────────────────────────
    planner = PlannerAgent(client, model, profile)
    plan: Plan = await asyncio.to_thread(planner.plan, message)

    await emit({
        "type": "plan",
        "intent": plan.intent,
        "source": plan.source,
        "tasks": [
            {"id": t.id, "agent": t.agent, "label": AGENT_LABELS.get(t.agent, t.agent), "goal": t.goal}
            for t in plan.tasks
        ],
        "success_criteria": plan.success_criteria,
    })

    # 兼容旧前端：仍然发一条 agent_route，指向首个任务
    first = plan.tasks[0]
    await emit({
        "type": "agent_route",
        "agent": first.agent,
        "label": AGENT_LABELS.get(first.agent, first.agent),
        "reason": first.goal or plan.intent,
    })

    def make_agent(task: Task):
        kwargs = dict(client=client, model=model, profile=profile)
        if task.agent == "market":
            return MarketAgent(**kwargs)
        if task.agent == "risk":
            return RiskAgent(holdings=holdings, nav_data=nav_data, nav_history=nav_history, **kwargs)
        return PortfolioAgent(holdings=holdings, nav_data=nav_data, nav_history=nav_history, **kwargs)

    # ── 2. 单任务快路径：直接流式输出，不经 Synthesizer ────────
    if plan.is_single:
        agent = make_agent(first)
        messages = [*base_messages, {"role": "user", "content": message}]
        result = await agent.run(messages, emit, goal=first.goal, stream_text=True)
        final_text = result.text
        grounding = check_numeric_grounding(final_text, [result])
        await _finish(emit, final_text, grounding, plan, message, holdings,
                      conversation_id, db_session, [first.agent])
        return

    # ── 3. 多任务：按波并发执行 ───────────────────────────────
    results: list[AgentResult] = []
    semaphore = asyncio.Semaphore(settings.agent_max_parallel)

    async def run_task(task: Task) -> AgentResult:
        async with semaphore:
            await emit({
                "type": "task_start",
                "id": task.id,
                "agent": task.agent,
                "label": AGENT_LABELS.get(task.agent, task.agent),
                "goal": task.goal,
            })
            agent = make_agent(task)
            prior = _prior_context(results)
            prompt = f"{prior}你的子任务：{task.goal or message}\n\n用户原始问题：{message}"
            messages = [*base_messages, {"role": "user", "content": prompt}]
            res = await agent.run(messages, emit, goal=task.goal, stream_text=False)
            await emit({
                "type": "task_done",
                "id": task.id,
                "agent": task.agent,
                "tools": res.tool_names,
                "summary": res.text.strip()[:180],
            })
            return res

    for wave in plan.waves():
        wave_results = await asyncio.gather(*[run_task(t) for t in wave])
        results.extend(wave_results)

    # ── 4. Synthesize ────────────────────────────────────────
    await emit({"type": "synthesizing", "agents": [r.agent for r in results]})
    synthesizer = SynthesizerAgent(client, model, profile)
    final_text = await synthesizer.run(message, results, plan.success_criteria, emit)

    grounding = check_numeric_grounding(final_text, results)
    await _finish(emit, final_text, grounding, plan, message, holdings,
                  conversation_id, db_session, [r.agent for r in results])


async def _finish(
    emit, final_text, grounding, plan, message, holdings,
    conversation_id, db_session, agents,
) -> None:
    if grounding["ungrounded"]:
        # 不拦截输出，但把问题暴露出来 —— 这是可以进 CI 的可观测指标
        await emit({
            "type": "grounding_warning",
            "rate": round(grounding["rate"], 3),
            "ungrounded": grounding["ungrounded"][:10],
        })

    if conversation_id and db_session:
        _save_message(db_session, conversation_id, "user", message)
        _save_message(
            db_session, conversation_id, "assistant", final_text,
            metadata={
                "intent": plan.intent,
                "plan_source": plan.source,
                "agents": agents,
                "grounding_rate": round(grounding["rate"], 3),
            },
        )

    await emit({
        "type": "done",
        "content": final_text,
        "follow_ups": _generate_follow_ups(final_text, message, agents, holdings),
        "meta": {
            "intent": plan.intent,
            "agents": agents,
            "grounding_rate": round(grounding["rate"], 3),
        },
    })


def _prior_context(results: list[AgentResult]) -> str:
    """把前序波次的结论传给依赖它们的任务。"""
    if not results:
        return ""
    lines = ["已有的前序分析结果（供参考，不要重复查询）："]
    for r in results:
        if r.text.strip():
            lines.append(f"- [{r.agent}] {r.text.strip()[:400]}")
    return "\n".join(lines) + "\n\n"


def _load_history(db_session: Session, conversation_id: str) -> list[dict[str, str]]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    rows = db_session.exec(stmt).all()
    return [{"role": r.role, "content": r.content} for r in rows]


def _save_message(
    db_session: Session,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> None:
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else "",
    )
    db_session.add(msg)
    db_session.commit()


def _generate_follow_ups(
    response: str, question: str, agents: list[str], holdings: list[PortfolioHolding]
) -> list[str]:
    """生成追问建议 —— 指向"还缺哪个证据"，而不是诱导下一个操作类问题。"""
    follow_ups: list[str] = []

    if "回撤" in response:
        follow_ups.append("这个回撤数据用的是多长的样本区间？")
    if "相关性" in response:
        follow_ups.append("相关性是按净值算的还是按持仓算的？")
    if "预期" in response or "可能" in response or "或将" in response:
        follow_ups.append("这个判断依赖什么前提？哪个数据会推翻它？")
    if "portfolio" in agents and "归因" in response:
        follow_ups.append("哪只基金对这个结果影响最大？")
    if "market" in agents:
        follow_ups.append("这些信息对我的持仓有什么影响？")

    defaults = [
        "这条结论里哪些是已发生的事实，哪些是推断？",
        "还缺哪个数据才能把这个判断做实？",
        "帮我看一下这个结论的反面证据",
    ]
    for d in defaults:
        if len(follow_ups) >= 3:
            break
        if d not in follow_ups:
            follow_ups.append(d)

    return follow_ups[:3]


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
