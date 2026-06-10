"""Orchestrator — 多 Agent 协调，对外暴露 chat_stream。"""

import json
from collections.abc import Generator

from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.market_agent import MarketAgent
from wealthpilot.services.agents.portfolio_agent import PortfolioAgent
from wealthpilot.services.agents.risk_agent import RiskAgent
from wealthpilot.services.agents.router_agent import RouterAgent
from wealthpilot.services.ai_client import create_ai_client
from wealthpilot.settings import get_settings


AGENT_LABELS = {
    "market": "📊 市场分析",
    "portfolio": "💼 持仓分析",
    "risk": "🛡️ 风险评估",
}


def chat_stream(
    message: str,
    history: list[dict[str, str]],
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
    conversation_id: str | None = None,
    db_session: Session | None = None,
) -> Generator[str, None, None]:
    """多 Agent 协调入口。Router 分流 → 专业 Agent 执行 → SSE 输出。"""
    settings = get_settings()
    try:
        client = create_ai_client(settings)
    except ValueError as e:
        yield _sse({"type": "error", "content": str(e)})
        return

    model = settings.active_model

    # 0. 如果前端没传 history 但有 conversation_id，从 DB 加载
    if not history and conversation_id and db_session:
        history = _load_history(db_session, conversation_id)

    # 1. Router 分类
    router = RouterAgent(client, model)
    agent_name, reason = router.route(message)

    yield _sse({"type": "agent_route", "agent": agent_name, "label": AGENT_LABELS.get(agent_name, agent_name), "reason": reason})

    # 2. 构建对应 Agent
    if agent_name == "market":
        agent = MarketAgent(client, model)
    elif agent_name == "risk":
        agent = RiskAgent(client, model, holdings, nav_data, nav_history)
    else:
        agent = PortfolioAgent(client, model, holdings, nav_data, nav_history)

    # 3. 构建消息列表
    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    # 4. 执行 Agent
    try:
        yield from agent.run(messages)
        final_text = agent.final_text
    except Exception as e:
        yield _sse({"type": "error", "content": f"Agent 执行异常: {e}"})
        return

    # 5. 持久化对话记录
    if conversation_id and db_session:
        _save_message(db_session, conversation_id, "user", message)
        _save_message(
            db_session, conversation_id, "assistant", final_text,
            metadata={"agent": agent_name, "reason": reason},
        )

    # 6. 生成 follow-ups
    follow_ups = _generate_follow_ups(final_text, message, agent_name, holdings)
    yield _sse({"type": "done", "content": final_text, "follow_ups": follow_ups})


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
    response: str, question: str, agent_name: str, holdings: list[PortfolioHolding]
) -> list[str]:
    """基于 agent 类型和回答内容生成追问建议。"""
    follow_ups = []

    if agent_name == "market":
        if "基金" in response:
            follow_ups.append("这只基金近3个月表现怎么样？")
        if "新闻" in response or "要闻" in response:
            follow_ups.append("这些新闻对我的持仓有什么影响？")
        if not follow_ups:
            follow_ups.append("帮我查看最新市场动态")

    elif agent_name == "portfolio":
        if "收益" in response:
            follow_ups.append("哪只基金贡献最大？")
        if "健康" in response or "评分" in response:
            follow_ups.append("如何改善我的组合健康度？")
        if not follow_ups:
            follow_ups.append("帮我分析持仓收益归因")

    elif agent_name == "risk":
        if "回撤" in response:
            follow_ups.append("回撤较大的基金需要止损吗？")
        if "相关性" in response:
            follow_ups.append("如何降低持仓相关性？")
        if not follow_ups:
            follow_ups.append("帮我做一个全面的风险评估")

    if len(follow_ups) < 2:
        defaults = {
            "market": ["本周市场有什么需要关注的？", "推荐关注哪些板块机会？"],
            "portfolio": ["帮我分析当前持仓的风险收益比", "给我一些调仓建议"],
            "risk": ["分析我的持仓回撤风险", "哪些持仓需要关注？"],
        }
        follow_ups.extend(defaults.get(agent_name, []))

    return follow_ups[:3]


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
