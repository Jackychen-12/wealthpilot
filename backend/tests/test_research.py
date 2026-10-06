"""股票主导架构：证券解析、研究模板、选股、估值分位、缓存、新校验规则。不打真实网络。"""

from datetime import date

import pytest

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services import cache, screener, securities, stocks
from wealthpilot.services.agents import orchestrator, tools
from wealthpilot.services.agents.critic_agent import CriticAgent
from wealthpilot.services.agents.planner_agent import Plan, PlannerAgent
from wealthpilot.services.agents.playbooks import PLAYBOOKS, build_tasks
from wealthpilot.services.agents.registry import AGENTS, build_agent

MAOTAI = {"code": "600519", "name": "贵州茅台", "asset_type": "stock", "industry": "白酒Ⅱ"}
WULIANGYE = {"code": "000858", "name": "五粮液", "asset_type": "stock", "industry": "白酒Ⅱ"}
FUND = {"code": "110011", "name": "易方达优质精选", "asset_type": "fund", "industry": ""}

SNAP = {"trade_date": "2026-09-30", "report_date": "2026-06-30", "stocks": [
    {"code": "600519", "name": "贵州茅台", "industry": "白酒Ⅱ", "price": 1258.6, "change_pct": 1.86, "total_mv_yi": 15733.0,
     "pe_ttm": 19.3, "pb": 6.3, "ps_ttm": 9.1, "roe_pct": 16.8, "revenue_yoy_pct": 1.3, "profit_yoy_pct": -1.95},
    {"code": "000858", "name": "五粮液", "industry": "白酒Ⅱ", "price": 70.0, "change_pct": 1.88, "total_mv_yi": 2719.0,
     "pe_ttm": 20.8, "pb": 2.3, "ps_ttm": 4.0, "roe_pct": 11.0, "revenue_yoy_pct": 3.0, "profit_yoy_pct": 2.0},
    {"code": "000001", "name": "平安银行", "industry": "银行Ⅱ", "price": 11.6, "change_pct": -0.5, "total_mv_yi": 2245.0,
     "pe_ttm": 5.2, "pb": 0.48, "ps_ttm": 1.7, "roe_pct": 5.0, "revenue_yoy_pct": -8.0, "profit_yoy_pct": -3.0},
    {"code": "300001", "name": "亏损科技", "industry": "软件开发", "price": 8.0, "change_pct": 9.9, "total_mv_yi": 60.0,
     "pe_ttm": -35.0, "pb": 4.0, "ps_ttm": 6.0, "roe_pct": -12.0, "revenue_yoy_pct": 40.0, "profit_yoy_pct": None},
    {"code": "600001", "name": "*ST 某某", "industry": "银行Ⅱ", "price": 2.0, "change_pct": -5.0, "total_mv_yi": 30.0,
     "pe_ttm": 4.0, "pb": 0.3, "ps_ttm": 1.0, "roe_pct": 8.0, "revenue_yoy_pct": 1.0, "profit_yoy_pct": 1.0},
]}


def holding(code, asset_type="stock", shares=100.0, cost=10.0, name=None):
    return PortfolioHolding(user_id=0, asset_type=asset_type, fund_code=code, fund_name=name or code,
                            shares=shares, cost_price=cost, buy_date=date(2025, 1, 1))


# ── 证券解析 ───────────────────────────────────────────

@pytest.fixture
def snap(monkeypatch):
    async def fake():
        return SNAP
    monkeypatch.setattr(securities, "snapshot", fake)
    monkeypatch.setattr(screener, "snapshot", fake)


async def test_resolve_finds_names_and_codes_in_free_text(snap, monkeypatch):
    async def no_search(*a, **k):
        return []
    monkeypatch.setattr(securities, "search", no_search)
    found = await securities.resolve_text("贵州茅台和000858哪个便宜")
    assert {s["code"] for s in found} == {"600519", "000858"}
    assert all(s["asset_type"] == "stock" for s in found)


async def test_resolve_prefers_known_holdings_and_falls_back_to_search(snap, monkeypatch):
    async def search(query, limit=8):
        return [{"code": "110011", "name": "易方达优质精选混合", "asset_type": "fund", "type_label": "基金"}] if query == "110011" else []
    monkeypatch.setattr(securities, "search", search)
    known = [{"code": "161725", "name": "招商中证白酒", "asset_type": "fund"}]
    found = await securities.resolve_text("招商中证白酒和110011对比", known)
    assert {(s["code"], s["asset_type"]) for s in found} == {("161725", "fund"), ("110011", "fund")}


async def test_unknown_code_is_not_invented(snap, monkeypatch):
    async def no_search(*a, **k):
        return []
    monkeypatch.setattr(securities, "search", no_search)
    assert await securities.resolve_text("帮我看看 999999") == []


# ── 意图识别与研究模板 ─────────────────────────────────

@pytest.mark.parametrize("message,resolved,has_holdings,expected", [
    ("帮我分析一下贵州茅台", [MAOTAI], False, "stock_deep"),
    ("贵州茅台现在多少钱", [MAOTAI], False, "free"),               # 只问一个数，不跑四个维度
    ("茅台和五粮液哪个好", [MAOTAI, WULIANGYE], False, "stock_compare"),
    ("帮我找出 ROE 高的白酒股", [], False, "screen"),
    ("我的持仓怎么样", [], True, "holding_review"),
    ("我的持仓怎么样", [], False, "free"),                         # 没有持仓就没法诊断
    ("这只基金怎么样", [FUND], False, "free"),                     # 基金不走个股模板
])
def test_intent_rules(message, resolved, has_holdings, expected):
    assert PlannerAgent.classify_by_rules(message, resolved, has_holdings) == expected


def test_stock_deep_runs_six_dimensions_in_parallel_with_resolved_code():
    tasks = build_tasks("stock_deep", [MAOTAI], [], {}, "分析茅台")
    assert [t.agent for t in tasks] == ["fundamental", "valuation", "price", "industry", "capital", "expectation"]
    assert all("600519" in t.goal and not t.deps for t in tasks)
    assert len(Plan("x", tasks).waves()) == 1


def test_compare_covers_each_stock_and_caps_at_three():
    many = [MAOTAI, WULIANGYE, {**MAOTAI, "code": "000001", "name": "平安银行"}, {**MAOTAI, "code": "300750", "name": "宁德时代"}]
    tasks = build_tasks("stock_compare", many, [], {}, "")
    assert len(tasks) == 6 and {t.agent for t in tasks} == {"fundamental", "valuation"}
    assert not any("宁德时代" in t.goal for t in tasks)


def test_holding_review_focuses_on_largest_and_worst_direct_stocks():
    held = [holding("600519", shares=10, cost=1500, name="贵州茅台"), holding("000858", shares=100, cost=100, name="五粮液"),
            holding("110011", "fund", name="某基金")]
    tasks = build_tasks("holding_review", [], held, {"600519": 1258.0, "000858": 70.0}, "")
    assert tasks[0].agent == "portfolio"
    goals = " ".join(t.goal for t in tasks[1:])
    assert "贵州茅台" in goals and "五粮液" in goals and "某基金" not in goals


def test_playbook_falls_through_when_its_precondition_is_missing():
    assert build_tasks("stock_deep", [FUND], [], {}, "") == []     # 解析出来的是基金
    assert build_tasks("holding_review", [], [], {}, "") == []     # 没有持仓


def test_planner_uses_playbook_and_carries_required_sections():
    offline = type("C", (), {"create": lambda self, **kw: (_ for _ in ()).throw(RuntimeError("offline"))})()
    plan = PlannerAgent(offline, "m").plan("帮我分析一下贵州茅台", securities=[MAOTAI])
    assert plan.playbook == "stock_deep" and plan.source == "fallback"
    assert plan.sections == list(PLAYBOOKS["stock_deep"].sections)
    assert plan.securities == [MAOTAI]


def test_every_agent_builds_with_its_own_tools():
    for name in AGENTS:
        agent = build_agent(name, None, "m", [], {}, None, None)
        assert agent.name == name and agent.tools == tools.AGENT_TOOLS[name]
    assert "resolve_security" in {t["name"] for t in tools.AGENT_TOOLS["valuation"]}


async def test_orchestrator_passes_resolved_codes_to_agents(monkeypatch):
    """解析出的代码必须出现在交给 Agent 的任务上下文里 —— 这是"不让模型猜代码"的落点。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from wealthpilot.services.agents.base import AgentResult, BaseAgent
    from wealthpilot.services.agents.critic_agent import Verdict
    from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent

    async def resolved(*a, **k):
        return [MAOTAI]

    settings = SimpleNamespace(active_model="fake", agent_max_parallel=4, critic_enabled=False,
                               critic_max_replans=0, critic_max_rewrites=0, planner_max_tasks=4)
    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    monkeypatch.setattr("wealthpilot.services.agents.planner_agent.get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator, "create_ai_client", lambda _: Mock(create=Mock(side_effect=RuntimeError("offline"))))
    monkeypatch.setattr(orchestrator, "resolve_text", resolved)
    run = AsyncMock(return_value=AgentResult("price", "g", "ok", []))
    monkeypatch.setattr(BaseAgent, "run", run)
    monkeypatch.setattr(SynthesizerAgent, "run", AsyncMock(return_value="## 结论\nok"))
    monkeypatch.setattr(CriticAgent, "review_evidence", Mock(return_value=Verdict(passed=True)))

    events = [line async for line in orchestrator.chat_stream("帮我分析一下贵州茅台", [], [], {})]
    assert any('"type": "resolved"' in e and "600519" in e for e in events)
    assert run.await_count == 6
    for call in run.await_args_list:
        assert "贵州茅台：600519" in call.args[0][-1]["content"]


# ── 选股与板块 ─────────────────────────────────────────

def test_screen_applies_ranges_and_excludes_st_and_loss_makers():
    out = screener.screen(SNAP, {"pe_max": 25, "roe_min": 10})
    assert [s["name"] for s in out["stocks"]] == ["贵州茅台", "五粮液"]      # 按市值降序
    assert out["matched"] == 2 and out["criteria"] == {"exclude_st": True, "pe_max": 25.0, "roe_min": 10.0}
    assert out["trade_date"] == "2026-09-30" and out["report_date"] == "2026-06-30"


def test_pe_ceiling_never_lets_negative_pe_through():
    names = [s["name"] for s in screener.screen(SNAP, {"pe_max": 100})["stocks"]]
    assert "亏损科技" not in names


def test_screen_by_industry_sort_and_limit():
    out = screener.screen(SNAP, {"industry": "白酒", "sort_by": "roe_pct", "limit": 1})
    assert [s["name"] for s in out["stocks"]] == ["贵州茅台"] and out["matched"] == 2 and out["shown"] == 1
    assert screener.screen(SNAP, {"exclude_st": False, "industry": "银行"})["matched"] == 2


def test_sector_ranking_skips_tiny_sectors():
    many = {"trade_date": "d", "stocks": [
        {"code": f"{i:06d}", "name": f"s{i}", "industry": "大行业", "change_pct": float(i)} for i in range(6)
    ] + [{"code": "999999", "name": "x", "industry": "小行业", "change_pct": 50.0}]}
    ranking = screener.sector_ranking(many)
    assert [s["industry"] for s in ranking["top"]] == ["大行业"]
    assert ranking["top"][0]["median_change_pct"] == 3.0 and ranking["top"][0]["leader"]["name"] == "s5"


async def test_screen_tool_reports_missing_snapshot(monkeypatch):
    async def empty():
        return {}
    monkeypatch.setattr(screener, "snapshot", empty)
    assert (await tools.execute_tool("screen_stocks", {"pe_max": 10}, [], {})).startswith("未获取到")


# ── 估值分位与技术指标 ─────────────────────────────────

def test_valuation_percentile_against_own_history():
    history = [{"date": f"d{i}", "pe_ttm": float(v), "pb": 1.0, "ps_ttm": 1.0} for i, v in enumerate([10, *range(11, 111)])]
    summary = stocks.summarize_valuation(history)
    assert summary["pe"]["current"] == 10.0 and summary["pe"]["percentile"] == pytest.approx(1.0, abs=0.1)
    assert summary["pe"]["min"] == 10.0 and summary["pe"]["max"] == 110.0


def test_negative_pe_has_no_percentile():
    history = [{"date": f"d{i}", "pe_ttm": -5.0 if i == 0 else 20.0, "pb": 2.0, "ps_ttm": 1.0} for i in range(60)]
    summary = stocks.summarize_valuation(history)
    assert summary["pe"]["percentile"] is None and "无法计算" in summary["pe"]["note"]
    assert summary["pb"]["percentile"] is not None


def test_technicals_describe_ma_alignment_without_forecasting():
    falling = [{"nav_date": f"2026-01-{i + 1:02d}", "nav": 100.0 + i, "daily_return": -1.0} for i in range(60)]
    out = stocks.summarize_technicals(falling)        # 最新在前：价格一路走低
    assert out["ma_alignment"].startswith("空头排列") and out["vs_ma60_pct"] < 0
    assert "不构成" in out["note"]


# ── 缓存 ───────────────────────────────────────────────

async def test_cache_stores_hits_but_not_empty_results():
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return [] if calls["n"] == 1 else [1, 2]

    assert await cache.cached("t:empty-then-ok", cache.DAY, loader) == []
    assert await cache.cached("t:empty-then-ok", cache.DAY, loader) == [1, 2]   # 空结果没被缓存，重试了
    assert await cache.cached("t:empty-then-ok", cache.DAY, loader) == [1, 2] and calls["n"] == 2
    assert cache.read("t:empty-then-ok", ttl=-1) is None                          # 过期即失效


# ── Critic 的研究规则 ─────────────────────────────────

def _evidence(output):
    from wealthpilot.services.agents.base import AgentResult
    return [AgentResult("fundamental", "g", "", [{"id": "E-aaaaaaaaaaaa", "tool": "t", "input": {}, "status": "ok", "output": output}])]


def test_missing_required_section_is_rejected():
    critic = CriticAgent(None, "m")
    answer = "## 结论\n净利润 445.17 亿元（2026-06-30）[E-aaaaaaaaaaaa]\n## 基本面\n同上 [E-aaaaaaaaaaaa]"
    verdict = critic.review_answer(answer, _evidence("净利润 445.17"), sections=["结论", "基本面", "估值"])
    assert not verdict.passed and "估值" in verdict.issues[-1]
    assert critic.review_answer(answer, _evidence("净利润 445.17"), sections=["结论", "基本面"]).passed


def test_financial_figures_need_a_report_period():
    critic = CriticAgent(None, "m")
    bare = "净利润 445.17 亿元 [E-aaaaaaaaaaaa]"
    assert any("报告期" in i for i in critic.review_answer(bare, _evidence("445.17")).issues)
    assert critic.review_answer("2026 中报净利润 445.17 亿元 [E-aaaaaaaaaaaa]", _evidence("445.17 2026")).passed


def test_below_average_wording_matches_negative_source():
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = _evidence('{"vs_ma20_pct": -8.59, "period_return_pct": -18.82}')
    assert check_numeric_grounding("现价低于 MA20 达 8.59%，区间下挫 18.82% [E-aaaaaaaaaaaa]", results)["ungrounded"] == []


# ── 自选股与研究记录接口 ───────────────────────────────

def _client_and_users():
    import uuid

    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    client = TestClient(app)

    def user():
        token = client.post("/api/auth/register", json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "pass1234"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return client, user(), user()


def test_watchlist_is_per_user_and_idempotent(monkeypatch):
    from wealthpilot.routes import research as route

    async def quotes(codes):
        return {c: {"price": 10.0, "change_pct": 1.5} for c in codes}
    monkeypatch.setattr(route, "fetch_sina_quotes", quotes)
    client, alice, bob = _client_and_users()

    first = client.post("/api/watchlist", json={"code": "600519", "name": "贵州茅台", "note": "等估值回落"}, headers=alice).json()
    again = client.post("/api/watchlist", json={"code": "600519", "name": "贵州茅台"}, headers=alice).json()
    assert again == {"id": first["id"], "already": True}

    mine = client.get("/api/watchlist", headers=alice).json()
    assert [(w["code"], w["note"], w["price"]) for w in mine] == [("600519", "等估值回落", 10.0)]
    assert client.get("/api/watchlist", headers=bob).json() == []
    # 别人的自选改不了、删不掉，且与"不存在"返回一致
    assert client.delete(f"/api/watchlist/{first['id']}", headers=bob).status_code == 404
    assert client.put(f"/api/watchlist/{first['id']}", json={"note": "x"}, headers=bob).status_code == 404
    assert client.delete(f"/api/watchlist/{first['id']}", headers=alice).json() == {"ok": True}
    assert client.post("/api/watchlist", json={"code": "abc"}, headers=alice).status_code == 422


def test_research_history_lists_only_own_records():
    from sqlmodel import Session

    from wealthpilot.models.chat import ChatMessage
    from wealthpilot.services.auth import decode_token
    from wealthpilot.storage.db import get_engine
    client, alice, bob = _client_and_users()
    alice_id = int(decode_token(alice["Authorization"][7:])["sub"])
    with Session(get_engine()) as db:
        db.add(ChatMessage(user_id=alice_id, conversation_id="c1", role="user", content="分析茅台"))
        db.add(ChatMessage(user_id=alice_id, conversation_id="c1", role="assistant", content="## 结论",
                           metadata_json='{"status":"passed","playbook":"stock_deep","evidence":[{"id":"E-1"}]}'))
        db.commit()
    listed = client.get("/api/research/history", headers=alice).json()
    assert [(r["question"], r["status"], r["playbook"], r["evidence_count"]) for r in listed] == [("分析茅台", "passed", "stock_deep", 1)]
    assert client.get("/api/research/history", headers=bob).json() == []
    assert client.get(f"/api/research/history/{listed[0]['id']}", headers=bob).status_code == 404
    assert client.get(f"/api/research/history/{listed[0]['id']}", headers=alice).json()["answer"] == "## 结论"


def test_screener_endpoint_uses_the_same_logic_as_the_tool(snap):
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    out = TestClient(app).post("/api/screener", json={"industry": "白酒", "roe_min": 15}).json()
    assert [s["name"] for s in out["stocks"]] == ["贵州茅台"]
