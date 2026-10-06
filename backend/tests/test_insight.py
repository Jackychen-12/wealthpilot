"""资金与筹码、预期与消息：换算、汇总，以及工具对"过期的""没有的"数据怎么处理。"""

import json
from datetime import date, timedelta

import httpx

from wealthpilot.services import capital, expectation, stocks
from wealthpilot.services.agents import insight_tools
from wealthpilot.services.agents.tools import AGENT_TOOLS, execute_tool


def _days_ago(n: int) -> str:
    return str(date.today() - timedelta(days=n))


def test_flow_summary_counts_streak_and_windows():
    daily = [{"date": f"2026-09-{30 - i:02d}", "net_yi": v} for i, v in enumerate([1.2, 0.5, 2.0, -0.4, 1.0] + [0.1] * 20)]
    out = capital.summarize_flow({"daily": daily})
    assert out["as_of"] == "2026-09-30" and out["streak_days"] == 3           # 连续三天净流入，第四天是流出
    assert out["net_5d_yi"] == 4.3 and out["net_20d_yi"] == round(4.3 + 0.1 * 15, 2)
    falling = capital.summarize_flow({"daily": [{"date": "d", "net_yi": -1.0}, {"date": "c", "net_yi": -2.0}, {"date": "b", "net_yi": 3.0}]})
    assert falling["streak_days"] == -2 and "net_5d_yi" not in falling          # 不够五天就不给五日合计
    assert capital.summarize_flow({"daily": []})["streak_days"] == 0


def test_margin_summary_reports_change_over_windows():
    rows = [{"date": f"d{i}", "financing_balance_yi": 100.0 - i, "short_balance_yi": 1.0, "financing_to_float_mv_pct": 2.0} for i in range(30)]
    out = capital.summarize_margin(rows)
    assert out["financing_balance_yi"] == 100.0 and out["financing_balance_change_5d_pct"] == round((100 / 95 - 1) * 100, 2)
    assert "financing_balance_change_20d_pct" in out and "financing_balance_change_60d_pct" not in out


def test_new_agents_get_their_own_tools():
    assert {t["name"] for t in AGENT_TOOLS["capital"]} == {"resolve_security", *insight_tools.CAPITAL}
    assert {t["name"] for t in AGENT_TOOLS["expectation"]} == {"resolve_security", *insight_tools.EXPECTATION}
    assert "get_business_segments" in {t["name"] for t in AGENT_TOOLS["fundamental"]}


async def _call(name, **inputs):
    return await execute_tool(name, {"code": "600519", **inputs}, [], {})


async def test_insider_activity_keeps_only_the_last_two_years(monkeypatch):
    async def holders(code, limit):
        return [{"notice_date": _days_ago(100), "holder": "大股东", "direction": "减持", "shares_wan": 500.0},
                {"notice_date": _days_ago(900), "holder": "很久以前", "direction": "增持", "shares_wan": 1.0}]

    async def executives(code, limit):
        return [{"date": _days_ago(2000), "person": "老高管", "shares": -700}]

    async def empty(*a, **k):
        return []
    monkeypatch.setattr(capital, "fetch_holder_trades", holders)
    monkeypatch.setattr(capital, "fetch_executive_trades", executives)
    monkeypatch.setattr(capital, "fetch_buybacks", empty)
    monkeypatch.setattr(capital, "fetch_unlocks", empty)
    data = json.loads(await _call("get_insider_activity"))
    assert [h["holder"] for h in data["holder_trades"]] == ["大股东"] and data["executive_trades"] == []
    assert "没有查到记录" in data["note"]                # 空列表要照实说成"没查到"，不是"没有风险"


async def test_consensus_adds_forward_pe_and_marks_targets_as_broker_views(monkeypatch):
    async def consensus(code):
        return {"name": "贵州茅台", "org_count": 43, "ratings": {"买入": 34, "增持": 9, "中性": 0, "减持": 0, "卖出": 0},
                "eps": [{"year": 2025, "eps": 65.85, "actual": True}, {"year": 2026, "eps": 67.25, "actual": False, "growth_pct": 2.13}],
                "target_price_low": 1430.0, "target_price_high": 2030.0, "concepts": []}

    async def quote(code):
        return {"price": 1258.62, "name": "贵州茅台"}
    monkeypatch.setattr(expectation, "fetch_consensus", consensus)
    monkeypatch.setattr(insight_tools, "fetch_stock_quote", quote)
    data = json.loads(await _call("get_consensus_forecast"))
    assert data["eps_forecast"][1]["pe_at_current_price"] == round(1258.62 / 67.25, 2)
    assert data["broker_target_vs_price_pct"] == [round((1430 / 1258.62 - 1) * 100, 1), round((2030 / 1258.62 - 1) * 100, 1)]
    assert "券商给出的目标价" in data["note"] and "偏乐观" in data["note"]

    async def nobody(code):
        return {"name": "x", "org_count": 0, "ratings": {}, "eps": [], "target_price_low": None, "target_price_high": None, "concepts": []}
    monkeypatch.setattr(expectation, "fetch_consensus", nobody)
    assert (await _call("get_consensus_forecast")).startswith("未获取到")


async def test_stale_guidance_is_not_passed_off_as_current(monkeypatch):
    async def old(code):
        return {"forecast": {"notice_date": _days_ago(700), "report_date": "2024-12-31", "items": []},
                "express": {"notice_date": _days_ago(2500), "report_date": "2019-06-30"}}
    monkeypatch.setattr(expectation, "fetch_guidance", old)
    assert (await _call("get_earnings_guidance")).startswith("未获取到")

    async def fresh(code):
        return {"forecast": {"notice_date": _days_ago(30), "report_date": "2026-09-30", "items": [{"metric": "净利润", "type": "预增"}]},
                "express": {"notice_date": _days_ago(2500), "report_date": "2019-06-30"}}
    monkeypatch.setattr(expectation, "fetch_guidance", fresh)
    data = json.loads(await _call("get_earnings_guidance"))
    assert "forecast" in data and "express" not in data


async def test_missing_data_is_reported_as_missing(monkeypatch):
    async def nothing(*a, **k):
        return None

    async def none_list(*a, **k):
        return []
    monkeypatch.setattr(capital, "fetch_fund_flow", nothing)
    monkeypatch.setattr(capital, "fetch_margin", none_list)
    monkeypatch.setattr(expectation, "fetch_research_reports", none_list)
    for name in ("get_capital_flow", "get_margin_trading", "get_research_reports"):
        assert (await _call(name)).startswith("未获取到"), name


def _mock_http(monkeypatch, module, payload):
    real = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: real(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), **{k: v for k, v in kw.items() if k != "transport"}))


async def test_minute_series_turns_cumulative_volume_into_per_minute(monkeypatch):
    _mock_http(monkeypatch, stocks, {"data": {"sh600519": {
        "data": {"date": "20260930", "data": ["0930 100.00 10 100000.00", "0931 101.00 25 251000.00", "0932 100.50 25 251000.00"]},
        "qt": {"sh600519": ["1", "贵州茅台", "600519", "100.50", "99.00"]}}}})
    data = await stocks.fetch_minute("600519", 1)
    assert data["prev_close"] == 99.0 and data["name"] == "贵州茅台"
    assert [p["volume"] for p in data["points"]] == [10.0, 15.0, 0.0]            # 累计量相减
    assert data["points"][1]["time"] == "2026-09-30 09:31" and data["points"][1]["avg"] == round(251000 / 2500, 3)


async def test_business_segments_split_by_kind_and_sort_by_share(monkeypatch):
    async def rows(report, **kw):
        base = {"REPORT_DATE": "2026-06-30 00:00:00", "REPORT_NAME": "2026中报"}
        return [{**base, "MAINOP_TYPE": "2", "ITEM_NAME": "系列酒", "MAIN_BUSINESS_INCOME": 129.34e8, "MBI_RATIO": 0.1426, "GROSS_RPOFIT_RATIO": 0.7359},
                {**base, "MAINOP_TYPE": "2", "ITEM_NAME": "茅台酒", "MAIN_BUSINESS_INCOME": 777.24e8, "MBI_RATIO": 0.8569, "GROSS_RPOFIT_RATIO": 0.9228},
                {**base, "MAINOP_TYPE": "3", "ITEM_NAME": "国内", "MAIN_BUSINESS_INCOME": 896.66e8, "MBI_RATIO": 0.9886, "GROSS_RPOFIT_RATIO": 0.8953},
                {"REPORT_DATE": "2025-12-31 00:00:00", "MAINOP_TYPE": "2", "ITEM_NAME": "上一期的不要", "MBI_RATIO": 1.0}], 1
    monkeypatch.setattr(stocks, "datacenter", rows)
    data = await stocks.fetch_business_segments("600519")
    assert [s["name"] for s in data["by_product"]] == ["茅台酒", "系列酒"] and data["by_product"][0]["gross_margin_pct"] == 92.28
    assert data["by_region"][0]["revenue_yi"] == 896.66 and data["by_industry"] == [] and data["report_name"] == "2026中报"
