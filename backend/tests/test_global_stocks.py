"""港股和美股：认代码、取数、研究计划跟着减、A 股独有的数据明说没有。全部用造的响应，不联网。"""

import asyncio
import json
import time

import pytest

from wealthpilot.services import global_stocks as g
from wealthpilot.services import securities, stocks
from wealthpilot.services import valuation_models as vm
from wealthpilot.services.agents import playbooks
from wealthpilot.services.agents.tools import execute_tool

HK_LINE = "~".join(["100", "腾讯控股", "00700", "419.000", "411.400", "415.000"] + ["0"] * 24 + ["2026/10/09 10:37:09", "7.600", "1.85", "421.400", "414.800", "0",
                    "6628920.0", "2772996459.250", "0", "15.30", "0", "0", "0", "1.60", "38098.0174", "38098.0174", "TENCENT", "1.27", "663.700", "411.000", "2.03", "-16.26"] + ["0"] * 23 + ["HKD", "1"])
US_LINE = "~".join(["200", "苹果", "AAPL.OQ", "340.42", "336.67", "336.82"] + ["0"] * 24 + ["2026-10-08 16:00:01", "3.75", "1.11", "341.57", "335.90", "0",
                    "35332449", "11989697641", "0.24", "39.04", "0", "0", "0", "1.68", "49650.62764", "49681.50756", "Apple Inc.", "8.72", "345.34", "242.76", "200", "46.21"] + ["0"] * 20)


def test_codes_from_three_markets_are_told_apart():
    assert [g.parse(c) for c in ("00700.HK", "hk700", "HK00700", "00700")] == [("hk", "00700")] * 4
    assert [g.parse(c) for c in ("AAPL", "aapl.us", "US.BABA", "usNVDA")] == [("us", "AAPL"), ("us", "AAPL"), ("us", "BABA"), ("us", "NVDA")]
    for a_share in ("600519", "sh600519", "600519.SH", "000858.sz", "110011", "", "  "):
        assert g.parse(a_share) is None, a_share
    assert g.canonical("hk700") == "00700.HK" and g.canonical("aapl") == "AAPL.US" and g.canonical("600519") == "600519"


def test_quotes_carry_their_currency_and_only_fields_we_are_sure_of():
    hk = g._quote_from(HK_LINE.split("~"), "hk", "00700")
    assert (hk["code"], hk["name"], hk["price"], hk["change_pct"], hk["pe_ttm"], hk["total_mv_yi"], hk["currency"]) == ("00700.HK", "腾讯控股", 419.0, 1.85, 15.3, 38098.0174, "港元")
    assert hk["high_52w"] == 663.7 and hk["pb"] is None and hk["quote_time"] == "2026-10-09 10:37"       # 港股的市净率字段拿不准：宁可不给
    us = g._quote_from(US_LINE.split("~"), "us", "AAPL")
    assert (us["code"], us["symbol"], us["currency"], us["pb"], us["turnover_pct"]) == ("AAPL.US", "usAAPL.OQ", "美元", 46.21, 0.24)
    assert g._quote_from(["", ""], "hk", "00700") is None


async def test_existing_functions_route_overseas_codes_and_refuse_a_share_only_data(monkeypatch):
    seen = []

    async def quote(code):
        seen.append(("quote", code))
        return {**g._quote_from(HK_LINE.split("~"), "hk", "00700")}

    async def kline(code, days=60):
        seen.append(("kline", code))
        return [{"fund_code": "00700.HK", "nav_date": f"2026-09-{d:02d}", "nav": 400.0 + d, "daily_return": 0.1, "open": 1, "high": 2, "low": 0.5, "volume": 9, "price_basis": "前复权"} for d in range(30, 0, -1)]

    async def indicators(code, periods=8):
        seen.append(("fin", code))
        return [{"report_date": "2025-12-31", "report_name": "2025年年报", "annual": True, "currency": "人民币", "net_profit_yi": 2200.0, "revenue_yi": 7000.0}]
    monkeypatch.setattr(g, "fetch_quote", quote)
    monkeypatch.setattr(g, "fetch_kline", kline)
    monkeypatch.setattr(g, "fetch_indicators", indicators)
    assert (await stocks.fetch_stock_quote("hk700"))["currency"] == "港元" and len(await stocks.fetch_stock_kline("00700.HK", 30)) == 30
    assert (await stocks.fetch_financial_indicators("00700.HK", 4))[0]["annual"] is True
    valuation = json.loads(await execute_tool("get_stock_valuation", {"code": "hk00700"}, [], {}))
    assert valuation["code"] == "00700.HK" and valuation["currency"] == "港元" and valuation["market"] == "港股" and "price_range_1y" in valuation
    for a_only in ("get_capital_flow", "get_valuation_history", "compare_peers_valuation", "get_margin_trading", "get_consensus_forecast", "read_latest_report"):
        said = await execute_tool(a_only, {"code": "00700.HK"}, [], {})
        assert said.startswith("未获取到 00700.HK") and "只覆盖 A 股" in said and "联网搜索" in said, a_only
    dcf = json.loads(await execute_tool("compute_reverse_dcf", {"code": "00700.HK"}, [], {}))
    assert dcf["ok"] and dcf["currency"] == "港元" and dcf["profit_period"] == "按滚动市盈率倒推的近四个季度" and dcf["pe_ttm"] == 15.3
    assert dcf["profit_ttm_yi"] == pytest.approx(38098.0174 / 15.3, abs=0.01)                  # 利润由市值和市盈率倒出来，不拿人民币的财报去除港元的市值


def test_overseas_reverse_dcf_handles_losses_and_odd_fiscal_years():
    rows = [{"report_date": d, "annual": True, "net_profit_yi": v} for d, v in (("2025-09-27", 1120.0), ("2024-09-28", 937.0), ("2023-09-30", 970.0), ("2022-09-24", 998.0))]
    assert vm.annual_cagr(rows) == pytest.approx((1120 / 998) ** (1 / 3) - 1)                  # 财年不在 12 月底也认得出年报
    out = vm.reverse_dcf(49681.5, rows, name="苹果", pe_ttm=39.04, currency="美元")
    assert out["ok"] and out["currency"] == "美元" and out["implied_growth"][1]["growth_pct"] > out["past_profit_cagr_3y_pct"]
    assert vm.reverse_dcf(1000, rows, pe_ttm=-8.0)["ok"] is False and "亏损" in vm.reverse_dcf(1000, rows, pe_ttm=0)["reason"]


def test_overseas_research_drops_what_cannot_be_evidenced():
    hk = {"code": "00700.HK", "name": "腾讯控股", "asset_type": "stock", "market": "hk"}
    cn = {"code": "600519", "name": "贵州茅台", "asset_type": "stock", "market": "cn"}
    tasks = playbooks.build_tasks("stock_deep", [hk], [], {}, "帮我分析一下腾讯")
    assert [t.agent for t in tasks] == ["fundamental", "valuation", "price", "expectation"]              # 没有资金与筹码、行业对比这两路
    assert "compute_reverse_dcf" in tasks[1].goal and "不要凭印象" in tasks[1].goal and "港股" in tasks[0].goal and "web_search" in tasks[3].goal
    book = playbooks.book_for("stock_deep", [hk])
    assert "资金" not in book.sections and "行业" not in book.sections and book.key == "stock_deep"      # 还是同一类研究，只是章节减了
    assert all(c in playbooks.CRITERIA_TOOLS for c in book.criteria)                                    # 每条证据要求都有工具能满足，不会被判"证据不足"
    assert len(playbooks.build_tasks("stock_deep", [cn], [], {}, "分析茅台")) == 6 and "资金" in playbooks.book_for("stock_deep", [cn]).sections
    mixed = playbooks.build_tasks("stock_compare", [cn, hk], [], {}, "对比")
    assert [t.id for t in mixed] == ["s1_fundamental", "s1_valuation", "s2_fundamental", "s2_valuation"] and "历史分位" not in mixed[3].goal.replace("没有估值历史分位", "")
    assert playbooks.book_for("stock_compare", [cn, hk]).criteria[1] == "每只股票的市盈率与现价隐含的增长"


async def test_search_and_question_parsing_find_overseas_stocks(monkeypatch):
    import httpx
    table = [{"Code": "00700", "Name": "腾讯控股", "Classify": "HK", "SecurityTypeName": "港股"}, {"Code": "80700", "Name": "腾讯控股-R", "Classify": "HK"},
             {"Code": "13005", "Name": "腾讯法兴七三购A", "Classify": "HK"}, {"Code": "TME", "Name": "腾讯音乐", "Classify": "UsStock"},
             {"Code": "AAPL22", "Name": "Apple Inc Notes 2022", "Classify": "UsStock"}, {"Code": "600519", "Name": "贵州茅台", "Classify": "AStock", "SecurityTypeName": "沪A"}]

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return httpx.Response(200, json={"QuotationCodeTable": {"Data": table}})
    monkeypatch.setattr(securities.httpx, "AsyncClient", Client)
    hits = await securities.search("腾讯", 8)
    assert [(h["code"], h["market"]) for h in hits] == [("00700.HK", "hk"), ("TME.US", "us"), ("600519", "cn")]       # 人民币柜台、窝轮、债券都滤掉了

    async def quotes(codes):
        return {c: {"name": {"00700.HK": "腾讯控股", "AAPL.US": "苹果"}[c], "market": c[-2:].lower()} for c in codes if c in ("00700.HK", "AAPL.US")}

    async def empty_snapshot():
        return {"stocks": []}
    monkeypatch.setattr(g, "fetch_quotes", quotes)
    monkeypatch.setattr(securities, "snapshot", empty_snapshot)
    found = await securities.resolve_text("对比一下 00700.HK 和 $AAPL，PE 和 ROE 哪个更好")
    assert {s["code"] for s in found} == {"00700.HK", "AAPL.US"}                               # PE、ROE 这种大写缩写不会被当成美股代码


def test_overseas_stocks_cannot_be_booked_as_holdings_yet():
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    resp = TestClient(app).post("/api/portfolio", json={"fund_code": "00700.HK", "fund_name": "腾讯控股", "shares": 100, "cost_price": 400, "asset_type": "stock", "buy_date": "2026-01-05"})
    assert resp.status_code == 422 and "汇率折算还没做" in resp.json()["detail"]


async def test_eastmoney_requests_are_spaced_and_capped(monkeypatch):
    """六个 Agent 并行时，打向东方财富数据中心的请求要排队：同时不超过几个，前后隔开一小段。"""
    import httpx
    starts, live, peak = [], 0, 0

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            nonlocal live, peak
            starts.append(time.monotonic())
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1
            return httpx.Response(200, json={"result": {"data": [{"x": 1}], "pages": 1}})
    monkeypatch.setattr(stocks.httpx, "AsyncClient", Client)
    monkeypatch.setattr(stocks, "EM_MIN_INTERVAL", 0.02)
    results = await asyncio.gather(*(stocks.datacenter("RPT_X") for _ in range(12)))
    assert all(rows == [{"x": 1}] for rows, _ in results)
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    assert peak <= stocks.EM_MAX_CONCURRENT and min(gaps) >= 0.015                            # 没有一窝蜂打出去
