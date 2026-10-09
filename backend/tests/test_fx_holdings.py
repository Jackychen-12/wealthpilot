"""港股美股记进持仓（按人民币记账）、官方的两融和汇率、宏观与港美股行情的备用、点名对比。全部用假的网络，不联网。"""

import json
from datetime import date

import httpx
import pytest
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services import assets, cache, capital, fx, macro, sources, stocks
from wealthpilot.services import global_stocks as g
from wealthpilot.services.sources import SourceError
from wealthpilot.storage.db import get_engine

REAL_CLIENT = httpx.AsyncClient


def net(monkeypatch, handler):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: REAL_CLIENT(*a, **{**k, "transport": httpx.MockTransport(handler)}))


@pytest.fixture(autouse=True)
def _clean():
    sources.reset()
    yield
    sources.reset()
    with Session(get_engine()) as db:
        for row in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id.in_([0, 31]))).all():
            if row.currency != "CNY":
                db.delete(row)
        db.commit()


@pytest.fixture
def rates(monkeypatch):
    """汇率固定下来：港元 0.86，美元 7；买入日（过去）的港元是 0.90。"""
    async def rate(currency, on=None):
        if currency == "CNY":
            return {"currency": "CNY", "rate": 1.0, "date": "", "source": ""}
        value = {"HKD": 0.90 if on and on < date.today() else 0.86, "USD": 7.0}[currency]
        return {"currency": currency, "rate": value, "date": str(on or date.today()), "source": "测试"}
    monkeypatch.setattr(fx, "rate", rate)


# ── 汇率 ─────────────────────────────────────────────────

async def test_the_central_parity_rate_is_read_for_today_and_for_a_past_day(monkeypatch):
    asked = []

    def handler(request):
        asked.append(dict(request.url.params))
        return httpx.Response(200, json={"data": {"searchlist": ["USD/CNY", "HKD/CNY"]}, "records": [
            {"date": "2026-09-30", "values": ["6.7351", "0.85842"]}, {"date": "2026-10-08", "values": ["6.7367", "0.85849"]}]})
    hkd = await fx._chinamoney("HKD", date(2026, 10, 9), httpx.MockTransport(handler))
    assert hkd == {"currency": "HKD", "rate": 0.85849, "date": "2026-10-08", "source": "中国货币网（人民币汇率中间价）"}      # 那天没公布：用之前最近的一个工作日
    assert asked[0]["currency"] == "HKD/CNY" and asked[0]["endDate"] == "2026-10-09" and asked[0]["startDate"] == "2026-09-27"
    assert (await fx._chinamoney("USD", None, httpx.MockTransport(handler)))["rate"] == 6.7367
    empty = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {"searchlist": ["USD/CNY"]}, "records": []}))
    assert await fx._chinamoney("USD", date(1990, 1, 1), empty) is None
    with pytest.raises(SourceError, match="没有 HKD/CNY"):
        await fx._chinamoney("HKD", None, empty)
    with pytest.raises(SourceError):
        await fx._chinamoney("HKD", None, httpx.MockTransport(lambda r: httpx.Response(200, text="<html>")))
    sina = httpx.MockTransport(lambda r: httpx.Response(200, content='var hq_str_fx_shkdcny="16:55:58,0.8528,0.8529,0.85,1";'.encode("gbk")))
    assert (await fx._sina("HKD", sina))["rate"] == 0.8528 and "不是中间价" in (await fx._sina("HKD", sina))["source"]
    with pytest.raises(SourceError, match="不像汇率"):
        await fx._sina("USD", httpx.MockTransport(lambda r: httpx.Response(200, content=b'var hq_str_fx_susdcny="16:55:58,0,0";')))

    async def down(*a, **k):
        raise SourceError("连不上")

    async def instant(currency, transport=None):
        return {"currency": currency, "rate": 0.85, "date": "2026-10-09", "source": "新浪"}
    monkeypatch.setattr(fx, "_chinamoney", down)
    monkeypatch.setattr(fx, "_sina", instant)
    assert (await fx.rate("HKD"))["rate"] == 0.85                                   # 最新的：官方不通时即时汇率顶上
    assert await fx.rate("HKD", date(2024, 3, 8)) is None                          # 过去某一天的：即时汇率顶不了，就是没有
    assert (await fx.rate("CNY"))["rate"] == 1.0 and await fx.rate("JPY") is None
    assert fx.currency_of("hk700") == "HKD" and fx.currency_of("AAPL.US") == "USD" and fx.currency_of("600519") == "CNY"
    booked = await fx.book("00700.HK", 400, date(2024, 3, 8))
    assert booked["cost_fx"] == 0.85 and booked["cost_price"] == 340.0             # 买入日的取不到：退到最新的，用了哪个汇率照样记着

    async def nothing(currency, transport=None):
        return None
    monkeypatch.setattr(fx, "_sina", nothing)
    with pytest.raises(SourceError, match="先记不了"):                              # 两边都没有：宁可不记，也不记一笔币种不明的账
        await fx.book("00700.HK", 400, date(2024, 3, 8))
    assert await fx.book("600519", 1500, date(2024, 3, 8)) == {"code": "600519", "currency": "CNY", "cost_price": 1500, "cost_native": None, "cost_fx": None}


# ── 港股美股记进持仓 ─────────────────────────────────────

async def test_overseas_holdings_are_booked_in_renminbi_and_valued_at_todays_rate(rates, monkeypatch):
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    from wealthpilot.services import context

    async def quotes(codes):
        return {c: {"price": {"00700.HK": 500.0, "AAPL.US": 300.0, "600519": 1263.0}[c], "change_pct": 1.0, "name": c} for c in codes}
    monkeypatch.setattr(assets, "fetch_sina_quotes", quotes)
    client = TestClient(app)
    made = client.post("/api/portfolio", json={"fund_code": "hk700", "fund_name": "腾讯控股", "shares": 100, "cost_price": 400, "asset_type": "stock", "buy_date": "2026-01-05"})
    assert made.status_code == 201
    body = made.json()
    assert (body["fund_code"], body["currency"], body["cost_native"], body["cost_fx"], body["cost_price"]) == ("00700.HK", "HKD", 400, 0.90, 360.0)   # 成本按买入日的汇率折
    listed = next(h for h in client.get("/api/portfolio").json() if h["fund_code"] == "00700.HK")
    assert listed["latest_nav"] == 430.0 and listed["native_price"] == 500.0 and listed["fx_rate"] == 0.86            # 现价按今天的汇率折
    assert listed["market_value"] == 43000.0 and listed["total_return"] == 7000.0 and listed["return_pct"] == pytest.approx(19.44, abs=0.01)
    # 股价涨了 25%，港元贬了 4.4%：人民币账上赚 19.4%，汇率的涨跌算在里面
    same = client.put(f"/api/portfolio/{body['id']}", json={"shares": 200, "cost_price": 400}).json()
    assert same["shares"] == 200 and same["cost_price"] == 360.0                    # 只改了股数：人民币成本不动
    changed = client.put(f"/api/portfolio/{body['id']}", json={"cost_price": 420}).json()
    assert changed["cost_native"] == 420 and changed["cost_price"] == 378.0         # 改了成本：填的还是港元，重新折一次

    prices = await assets.fetch_prices_by_type([("00700.HK", "stock"), ("AAPL.US", "stock"), ("600519", "stock")])
    assert prices == {"00700.HK": 430.0, "AAPL.US": 2100.0, "600519": 1263.0}

    async def history(code, asset_type, days):
        return [{"nav_date": "2026-10-09", "nav": 500.0, "daily_return": 1.0}, {"nav_date": "2026-10-08", "nav": 495.0, "daily_return": 0.0}]
    monkeypatch.setattr(context, "fetch_price_history", history)
    with Session(get_engine()) as db:
        held = [h for h in db.exec(select(PortfolioHolding)).all() if h.fund_code == "00700.HK"]
    nav, hist = await context.load_market_context(held)
    assert nav["00700.HK"] == 430.0 and [r["nav"] for r in hist["00700.HK"]] == [430.0, 425.7] and hist["00700.HK"][0]["daily_return"] == 1.0   # 历史价也折成人民币，涨跌幅不变

    async def no_rate(currency, on=None):
        return {"currency": "CNY", "rate": 1.0, "date": "", "source": ""} if currency == "CNY" else None
    monkeypatch.setattr(fx, "rate", no_rate)
    assert await assets.fetch_prices_by_type([("00700.HK", "stock"), ("600519", "stock")]) == {"600519": 1263.0}      # 取不到汇率：不拿港元的数混进人民币的账
    refused = client.post("/api/portfolio", json={"fund_code": "AAPL.US", "fund_name": "苹果", "shares": 10, "cost_price": 300, "asset_type": "stock", "buy_date": "2026-01-05"})
    assert refused.status_code == 503 and "取不到USD兑人民币的汇率" in refused.json()["detail"]
    coin = client.post("/api/portfolio", json={"fund_code": "BTC", "fund_name": "比特币", "shares": 0.1, "cost_price": 400000, "asset_type": "crypto", "buy_date": "2026-01-05"})
    assert coin.status_code == 201 and coin.json()["currency"] == "CNY" and coin.json()["fund_code"] == "BTC"      # 长得像美股代码，但它是加密货币：不折算
    client.delete(f"/api/portfolio/{coin.json()['id']}")


async def test_pasted_holdings_and_the_home_desk_handle_overseas_stocks(rates, monkeypatch):
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    from wealthpilot.routes import onboarding, research
    from wealthpilot.services import securities

    async def search(query, limit=10, **kw):
        return [{"code": "00700.HK", "name": "腾讯控股", "asset_type": "stock", "market": "hk"}] if "腾讯" in query else []

    async def profile(code):
        return {"industry": "互联网"}
    monkeypatch.setattr(securities, "search", search)
    monkeypatch.setattr(onboarding, "fetch_stock_profile", profile)
    client = TestClient(app)
    preview = client.post("/api/portfolio/parse", json={"text": "腾讯 100 400"}).json()["rows"][0]
    assert preview["ok"] and preview["code"] == "00700.HK" and "按港元填" in preview["note"]
    added = client.post("/api/portfolio/batch", json={"rows": [{"code": "00700.HK", "name": "腾讯控股", "shares": 100, "cost": 400, "asset_type": "stock"}, {"code": "bad", "shares": 1, "cost": 1}]}).json()
    assert added["added"] == 1 and len(added["skipped"]) == 1
    with Session(get_engine()) as db:
        row = next(h for h in db.exec(select(PortfolioHolding)).all() if h.fund_code == "00700.HK")
        assert (row.currency, row.cost_native, row.cost_price, row.industry) == ("HKD", 400, 344.0, "互联网")       # 粘贴导入没有买入日：按今天的汇率

    async def quotes(codes):
        return {c: {"price": 500.0, "change_pct": 2.0} for c in codes}
    monkeypatch.setattr(research, "fetch_sina_quotes", quotes)
    stock = next(s for s in client.get("/api/desk").json()["stocks"] if s["code"] == "00700.HK")
    assert stock["price"] == 500.0 and stock["currency"] == "HKD" and stock["market_value"] == 43000.0 and stock["return_pct"] == 25.0   # 现价给港元，市值和收益是人民币账上的


# ── 两融：东方财富 → 交易所 ──────────────────────────────

async def test_margin_data_falls_back_to_the_exchanges_own_tables(monkeypatch):
    def handler(request):
        url = str(request.url)
        if "datacenter-web" in url:
            return httpx.Response(503)
        if "sse.com.cn" in url:
            assert request.url.params["stockCode"] == "600519" and request.url.params["beginDate"] < request.url.params["endDate"]
            return httpx.Response(200, json={"pageHelp": {"data": [
                {"opDate": "20261007", "rzye": 17200000000, "rzmre": 200000000, "rzche": 150000000, "rqylje": None},
                {"opDate": "20261008", "rzye": 17229986025, "rzmre": 195982276, "rzche": 199517782, "rqylje": 258000000}]}})
        day = request.url.params["txtDate"]
        rows = [] if day == "2026-10-06" else [{"zqdm": "000001", "jrrzmr": "1.08", "jrrzye": "44.43", "jrrjye": "18,681.00"}]
        return httpx.Response(200, json=[{"metadata": {"tabkey": "tab1"}, "data": []}, {"metadata": {"tabkey": "tab2"}, "data": rows}])

    async def bars(code, days):
        return [{"nav_date": d} for d in ("2026-10-09", "2026-10-08", "2026-10-07", "2026-10-06")]
    net(monkeypatch, handler)
    monkeypatch.setattr(capital, "fetch_stock_kline", bars)
    sh = await capital.fetch_margin("600519", 30)
    assert sh[0] == {"date": "2026-10-08", "close": None, "financing_balance_yi": 172.3, "financing_buy_yi": 1.96, "financing_net_buy_yi": -0.04,
                     "short_balance_yi": 2.58, "financing_to_float_mv_pct": None, "source": "上海证券交易所"} and len(sh) == 2
    sz = await capital.fetch_margin("000001", 30)
    assert [r["date"] for r in sz] == ["2026-10-08", "2026-10-07"]                 # 当天的第二天才公布，从上一个交易日起；没数据的那天跳过
    assert sz[0]["financing_balance_yi"] == 44.43 and sz[0]["short_balance_yi"] == 1.8681 and sz[0]["source"] == "深圳证券交易所"
    assert {s["name"]: s["status"] for s in sources.health()}["exchange"] == "ok" and sources.SOURCES["exchange"]["official"]
    assert await capital.fetch_margin("830799", 30) == []                          # 北交所：没有备用
    net(monkeypatch, lambda r: httpx.Response(200, json={"pageHelp": {"data": [{"x": 1}]}}))
    with pytest.raises(SourceError, match="字段变了"):
        await capital._margin_sse("600519", 5)


# ── 宏观：东方财富 → 新浪 ────────────────────────────────

def sina_table(rows):
    return ('x(({config:{all:[[0,"统计月份"]]},querylist:[{title:"时间段",data:[["2026.9","2026.9",true]]}],count:"261",data:' + json.dumps(rows) + "}));").encode("gbk")


async def test_macro_series_fall_back_to_sina_where_it_still_publishes(monkeypatch):
    this_year = date.today().year
    tables = {"boom": [[f"{this_year}.9", "50.10", "51.70"], [f"{this_year}.8", "49.80", "50.40"]], "price": [[f"{this_year}.8", "100.80"], [f"{this_year}.7", "100.50"]],
              "fininfo": [[f"{this_year}.8", "3568083.60", "7.50", "1157741.43", "4.10"]], "nation": [[f"{this_year}.2", "695704.00", "4.70"], [f"{this_year}.1", "334192.90", "5.00"]]}

    def transport(cate):
        return httpx.MockTransport(lambda r: httpx.Response(200, content=sina_table(tables[r.url.params["cate"]])) if r.url.params["cate"] == cate else httpx.Response(500))
    pmi = await macro._sina_macro("RPT_ECONOMY_PMI", transport("boom"))
    assert pmi == [{"REPORT_DATE": f"{this_year}-09-01", "source": "新浪财经（备用源）", "MAKE_INDEX": 50.1}, {"REPORT_DATE": f"{this_year}-08-01", "source": "新浪财经（备用源）", "MAKE_INDEX": 49.8}]
    assert (await macro._sina_macro("RPT_ECONOMY_CPI", transport("price")))[0]["NATIONAL_SAME"] == 0.8             # 它给的是指数，减 100 才是同比
    money = (await macro._sina_macro("RPT_ECONOMY_CURRENCY_SUPPLY", transport("fininfo")))[0]
    assert (money["BASIC_CURRENCY_SAME"], money["CURRENCY_SAME"]) == (7.5, 4.1)
    gdp = await macro._sina_macro("RPT_ECONOMY_GDP", transport("nation"))
    assert [r["REPORT_DATE"] for r in gdp] == [f"{this_year}-06-01", f"{this_year}-03-01"] and gdp[0]["SUM_SAME"] == 4.7          # 2026.2 是二季度
    with pytest.raises(SourceError, match="不再更新"):                                # 它有几项停在好几年前：认出来，不拿旧数顶
        await macro._sina_macro("RPT_ECONOMY_PMI", httpx.MockTransport(lambda r: httpx.Response(200, content=sina_table([["2019.10", "52.80"]]))))
    with pytest.raises(SourceError):
        await macro._sina_macro("RPT_ECONOMY_PMI", httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>")))

    async def dead(*a, strict=False, **k):
        if strict:
            raise SourceError("连不上")
        return [], 0

    async def backup(report, transport=None):
        return [{"REPORT_DATE": "2026-09-01", "MAKE_INDEX": 50.1}]
    monkeypatch.setattr(macro, "datacenter", dead)
    monkeypatch.setattr(macro, "_sina_macro", backup)
    assert (await macro._macro_rows("RPT_ECONOMY_PMI"))[0]["MAKE_INDEX"] == 50.1 and await macro._macro_rows("RPT_ECONOMY_PPI") == []   # PPI 没有备用：就是没有


# ── 港美股行情和日线的备用 ───────────────────────────────

HK = "TENCENT,腾讯控股,415.000,411.400,425.800,414.800,424.800,13.400,3.257,424.800,425.000,8610387928.730,20422500,15.433,0.000,661.295,411.000,2026/10/09,16:08:14,100|0"
US = "苹果,340.4200,1.11,2026-10-09 17:11:31,3.7500,336.8150,341.5700,335.9000,345.3400,242.8900,35332449,35520491,4968257866370,8.30,41.010000," + ",".join(["0"] * 11) + ",336.6700,401973,1,2026,11993662716.9897"


async def test_overseas_quotes_and_us_bars_have_a_backup_and_say_what_it_lacks(caching_on, monkeypatch):
    def handler(request):
        url = str(request.url)
        if "qt.gtimg.cn" in url:
            return httpx.Response(501, text="<html>waf</html>")
        if "hq.sinajs.cn" in url:
            return httpx.Response(200, content=f'var hq_str_rt_hk00700="{HK}";\nvar hq_str_gb_aapl="{US}";\nvar hq_str_gb_zzzzq="";'.encode("gbk"))
        if "US_MinKService" in url:
            return httpx.Response(200, text='/*x*/\nvar x=([{"d":"2026-10-07","o":"336.96","h":"338.67","l":"332.78","c":"336.67","v":"34147860"},{"d":"2026-10-08","o":"336.81","h":"341.57","l":"335.90","c":"340.42","v":"35332449"}]);')
        return httpx.Response(501, text="<html>waf</html>")
    net(monkeypatch, handler)
    quotes = await g.fetch_quotes(["hk700", "AAPL", "ZZZZQ.US"])
    hk, us = quotes["00700.HK"], quotes["AAPL.US"]
    assert (hk["price"], hk["prev_close"], hk["change_pct"], hk["amount_yi"], hk["quote_time"], hk["currency"]) == (424.8, 411.4, 3.257, 86.1, "2026-10-09 16:08", "港元")
    assert (us["price"], us["prev_close"], us["total_mv_yi"], us["amount_yi"]) == (340.42, 336.67, 49682.58, 119.94) and "ZZZZQ.US" not in quotes
    assert hk["pe_ttm"] is None and us["pe_ttm"] is None and "没有市盈率" in us["source"] and hk["total_mv_yi"] is None       # 两家口径不同的、没有的：留空
    assert {s["name"]: s["status"] for s in sources.health()}["tencent"] == "failing"
    bars = await g.fetch_kline("AAPL.US", 5)
    assert [(b["nav_date"], b["nav"], b["price_basis"]) for b in bars] == [("2026-10-08", 340.42, "不复权"), ("2026-10-07", 336.67, "不复权")] and bars[0]["daily_return"] == 1.11
    assert await g.fetch_kline("00700.HK", 5) == []                                 # 港股日线只有腾讯：它不通又没有旧的，就是没有
    assert cache.read("global:tencent-symbol:AAPL", cache.DAY) is None              # 新浪给的代码没有交易所后缀，不能记下来拿去问腾讯
    net(monkeypatch, lambda r: httpx.Response(200, content=b'var hq_str_gb_aapl="a,b,c";'))
    with pytest.raises(SourceError, match="字段数变了"):
        await g._sina_quotes({"usAAPL": ("us", "AAPL")})


@pytest.fixture
def caching_on(monkeypatch):
    monkeypatch.delenv("WEALTHPILOT_NO_FETCH_CACHE", raising=False)
    for key in ("quote:hk00700", "quote:usAAPL", "kline:usAAPL:5", "kline:hk00700:5", "global:tencent-symbol:AAPL", "dividends:600887:8"):
        cache.write(key, None)


# ── 变化慢的数据留得久 ───────────────────────────────────

async def test_slow_changing_data_is_kept_for_a_reporting_period(caching_on, monkeypatch):
    from tests.test_sources import age
    up = True

    async def datacenter(report, **kw):
        if not up:
            return [], 0
        return [{"REPORT_DATE": "2025-12-31", "IMPL_PLAN_PROFILE": "10派276.24元", "PRETAX_BONUS_RMB": 276.24, "EX_DIVIDEND_DATE": "2026-06-20"}], 1
    monkeypatch.setattr(stocks, "datacenter", datacenter)
    first = await stocks.fetch_dividends("600887")
    assert first[0]["plan"] == "10派276.24元"
    up = False
    age("dividends:600887:8", 100 * cache.DAY)
    notes = cache.collect_stale()
    assert await stocks.fetch_dividends("600887") == first and "600887 的分红记录" in notes[0]          # 断了一百天：上一期的分红还是那一期
    age("dividends:600887:8", 100 * cache.DAY)
    assert await stocks.fetch_dividends("600887") == []                                                # 超过五个月：不再拿出来
    assert stocks.SLOW == 150 * cache.DAY


# ── 点名对比 ─────────────────────────────────────────────

async def test_named_stocks_are_compared_across_markets_with_caveats(monkeypatch):
    from wealthpilot.services.agents import depth_tools, tools

    async def quote(code):
        return {"00700.HK": {"name": "腾讯控股", "price": 424.8, "currency": "港元", "total_mv_yi": 38625.4, "pe_ttm": 15.52, "pb": None},
                "META.US": {"name": "Meta", "price": 720.9, "currency": "美元", "total_mv_yi": 18364.7, "pe_ttm": 27.15, "pb": 7.03},
                "600519": {"name": "贵州茅台", "price": 1263.0, "total_mv_yi": 15788.5, "pe_ttm": 19.39, "pb": 6.28}}.get(code)

    async def indicators(code, periods=8):
        return [{"report_name": "2026中报", "revenue_yoy_pct": 10.0, "net_profit_yoy_pct": 12.0, "roe_pct": 9.9, "gross_margin_pct": 57.0, "net_margin_pct": 29.0, "debt_ratio_pct": 43.0,
                 **({"currency": "美元"} if code == "META.US" else {})}]

    async def valuation(code, years=5):
        return [{"date": f"2026-{m:02d}-{d:02d}", "pe_ttm": 10 + m, "pb": 2.0 + m / 10, "ps_ttm": None} for m in range(9, 0, -1) for d in (25, 15, 5)]
    monkeypatch.setattr(depth_tools, "fetch_stock_quote", quote)
    monkeypatch.setattr(depth_tools, "fetch_financial_indicators", indicators)
    monkeypatch.setattr(stocks, "fetch_valuation_history", valuation)
    out = json.loads(await tools.execute_tool("compare_stocks", {"codes": ["hk700", "META.US", "sh600519", "NOPE.US", "hk700"]}, [], {}))
    assert [s["code"] for s in out["stocks"]] == ["00700.HK", "META.US", "600519"] and out["not_found"] == ["NOPE.US"]      # 重复的只算一次，没取到的单独列
    hk = out["stocks"][0]
    assert (hk["market"], hk["price_currency"], hk["pe_ttm"], hk["pb"], hk["pe_percentile_5y"], hk["revenue_yoy_pct"]) == ("港股", "港元", 15.52, 2.9, 100.0, 10.0)
    assert out["stocks"][1]["report_currency"] == "美元" and out["stocks"][2]["market"] == "A 股" and out["stocks"][2]["price_currency"] == "人民币"
    assert "点名的" in out["note"] and "不同货币不能直接比大小" in out["note"]
    assert "至少要两只" in await tools.execute_tool("compare_stocks", {"codes": ["600519"]}, [], {})
    assert "未获取到足够的数据" in await tools.execute_tool("compare_stocks", {"codes": ["NOPE.US", "600519"]}, [], {})
    assert json.loads(await tools.execute_tool("compare_stocks", {"codes": "600519、META.US"}, [], {}))["stocks"][0]["code"] == "600519"    # 写成一句话也认
    names = {t["name"] for t in tools.AGENT_TOOLS["valuation"]}
    assert "compare_stocks" in names and "compare_stocks" in {t["name"] for t in tools.AGENT_TOOLS["industry"]}
