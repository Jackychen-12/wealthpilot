"""终端入口：命令解析、本机后端直连、研究过程渲染。不联网、不调模型。"""

import io

import pytest
from rich.console import Console

from wealthpilot import tui


def test_screen_shorthand_maps_to_screener_criteria():
    assert tui.parse_screen("pe<15 roe>15 mv>200 白酒") == {
        "limit": 20, "pe_max": 15.0, "roe_min": 15.0, "mv_min_yi": 200.0, "industry": "白酒"}
    assert tui.parse_screen("mv<500 rev>=30 profit>30 chg>-2") == {
        "limit": 20, "mv_max_yi": 500.0, "revenue_yoy_min": 30.0, "profit_yoy_min": 30.0, "change_min": -2.0}
    with pytest.raises(ValueError, match="roe 只支持"):
        tui.parse_screen("roe<5")
    with pytest.raises(ValueError, match="不认识的条件"):
        tui.parse_screen("eps>1")


def test_citations_are_shortened_for_the_terminal():
    assert tui.cite("营收 100 亿 [E-5ea7c0ffee12]。") == "营收 100 亿 `5ea7`。"


class FakeBackend(tui.Backend):
    label = "测试"

    def __init__(self, events):
        self.events = events

    async def chat(self, message, history, conversation_id):
        for e in self.events:
            yield e

    async def close(self):
        pass


def run_app(events):
    out = io.StringIO()
    app = tui.App(FakeBackend(events), Console(file=out, width=120, force_terminal=False))
    return app, out


async def test_research_renders_process_answer_checkpoints_and_proposals():
    cp = {"name": "贵州茅台", "code": "600519", "metric_label": "营收同比", "op": ">=", "threshold": 0.0, "baseline_value": 1.3,
          "baseline_as_of": "2026-06-30", "status": "pending", "actual_value": None, "actual_as_of": "", "due": "下一期财报"}
    proposal = {"id": 3, "action_label": "加仓", "name": "贵州茅台", "code": "600519", "shares": 100, "price_ref": 1258.62,
                "reason": "估值处于低位", "invalidation": "营收同比转负", "status": "proposed", "exec_shares": None, "exec_price": None}
    app, out = run_app([
        {"type": "resolved", "securities": [{"name": "贵州茅台", "code": "600519"}]},
        {"type": "plan", "intent": "个股深度研究", "tasks": [{"agent": "valuation", "label": "⚖️ 估值", "goal": "研究估值"}]},
        {"type": "evidence", "evidence": {"id": "E-5ea7c0ffee12", "tool": "get_valuation_history", "input": {"code": "600519"}, "output": "PE 19.32"}},
        {"type": "task_done", "agent": "valuation", "status": "completed", "tools": ["get_valuation_history"]},
        {"type": "critic", "gate": "answer", "attempt": 1, "passed": False, "issues": ["以下数字未出现在工具返回中：42"]},
        {"type": "checkpoints", "items": [cp], "proposals": [proposal]},
        {"type": "done", "content": "## 结论\nPE 19.32 [E-5ea7c0ffee12]", "meta": {"status": "passed"}},
    ])
    await app.research("帮我分析一下贵州茅台")
    text = out.getvalue()
    for expected in ("已解析", "600519", "个股深度研究", "打回", "PE 19.32", "已通过校验", "营收同比 ≥ 0%", "下一期财报 核对",
                     "#3", "加仓", "失效条件：营收同比转负", "/approve"):
        assert expected in text, expected
    assert len(app.history) == 2 and app.evidence[0]["tool"] == "get_valuation_history"

    out.truncate(0)
    await app.cmd_evidence("5ea7")
    assert "PE 19.32" in out.getvalue()


async def test_unpublished_answers_do_not_enter_the_conversation_and_errors_do_not_crash():
    app, out = run_app([{"type": "done", "content": "证据不足", "meta": {"status": "rejected"}}])
    assert await app.handle("随便问问") is True
    assert app.history == [] and "未通过校验" in out.getvalue()
    assert await app.handle("/nope") is True and "没有这个命令" in out.getvalue()
    assert await app.handle("/screen eps>1") is True and "不认识的条件" in out.getvalue()
    assert await app.handle("/quit") is False


async def test_local_backend_serves_the_api_in_process():
    backend = tui.LocalBackend()
    try:
        assert (await backend.request("GET", "/health"))["status"] == "ok"
        assert isinstance(await backend.request("GET", "/api/checkpoints/scorecard"), dict)
        with pytest.raises(RuntimeError, match="未知工具"):
            await backend.tool("delete_everything")
    finally:
        await backend.close()
        from wealthpilot.main import app
        app.dependency_overrides.clear()
