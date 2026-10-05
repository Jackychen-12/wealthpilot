"""编排全链路测试 —— 用脚本化的假模型跑通 Plan → 工具 → Critic → 回答。

不打真实模型；假 client 实现与 AnthropicAIClient / DeepSeekAIClient 相同的
create / stream 接口，行为由每个测试自己编排。
"""

import json
import re
from types import SimpleNamespace

import pytest

from wealthpilot.services import ai_client
from wealthpilot.services.agents import orchestrator
from wealthpilot.services.agents.planner_agent import PlannerAgent
from wealthpilot.services.ai_client import CompletionResult, ToolCall, create_ai_client

SETTINGS = SimpleNamespace(
    active_model="fake", agent_max_parallel=2, critic_enabled=True,
    critic_max_replans=1, critic_max_rewrites=1, run_timeout_seconds=30,
    agent_max_tool_rounds=2, agent_max_tokens=1000, planner_max_tasks=4,
)


class _Stream:
    def __init__(self, result: CompletionResult):
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def text_stream(self):
        yield from ([self.result.text] if self.result.text else [])

    def get_final_result(self):
        return self.result


class FakeClient:
    """create 依次返回 planner / critic 的 JSON；stream 交给 on_stream 回调决定。"""

    def __init__(self, on_stream, creates=()):
        self.on_stream = on_stream
        self.creates = list(creates)
        self.stream_calls: list[dict] = []

    def create(self, **kwargs):
        if not self.creates:
            raise RuntimeError("offline")
        return CompletionResult(text=self.creates.pop(0))

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        return _Stream(self.on_stream(kwargs))


def _tool_use(name="get_fund_info", args=None) -> CompletionResult:
    tc = ToolCall(id="tu_1", name=name, input=args or {"fund_code": "110011"})
    return CompletionResult(
        stop_reason="tool_use", tool_calls=[tc],
        raw_content=[{"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}],
    )


def _evidence_id(kwargs) -> str:
    """从回传给模型的 tool_result 里取证据 ID —— 模型只能从这里知道该引用什么。"""
    blocks = kwargs["messages"][-1]["content"]
    return re.search(r"\[(E-[a-f0-9]+)\]", blocks[0]["content"]).group(1)


async def _run(monkeypatch, client, message="110011 基金净值多少", settings=SETTINGS):
    async def fake_tool(name, *args, **kwargs):
        return "基金 110011 最新净值 1.5983"

    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    monkeypatch.setattr("wealthpilot.services.agents.base.get_settings", lambda: settings)
    monkeypatch.setattr("wealthpilot.services.agents.planner_agent.get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator, "create_ai_client", lambda _: client)
    monkeypatch.setattr("wealthpilot.services.agents.base.execute_tool", fake_tool)
    events = []
    async for line in orchestrator.chat_stream(message, [], [], {}):
        events.append(json.loads(line[6:]))
    return events


def _done(events) -> dict:
    return next(e for e in events if e["type"] == "done")


PLAN = '{"intent":"查询","tasks":[{"id":"t1","agent":"fund","goal":"查净值"}],"success_criteria":["最新净值"]}'


async def test_single_task_answer_is_published_with_citation(monkeypatch):
    def on_stream(kwargs):
        if kwargs["messages"][-1]["role"] == "user" and isinstance(kwargs["messages"][-1]["content"], str):
            return _tool_use()
        return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")

    client = FakeClient(on_stream, creates=[PLAN, '{"missing":[]}'])
    events = await _run(monkeypatch, client)
    done = _done(events)
    assert done["meta"]["status"] == "passed"
    assert "1.5983" in done["content"]
    # 单任务快路径：专业 Agent 的回答直接过审，不需要 Synthesizer 再写一遍
    assert len(client.stream_calls) == 2


async def test_exhausted_tool_rounds_force_a_final_answer(monkeypatch):
    def on_stream(kwargs):
        if kwargs.get("tool_choice") == "none":
            return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")
        return _tool_use(args={"fund_code": "110011", "n": len(kwargs["messages"])})

    client = FakeClient(on_stream, creates=[PLAN, '{"missing":[]}'])
    events = await _run(monkeypatch, client)
    task_done = next(e for e in events if e["type"] == "task_done")
    assert task_done["status"] == "completed"
    assert _done(events)["meta"]["status"] == "passed"
    assert client.stream_calls[-1]["tool_choice"] == "none"


async def test_all_tasks_failed_short_circuits(monkeypatch):
    def on_stream(kwargs):
        raise RuntimeError("401 invalid key")

    client = FakeClient(on_stream)  # planner 也不可用 → 关键词兜底
    events = await _run(monkeypatch, client)
    assert _done(events)["meta"]["status"] == "failed"
    assert not [e for e in events if e["type"] in ("replan", "critic")]
    assert len(client.stream_calls) == 1


async def test_truncated_output_is_not_published(monkeypatch):
    client = FakeClient(lambda kw: CompletionResult(text="最新净值 1.59", stop_reason="max_tokens"),
                        creates=[PLAN])
    events = await _run(monkeypatch, client)
    assert next(e for e in events if e["type"] == "task_done")["status"] == "truncated"
    assert _done(events)["meta"]["status"] != "passed"
    assert "1.59" not in _done(events)["content"]


def test_fallback_plan_uses_raw_question_not_history():
    client = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    plan = PlannerAgent(client, "m").plan("今天天气如何", context="user: 帮我看看回撤和相关性风险")
    assert [t.agent for t in plan.tasks] == ["portfolio"]
    assert plan.tasks[0].goal == "今天天气如何"


@pytest.mark.parametrize("key", ["", "sk-ant-xxx", "  "])
def test_placeholder_key_is_treated_as_unset(key):
    settings = SimpleNamespace(ai_provider="anthropic", anthropic_api_key=key)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_ai_client(settings)


def test_thinking_blocks_survive_for_tool_round_replay():
    def block(**kw):
        return SimpleNamespace(model_dump=lambda exclude_none=True: dict(kw), **kw)

    response = SimpleNamespace(stop_reason="tool_use", content=[
        block(type="thinking", thinking="", signature="sig"),
        block(type="tool_use", id="tu", name="get_fund_info", input={"fund_code": "1"}),
    ])
    result = ai_client._anthropic_response_to_result(response)
    assert [b["type"] for b in result.raw_content] == ["thinking", "tool_use"]
    assert result.raw_content[0]["signature"] == "sig"


def test_max_tokens_stop_reason_is_surfaced():
    response = SimpleNamespace(stop_reason="max_tokens", content=[])
    assert ai_client._anthropic_response_to_result(response).stop_reason == "max_tokens"


# ── 真实模型跑出来的 Critic 误杀（回归） ────────────────────────────

def _ev(eid, output, inputs=None, status="ok"):
    from wealthpilot.services.agents.base import AgentResult
    return AgentResult("market", "g", "", [
        {"id": eid, "tool": "t", "input": inputs or {}, "output": output, "status": status}])


@pytest.mark.parametrize("answer", [
    "# 易方达优质精选（110011）最新净值",                      # 标题里的基金代码来自工具入参
    "- 2026-09-29：3.9702（-0.25%）、09-28 为 3.9801",        # 日期不是数值
    "近20个交易日区间收益率 -3.51% [E-aaaaaaaaaaaa]",          # 天数来自入参
    "近一个月下跌约 3.51% [E-aaaaaaaaaaaa]",                  # 文字表达方向
    "口径说明：-3.51% 为交易日区间口径",                        # 未带引用的说明行对照全部证据
])
def test_grounding_accepts_legitimate_references(answer):
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", "2026-09-29: 净值3.9702, 涨跌-0.25%\n2026-09-28: 净值3.9801\n区间收益率: -3.51%",
                   {"fund_code": "110011", "days": 20})]
    assert check_numeric_grounding(answer, results)["ungrounded"] == []


def test_grounding_still_rejects_invented_numbers():
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", "区间收益率: -3.51%", {"fund_code": "110011"})]
    assert check_numeric_grounding("预计上涨 8.8%", results)["ungrounded"] == ["8.8"]
    assert check_numeric_grounding("区间收益率 3.51% [E-aaaaaaaaaaaa]", results)["ungrounded"] == ["3.51"]


def test_citing_failed_evidence_is_allowed_but_unknown_id_is_not():
    from wealthpilot.services.agents.critic_agent import CriticAgent
    results = [_ev("E-aaaaaaaaaaaa", "净值 1.5"), _ev("E-bbbbbbbbbbbb", "当前没有持仓", status="insufficient_data")]
    critic = CriticAgent(None, "m")
    assert critic.review_answer("净值 1.5 [E-aaaaaaaaaaaa]；无持仓 [E-bbbbbbbbbbbb]", results).passed
    assert not critic.review_answer("净值 1.5 [E-aaaaaaaaaaaa][E-cccccccccccc]", results).passed


async def test_unfillable_gap_is_disclosed_not_refused(monkeypatch):
    def on_stream(kwargs):
        last = kwargs["messages"][-1]["content"]
        if "tools" not in kwargs:  # Synthesizer
            assert "同类平均" in last and "当前数据无法判断" in last
            eid = re.search(r"\[(E-[a-f0-9]+)\]", last).group(1)
            return CompletionResult(text=f"最新净值 1.5983 [{eid}]\n同类平均：当前数据无法判断")
        if isinstance(last, str):
            if "补充查证" in last:
                return CompletionResult(text="工具取不到同类平均数据")
            return _tool_use()
        return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")

    missing = '{"missing":["同类平均对比"]}'
    client = FakeClient(on_stream, creates=[PLAN, missing, missing])
    events = await _run(monkeypatch, client)
    done = _done(events)
    assert done["meta"]["status"] == "partial"
    assert done["meta"]["missing_evidence"] == ["同类平均对比"]
    assert "1.5983" in done["content"] and "无法判断" in done["content"]


async def test_tool_round_preamble_is_not_part_of_the_answer(monkeypatch):
    def on_stream(kwargs):
        if isinstance(kwargs["messages"][-1]["content"], str):
            result = _tool_use()
            result.text = "I'll query the fund first."
            return result
        return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")

    events = await _run(monkeypatch, FakeClient(on_stream, creates=[PLAN, '{"missing":[]}']))
    assert "query" not in _done(events)["content"]


def test_restating_users_rule_or_backtest_result_is_not_advice():
    from wealthpilot.services.agents.base import AgentResult
    from wealthpilot.services.agents.critic_agent import CriticAgent
    bt = AgentResult("quant", "g", "", [{"id": "E-aaaaaaaaaaaa", "tool": "backtest_rule", "status": "ok",
                                         "input": {"fund_code": "110011"}, "output": '{"lump_sum":{"total_return_pct":-30.15}}'}])
    critic = CriticAgent(None, "m")  # 未测评
    ok = "规则为回撤 5% 时加仓 30%；一次性买入收益 -30.15% [E-aaaaaaaaaaaa]"
    assert critic.review_answer(ok, [bt], "回撤5%加30%的规则好吗").passed
    assert not critic.review_answer("建议加仓 15% [E-aaaaaaaaaaaa]", [bt], "回撤5%加30%的规则好吗").passed


def test_index_names_and_cross_evidence_numbers_are_grounded():
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", "最大回撤 6.81%", {"fund_code": "110011"}),
               _ev("E-bbbbbbbbbbbb", "区间收益率: -3.51%", {"days": 250})]
    answer = "基准含沪深300与中证500；近 250 个交易日区间收益率 -3.51% [E-aaaaaaaaaaaa]"
    assert check_numeric_grounding(answer, results)["ungrounded"] == []


@pytest.mark.parametrize("answer", [
    "最大持仓占比 31.24% [E-aaaaaaaaaaaa]",          # 工具给小数 0.3124
    "两者相关系数 -0.12 [E-aaaaaaaaaaaa]",           # 工具给 -0.117
    "累计收益 8,348.4 元 [E-aaaaaaaaaaaa]",          # 千分位
])
def test_grounding_accepts_reformatted_numbers(answer):
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", '{"weights":{"007340":0.3124},"corr":-0.117,"total_return":8348.4}')]
    assert check_numeric_grounding(answer, results)["ungrounded"] == []


def test_grounding_rounding_is_not_a_loophole():
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", '{"weights":{"007340":0.3124},"corr":-0.117}')]
    assert check_numeric_grounding("占比 35.5%，相关系数 0.12", results)["ungrounded"] == ["0.12", "35.5"]


@pytest.mark.parametrize("answer", [
    "最大回撤 -11.75% [E-aaaaaaaaaaaa]",       # 工具把回撤幅度存成正数
    "本周浮亏 2530.1 元 [E-aaaaaaaaaaaa]",     # 文字表达了方向
])
def test_grounding_accepts_loss_and_drawdown_phrasing(answer):
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [_ev("E-aaaaaaaaaaaa", '{"max_drawdown_pct": 11.75, "weekly_return": -2530.1}')]
    assert check_numeric_grounding(answer, results)["ungrounded"] == []


async def test_mostly_grounded_draft_is_published_with_named_gaps(monkeypatch):
    numbers = "、".join(f"{n}.5" for n in range(20, 40))  # 20 个能溯源的数

    def on_stream(kwargs):
        last = kwargs["messages"][-1]["content"]
        if "tools" not in kwargs:
            eid = re.search(r"\[(E-[a-f0-9]+)\]", last).group(1)
            return CompletionResult(text=f"净值序列 {numbers} [{eid}]\n合计 999.9")  # 999.9 是模型自己加的
        if isinstance(last, str):
            return _tool_use()
        return CompletionResult(text=f"净值序列 {numbers} [{_evidence_id(kwargs)}]\n合计 999.9")

    async def fake_tool(name, *args, **kwargs):
        return numbers

    client = FakeClient(on_stream, creates=[PLAN, '{"missing":[]}'])
    monkeypatch.setattr(orchestrator, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr("wealthpilot.services.agents.base.get_settings", lambda: SETTINGS)
    monkeypatch.setattr("wealthpilot.services.agents.planner_agent.get_settings", lambda: SETTINGS)
    monkeypatch.setattr(orchestrator, "create_ai_client", lambda _: client)
    monkeypatch.setattr("wealthpilot.services.agents.base.execute_tool", fake_tool)
    events = [json.loads(line[6:]) async for line in orchestrator.chat_stream("净值多少", [], [], {})]
    done = _done(events)
    assert done["meta"]["status"] == "partial"
    assert "未能核对的数字" in done["content"] and "999.9" in done["content"]


def test_restating_profile_constraints_and_day_of_month_is_grounded():
    from wealthpilot.models.profile import InvestorProfile
    from wealthpilot.services.agents.critic_agent import CriticAgent
    profile = InvestorProfile(user_id=1, risk_level=3, horizon_months=36, max_drawdown_tolerance=0.2,
                              liquidity_reserve=20000, experience_years=4)
    results = [_ev("E-aaaaaaaaaaaa", "净值 4.0054")]
    answer = "净值 4.0054 [E-aaaaaaaaaaaa]，23日至28日小幅回落。按你的画像（36 个月、最大回撤 20%、储备金 20000 元）核对。"
    assert CriticAgent(None, "m", profile).review_answer(answer, results).ungrounded_numbers == []
