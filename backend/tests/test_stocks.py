"""个股能力：代码规范化、历史行情分发、个股工具、直接持股并入穿透。不打真实网络。"""

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services import assets, stocks
from wealthpilot.services.agents import tools
from wealthpilot.services.agents.planner_agent import PlannerAgent
from wealthpilot.services.lookthrough import aggregate_exposure


def holding(code, asset_type="fund", shares=100.0, name=None):
    return PortfolioHolding(user_id=0, asset_type=asset_type, fund_code=code, fund_name=name or code,
                            shares=shares, cost_price=1.0, buy_date=date(2025, 1, 1))


def kline(closes):
    """最新在前，与 fetch_stock_kline 的输出一致。"""
    return [{"fund_code": "X", "nav_date": f"2026-01-{i + 1:02d}", "nav": c, "daily_return": 0.0,
             "open": c, "high": c + 1, "low": c - 1, "volume": 1.0} for i, c in reversed(list(enumerate(closes)))]


@pytest.mark.parametrize("raw,expected", [
    ("600519", "sh600519"), ("000858", "sz000858"), ("600519.SH", "sh600519"),
    ("sz300750", "sz300750"), ("510300", "sh510300"), ("000001.sz", "sz000001"),
])
def test_market_symbol_normalizes_common_spellings(raw, expected):
    assert stocks.market_symbol(raw) == expected
    assert stocks.plain_code(raw) == expected[2:]


async def test_price_history_dispatches_by_asset_type(monkeypatch):
    fund = AsyncMock(return_value=["fund"])
    stock = AsyncMock(return_value=["stock"])
    monkeypatch.setattr(assets, "fetch_fund_nav", fund)
    monkeypatch.setattr(stocks, "fetch_stock_kline", stock)
    assert await assets.fetch_price_history("110011", "fund", 60) == ["fund"]
    assert await assets.fetch_price_history("600519", "stock", 60) == ["stock"]
    assert await assets.fetch_price_history("510300", "etf", 60) == ["stock"]
    assert await assets.fetch_price_history("BTC", "crypto", 60) == []


def test_kline_summary_reports_return_and_range_position():
    summary = stocks.summarize_kline(kline([100, 110, 90, 105]))
    assert summary["period_return_pct"] == 5.0
    assert summary["period_high"] == 111 and summary["period_low"] == 89
    assert summary["range_position_pct"] == pytest.approx((105 - 89) / (111 - 89) * 100, abs=0.1)
    assert summary["price_basis"] == "前复权收盘价"


async def test_stock_tools_say_so_when_data_is_missing(monkeypatch):
    monkeypatch.setattr(tools, "fetch_stock_quote", AsyncMock(return_value=None))
    monkeypatch.setattr(tools, "fetch_stock_financials", AsyncMock(return_value=[]))
    assert (await tools.execute_tool("get_stock_quote", {"code": "999999"}, [], {})).startswith("未获取到")
    assert (await tools.execute_tool("get_stock_financials", {"code": "999999"}, [], {})).startswith("未获取到")


async def test_valuation_labels_price_range_not_valuation_percentile(monkeypatch):
    quote = {"code": "600519", "name": "贵州茅台", "price": 105.0, "pe_ttm": 19.3, "pb": 6.3,
             "total_mv_yi": 15733.8, "quote_time": "2026-09-30 15:00"}
    monkeypatch.setattr(tools, "fetch_stock_quote", AsyncMock(return_value=quote))
    monkeypatch.setattr(tools, "fetch_stock_kline", AsyncMock(return_value=kline([100, 110, 90, 105])))
    out = json.loads(await tools.execute_tool("get_stock_valuation", {"code": "600519"}, [], {}))
    assert out["pe_ttm"] == 19.3 and "range_position_pct" in out["price_range_1y"]
    assert "不是估值分位" in out["note"]


async def test_return_and_backtest_use_holding_asset_type(monkeypatch):
    fetch = AsyncMock(return_value=kline([10.0] * 30))
    monkeypatch.setattr(tools, "fetch_price_history", fetch)
    mine = [holding("600519", "stock")]
    await tools.execute_tool("calculate_return", {"fund_code": "600519", "days": 21}, mine, {})
    assert fetch.await_args.args[1] == "stock"          # 持仓里是股票 → 走日线
    await tools.execute_tool("calculate_return", {"fund_code": "110011", "days": 21}, mine, {})
    assert fetch.await_args.args[1] == "fund"           # 不在持仓里 → 默认基金
    await tools.execute_tool("calculate_return", {"fund_code": "000858", "days": 21, "asset_type": "stock"}, mine, {})
    assert fetch.await_args.args[1] == "stock"          # 显式指定优先


def test_lookthrough_merges_direct_stock_with_fund_holdings():
    held = [holding("110011", "fund", 100, "某基金"), holding("600519", "stock", 100, "贵州茅台")]
    fund_data = {"110011": {"stocks": [{"stock_code": "600519", "stock_name": "贵州茅台", "weight_pct": 10.0}],
                            "report_date": "2026-06-30", "coverage_pct": 60.0}}
    out = aggregate_exposure(held, {"110011": 1.0, "600519": 1.0}, fund_data)
    maotai = next(s for s in out["stocks"] if s["stock_code"] == "600519")
    # 各占一半：直接 50% + 通过基金 50% × 10% = 5%
    assert maotai["direct_pct"] == 50.0 and maotai["exposure_pct"] == 55.0
    assert maotai in out["multi_fund_stocks"]            # 直接 + 间接算一次重叠
    assert out["total_fund_count"] == 1 and out["direct_stock_count"] == 1


def test_keyword_fallback_routes_stock_questions_to_stock_agent():
    offline = type("C", (), {"create": lambda self, **kw: (_ for _ in ()).throw(RuntimeError("offline"))})()
    plan = PlannerAgent(offline, "m").plan("贵州茅台现在市盈率多少，财报怎么样")
    assert plan.tasks[0].agent in ("fundamental", "valuation")


def test_grounding_accepts_unit_scaling_and_bare_evidence_ids():
    from wealthpilot.services.agents.base import AgentResult
    from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
    results = [AgentResult("stock", "g", "", [{"id": "E-cc066697d936", "tool": "t", "input": {}, "status": "ok",
                                               "output": '{"amount_wan": 479725.0, "revenue": 92278072083.21}'}])]
    answer = "成交额 47.97 亿元，营收 922.78 亿元，来源 E-cc066697d936"
    assert check_numeric_grounding(answer, results)["ungrounded"] == []
    assert check_numeric_grounding("成交额 52.3 亿元", results)["ungrounded"] == ["52.3"]


def test_restating_holdings_snapshot_and_decline_wording_is_grounded():
    from wealthpilot.services.agents.base import AgentResult
    from wealthpilot.services.agents.critic_agent import CriticAgent
    results = [AgentResult("stock", "g", "", [{"id": "E-aaaaaaaaaaaa", "tool": "t", "input": {}, "status": "ok",
                                               "output": '{"net_profit_yoy_pct": -1.95}'}])]
    context = "- 招商中证白酒指数A（161725）：8000.00份，成本0.9200，最新0.5314，收益率-42.24%"
    answer = "净利润同比下滑 1.95% [E-aaaaaaaaaaaa]。你持有的 161725 成本 0.9200、最新 0.5314，收益率 -42.24%。"
    verdict = CriticAgent(None, "m").review_answer(answer, results, "茅台怎么样", context)
    assert verdict.ungrounded_numbers == []
