"""数据源会断是常态：主来源不通换备用的，都不通用上一次取到的并标明日期，哪一路坏了看得见。全部用假的网络，不联网。"""

import asyncio
import json
from datetime import date

import httpx
import pytest
from sqlmodel import Session

from wealthpilot.models.research import DataCache
from wealthpilot.services import cache, macro, sources, stocks
from wealthpilot.services.sources import SourceError
from wealthpilot.storage.db import get_engine


@pytest.fixture(autouse=True)
def _clean():
    sources.reset()
    yield
    sources.reset()


@pytest.fixture
def caching(monkeypatch):
    """打开取数层的缓存（别的测试里是关着的），并保证每个测试用自己的 key。"""
    monkeypatch.delenv("WEALTHPILOT_NO_FETCH_CACHE", raising=False)


REAL_CLIENT = httpx.AsyncClient


def net(monkeypatch, handler):
    """让模块里新建的 httpx 客户端都走这个假的网络。一个测试里可以换好几次。"""
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: REAL_CLIENT(*a, **{**k, "transport": httpx.MockTransport(handler)}))


def age(key: str, seconds: float) -> None:
    with Session(get_engine()) as db:
        row = db.get(DataCache, key)
        row.fetched_at -= seconds
        db.add(row)
        db.commit()


# ── 成败记录与跳过 ──────────────────────────────────────

async def test_a_source_is_skipped_after_two_failures_and_comes_back_on_success():
    sources.fail("tencent", SourceError("超时"))
    assert not sources.is_down("tencent")                       # 一次抖动不切换
    sources.fail("tencent", "又超时")
    assert sources.is_down("tencent")
    by_name = {s["name"]: s for s in sources.health()}
    assert by_name["tencent"]["status"] == "failing" and "又超时" in by_name["tencent"]["error"] and by_name["tencent"]["failing_since"]
    assert by_name["cninfo"]["status"] == "unknown" and by_name["cninfo"]["official"] and not by_name["tencent"]["official"]
    quote = next(d for d in sources.overview()["datasets"] if d["key"] == "quote")
    assert quote["state"] == "fallback" and [c["label"] for c in quote["chain"]] == ["腾讯财经", "新浪财经"]
    sources.fail("sina", "x")
    assert next(d for d in sources.overview()["datasets"] if d["key"] == "quote")["state"] == "down"
    report = sources.overview()
    assert any("A 股实时行情现在取不到" in p for p in sources.problems(report))
    sources.ok("tencent")
    assert not sources.is_down("tencent") and {s["name"]: s for s in sources.health()}["tencent"]["status"] == "ok"
    assert next(d for d in sources.overview()["datasets"] if d["key"] == "quote")["state"] == "ok"


async def test_the_chain_moves_on_when_a_source_errors_or_has_nothing():
    calls = []

    def source(name, result):
        async def call():
            calls.append(name)
            if isinstance(result, Exception):
                raise result
            return result
        return name, call
    assert await sources.first([source("eastmoney", SourceError("改版了")), source("sina", [1])]) == ([1], "sina")
    assert {s["name"]: s["status"] for s in sources.health()}["eastmoney"] == "failing"
    calls.clear()
    assert await sources.first([source("baidu", []), source("cninfo", {"a": 1})]) == ({"a": 1}, "cninfo")       # 空的不算失败，只是接着问
    assert {s["name"]: s["status"] for s in sources.health()}["baidu"] == "ok"
    sources.fail("eastmoney", "x")                                   # 第二次失败：开始跳过
    calls.clear()
    await sources.first([source("eastmoney", [0]), source("sina", [1])])
    assert calls == ["sina"]
    sources.fail("sina", "x")
    sources.fail("sina", "x")
    calls.clear()
    assert (await sources.first([source("eastmoney", [0]), source("sina", [1])]))[1] == "eastmoney" and calls == ["eastmoney"]   # 全在跳过：总得有人去试
    assert await sources.first([source("pbc", SourceError("x")), source("mofcom", [])]) == (None, "")


# ── 取不到时用上一次的 ──────────────────────────────────

async def test_the_last_good_copy_is_served_with_its_date_when_everything_fails(caching):
    hits = []

    async def good():
        hits.append(1)
        return {"price": 10}

    async def dead():
        hits.append(0)
        raise RuntimeError("连不上")

    async def empty():
        return []
    assert await cache.resilient("t:quote:a", 60, good) == {"price": 10} and await cache.resilient("t:quote:a", 60, dead) == {"price": 10}
    assert hits == [1]                                                # 有效期内不再去取
    age("t:quote:a", 3600)
    notes = cache.collect_stale()
    served = await cache.resilient("t:quote:a", 60, dead, keep=cache.DAY, what="600519 的行情")
    assert served["price"] == 10 and served["stale_as_of"][:4] == str(date.today().year) and len(notes) == 1
    assert notes[0].startswith("600519 的行情：数据源这次取不到，用的是 ") and "取到的那一份" in notes[0]
    assert await cache.resilient("t:quote:a", 60, empty, keep=cache.DAY) == served                # 空的也当没取到
    assert await cache.resilient("t:quote:a", 60, good) == {"price": 10}                         # 恢复了就是新的，不带旧数据的标记
    age("t:quote:a", 3 * cache.DAY)
    assert await cache.resilient("t:quote:a", 60, dead, keep=cache.DAY) is None                  # 太旧的不拿出来
    assert await cache.resilient("t:never", 60, empty) == [] and await cache.resilient("t:never", 60, dead) is None


async def test_concurrent_requests_for_the_same_data_fetch_once_and_tests_can_switch_caching_off(caching, monkeypatch):
    started = 0

    async def slow():
        nonlocal started
        started += 1
        await asyncio.sleep(0.02)
        return [started]
    assert await asyncio.gather(*(cache.resilient("t:once", 60, slow) for _ in range(5))) == [[1]] * 5 and started == 1
    monkeypatch.setenv("WEALTHPILOT_NO_FETCH_CACHE", "1")
    assert await cache.resilient("t:once", 60, slow) == [2] and await cache.resilient("t:once", 60, slow) == [3]


# ── 行情：腾讯 → 新浪 ───────────────────────────────────

TENCENT = "v_sh600519=\"1~贵州茅台~600519~1263.00~1255.79~1255.42~35111~1~2~" + "~".join(["0"] * 21) + "~20261009161403~7.21~0.57~1282.00~1255.42~x~35111~445322~0.28~19.39~~1282~1255~2.1~15789~15789~6.28~" + "~".join(["0"] * 10) + "\";"
SINA = "var hq_str_sh600519=\"贵州茅台,1255.420,1255.790,1263.000,1282.000,1255.420,1263.000,1263.060,3511051,4453223189.000," + ",".join(["0"] * 20) + ",2026-10-09,15:34:56,00,\";"


async def test_quotes_fall_back_to_sina_and_say_what_is_missing(caching, monkeypatch):
    tencent_up = True

    def handler(request):
        if "qt.gtimg.cn" in str(request.url):
            if not tencent_up:
                return httpx.Response(501, text="<html>waf</html>")
            return httpx.Response(200, content=("v_pv_none_match=\"1\";" if "sh999999" in str(request.url) else TENCENT).encode("gbk"))
        return httpx.Response(200, content=("var hq_str_sh999999=\"\";" if "sh999999" in str(request.url) else SINA).encode("gbk"))
    net(monkeypatch, handler)
    main = await stocks.fetch_stock_quote("600519")
    assert (main["price"], main["pe_ttm"], main["total_mv_yi"], main["source"], main["quote_time"]) == (1263.0, 19.39, 15789.0, "腾讯行情", "2026-10-09 16:14")
    assert await stocks.fetch_stock_quote("999999") is None                                     # 代码不存在：两家都说没有，谁也没错
    assert all(s["status"] != "failing" for s in sources.health())
    tencent_up = False
    age("quote:sh600519", 60)
    backup = await stocks.fetch_stock_quote("600519")
    assert (backup["price"], backup["change_pct"], backup["amount_yi"], backup["quote_time"]) == (1263.0, 0.57, 44.53, "2026-10-09 15:34")
    assert backup["pe_ttm"] is None and backup["total_mv_yi"] is None and "备用源" in backup["source"]     # 没有的留空，不估
    assert {s["name"]: s["status"] for s in sources.health()}["tencent"] == "failing"
    with pytest.raises(SourceError):
        await stocks._tencent_quote("sh600519", "600519")
    net(monkeypatch, lambda r: httpx.Response(200, content="v_sh600519=\"1~贵州茅台~600519~1263.00\";".encode("gbk")))
    with pytest.raises(SourceError, match="字段数变了"):                                          # 对方改了格式：认得出来，不是悄悄返回空
        await stocks._tencent_quote("sh600519", "600519")


# ── 财务指标：东方财富 → 新浪 ────────────────────────────

def sina_report(items):
    return {"result": {"status": {"code": 0}, "data": {"report_count": "2", "report_date": [{"date_value": "20260630", "date_type": 2}, {"date_value": "20260331", "date_type": 1}],
            "report_list": {"20260630": {"data": [{"item_title": k, "item_value": v} for k, v in items.items()]}, "20260331": {"data": []}}}}}


FULL = {"常用指标": "", "归母净利润": "44516880421.86", "营业总收入": "92278072083.21", "扣非净利润": "44464207646.01", "基本每股收益": "35.57", "每股净资产": "200.989754",
        "净资产收益率(ROE)": "16.75", "毛利率": "89.555212", "销售净利率": "50.751571", "资产负债率": "15.193112", "每股经营现金流": "56.548908",
        "营业总收入增长率": "1.30", "归属母公司净利润增长率": "-1.95", "商誉": None}


async def test_financial_indicators_come_from_sina_in_the_same_shape_when_eastmoney_is_down(caching, monkeypatch):
    def handler(request):
        url = str(request.url)
        if "datacenter-web" in url:
            return httpx.Response(200, json={"result": None, "success": False, "message": "报表不存在", "code": 9501})
        if "paperCode=sh688001" in url:
            return httpx.Response(200, json={"result": {"status": {"code": 0}, "data": None}})
        return httpx.Response(200, json=sina_report(FULL))
    net(monkeypatch, handler)
    rows = await stocks.fetch_financial_indicators("600519", 4)
    assert len(rows) == 1 and rows[0] == {
        "report_date": "2026-06-30", "report_name": "2026中报", "revenue_yi": 922.78, "revenue_yoy_pct": 1.3, "net_profit_yi": 445.17, "net_profit_yoy_pct": -1.95,
        "deducted_net_profit_yi": 444.64, "roe_pct": 16.75, "gross_margin_pct": 89.56, "net_margin_pct": 50.75, "debt_ratio_pct": 15.19, "eps": 35.57, "bps": 200.99,
        "operating_cashflow_per_share": 56.55, "source": "新浪财经（备用源）"}
    state = {s["name"]: s for s in sources.health()}
    assert state["eastmoney"]["status"] == "failing" and "报表不存在" in state["eastmoney"]["error"] and state["sina"]["status"] == "ok"     # 报表改名：认作对方改版
    brief = await stocks.fetch_stock_financials("600519", 2)
    assert brief[0]["revenue_yi"] == 922.78 and "bps" not in brief[0] and brief[0]["source"] == "新浪财经（备用源）"
    assert await stocks.fetch_financial_indicators("688001", 4) == []                              # 新浪也没有：就是没有
    net(monkeypatch, lambda r: httpx.Response(200, json=sina_report({"别的名字": "1"})))
    with pytest.raises(SourceError, match="字段改名"):
        await stocks._sina_indicators("600519", 2)


async def test_the_data_centre_tells_empty_from_broken(monkeypatch):
    answers = [httpx.Response(200, json={"result": {"pages": 3, "data": [{"A": 1}]}, "success": True, "code": 0}),
               httpx.Response(200, json={"result": None, "success": False, "message": "返回数据为空", "code": 9201}),
               httpx.Response(200, json={"result": None, "success": False, "message": "参数错误", "code": 9501}),
               httpx.Response(200, text="<html>限流</html>")]
    net(monkeypatch, lambda r: answers.pop(0))
    assert await stocks.datacenter("X", strict=True) == ([{"A": 1}], 3)
    assert await stocks.datacenter("X", strict=True) == ([], 0) and not sources.health()[3]["error"]      # 没有数据不是它的错
    with pytest.raises(SourceError, match="参数错误"):
        await stocks.datacenter("X", strict=True)
    assert await stocks.datacenter("X") == ([], 0)                                                   # 不要求严格的老调用方照旧拿到空
    assert sources.is_down("eastmoney")
    seen = []
    net(monkeypatch, lambda r: seen.append(1) or httpx.Response(200, json={}))
    assert await stocks.datacenter("X") == ([], 0) and seen == []                                    # 正在跳过：不再发请求，不让每个调用都等一遍超时


# ── 估值历史：东方财富 → 百度；港股美股只有百度 ──────────

def baidu(points):
    chart = [{"body": points}] if points is not None else None
    return {"Result": [{"DisplayData": {"resultData": {"tplData": {"result": {"chartInfo": chart} if chart else {}}}}}]}


async def test_valuation_history_falls_back_to_baidu_and_covers_overseas_stocks(caching, monkeypatch):
    pe = [[f"2026-{m:02d}-{d:02d}", str(10 + m + d / 100)] for m in range(1, 10) for d in (5, 15, 25)]

    def handler(request):
        url = str(request.url)
        if "datacenter-web" in url:
            return httpx.Response(503)
        if "code=NOPE" in url:
            return httpx.Response(200, json=baidu(None))
        assert "finance.baidu.com/opendata" in url and ("market=hk" in url) == ("code=00700" in url)
        return httpx.Response(200, json=baidu(pe if "TTM" in request.url.params["tag"] else [[p[0], "2.5"] for p in pe]))
    net(monkeypatch, handler)
    a = await stocks.fetch_valuation_history("600519", 5)
    assert len(a) == 27 and a[0] == {"date": "2026-09-25", "pe_ttm": 19.25, "pb": 2.5, "ps_ttm": None, "close": None, "industry": "", "board_code": "", "name": "", "source": "百度股市通"}
    summary = stocks.summarize_valuation(a)
    assert summary["pe"]["percentile"] == 100.0 and summary["ps"]["percentile"] is None
    hk = await stocks.fetch_valuation_history("00700.HK", 5)
    assert len(hk) == 27 and hk[0]["pe_ttm"] == 19.25
    assert await stocks.fetch_valuation_history("NOPE.US", 5) == []
    from wealthpilot.services.agents.tools import execute_tool
    out = json.loads(await execute_tool("get_valuation_history", {"code": "hk00700"}, [], {}))
    assert out["code"] == "00700.HK" and out["source"] == "百度股市通" and out["pe"]["percentile"] == 100.0 and "数据点的个数" in out["note"]
    net(monkeypatch, lambda r: httpx.Response(200, json={"Result": [{"DisplayData": {}}]}))
    with pytest.raises(SourceError, match="结构变了"):
        await stocks._baidu_valuation("600519", "ab")


# ── 公告：东方财富 → 巨潮 ───────────────────────────────

async def test_announcements_fall_back_to_the_official_disclosure_site(caching, monkeypatch):
    def handler(request):
        url = str(request.url)
        if "np-anotice" in url:
            return httpx.Response(200, text="Bad Gateway")
        if url.endswith("szse_stock.json"):
            return httpx.Response(200, json={"stockList": [{"code": "600519", "orgId": "gssh0600519"}]})
        form = dict(pair.split("=") for pair in request.content.decode().split("&"))
        assert request.method == "POST" and form["stock"] == "600519%2Cgssh0600519" and form["column"] == "sse"
        return httpx.Response(200, json={"announcements": [{"announcementTitle": "贵州茅台<em>2026</em>年半年度报告", "announcementTime": 1786723200000, "adjunctUrl": "finalpage/2026-08-15/1.PDF"}]})
    net(monkeypatch, handler)
    cache.write("cninfo:orgs", None)                       # 对照表是长期缓存的：不用别的测试留下的
    rows = await stocks.fetch_announcements("600519", 5)
    assert rows == [{"date": "2026-08-15", "title": "贵州茅台2026年半年度报告", "url": "http://static.cninfo.com.cn/finalpage/2026-08-15/1.PDF", "source": "巨潮资讯（官方披露，PDF）"}]
    state = {s["name"]: s["status"] for s in sources.health()}
    assert state["eastmoney_notice"] == "failing" and state["cninfo"] == "ok"
    assert await stocks._cninfo_announcements("000001", 5) == []                                  # 对照表里没有这只：就是没有
    cache.write("cninfo:orgs", None)


# ── 日线 ─────────────────────────────────────────────────

async def test_daily_bars_use_the_second_tencent_host_then_other_vendors(caching, monkeypatch):
    seen = []
    bars = [[f"2026-10-{d:02d}", "10", str(10 + d / 10), "11", "9", "100", {}, "0.2"] for d in range(1, 8)]

    def handler(request):
        url = str(request.url)
        seen.append(request.url.host)
        if request.url.host == "web.ifzq.gtimg.cn":
            return httpx.Response(501, text="<html>waf</html>")
        if request.url.host == "proxy.finance.qq.com":
            return httpx.Response(200, json={"code": 0, "data": {"sh600519": {"qfqday": bars}} if "sh600519" in url else {"sh999999": []}})
        return httpx.Response(500)
    net(monkeypatch, handler)
    rows = await stocks.fetch_stock_kline("600519", 5)
    assert [r["nav_date"] for r in rows] == ["2026-10-07", "2026-10-06", "2026-10-05", "2026-10-04", "2026-10-03"] and rows[0]["price_basis"] == "前复权"
    assert rows[0]["nav"] == 10.7 and rows[0]["daily_return"] == round((10.7 - 10.6) / 10.6 * 100, 2) and seen[:2] == ["web.ifzq.gtimg.cn", "proxy.finance.qq.com"]
    assert await stocks._tencent_kline("sh999999", 5) == []
    net(monkeypatch, lambda r: httpx.Response(501, text="<html>waf</html>"))
    with pytest.raises(SourceError):
        await stocks._tencent_kline("sh600519", 5)
    age("kline:sh600519:5", 3600)
    notes = cache.collect_stale()
    assert await stocks.fetch_stock_kline("600519", 5) == rows and "600519 的日线" in notes[0]     # 三家都不通：用刚才那份，并说明


# ── 工具结果里写明用了旧数据 ─────────────────────────────

async def test_tool_results_carry_a_warning_when_they_rest_on_stale_data(monkeypatch):
    from wealthpilot.services.agents import tools

    async def indicators(code, periods=8):
        cache._stale_notes.get().append("600519 的财务指标：数据源这次取不到，用的是 2026-10-07 16:26 取到的那一份")
        return [{"report_date": "2026-06-30", "revenue_yi": 922.78}]

    async def fresh(code, periods=8):
        return [{"report_date": "2026-06-30", "revenue_yi": 922.78}]
    monkeypatch.setattr(tools, "fetch_financial_indicators", indicators)
    out = json.loads(await tools.execute_tool("get_financial_indicators", {"code": "600519"}, [], {}))
    assert out["data_freshness"].startswith("注意：600519 的财务指标：数据源这次取不到，用的是 2026-10-07 16:26") and "不要当成最新的" in out["data_freshness"]
    monkeypatch.setattr(tools, "fetch_financial_indicators", fresh)
    assert "data_freshness" not in json.loads(await tools.execute_tool("get_financial_indicators", {"code": "600519"}, [], {}))


# ── 官方来源：央行的社融、货币网的 LPR ───────────────────

PBC_PAGES = {
    "/diaochatongjisi/116219/116319/index.html": "<html>统计数据<a href='/diaochatongjisi/116219/116319/2026ntjsj/index.html' class='x'>2026年统计数据</a>"
                                                 "<a href='/diaochatongjisi/116219/116319/5570903/index.html'>2025年统计数据</a></html>",
    "/diaochatongjisi/116219/116319/2026ntjsj/index.html": "<a href='/diaochatongjisi/116219/116319/2026ntjsj/shrzgm/index.html'>社会融资规模</a>",
    "/diaochatongjisi/116219/116319/2026ntjsj/shrzgm/index.html": "<div>社会融资规模存量统计表</div><a href='/a/stock.htm'>htm</a><div>社会融资规模增量统计表 <br> Flow</div>"
                                                                  "<a href=\"/diaochatongjisi/attachDir/2026/09/flow26.htm\">htm</a><a href='/x.xlsx'>xls</a>",
    "/diaochatongjisi/attachDir/2026/09/flow26.htm": "<table><tr><td>社会融资规模增量统计表</td></tr><tr><td>社会融资规模增量</td><td>人民币贷款</td></tr>"
                                                     "<tr><td> 2026.07 </td><td>14,068</td><td>-5896</td></tr><tr><td>2026.08</td><td>16577</td><td>1</td></tr><tr><td>注</td><td>x</td></tr></table>",
    "/diaochatongjisi/116219/116319/5570903/index.html": "<a href='shrzgm25/index.html'>社会融资规模</a>",
    "/diaochatongjisi/116219/116319/5570903/shrzgm25/index.html": "社会融资规模增量统计表<a href='flow25.htm'>htm</a>",
    "/diaochatongjisi/116219/116319/5570903/shrzgm25/flow25.htm": "<table><tr><td>2025.12</td><td>22000</td></tr></table>",
}


async def test_social_financing_is_read_from_the_central_bank_and_falls_back_to_the_republisher(monkeypatch):
    visited = []

    def handler(request):
        visited.append(request.url.path)
        page = PBC_PAGES.get(request.url.path)
        return httpx.Response(200, content=page.encode("gb18030" if request.url.path.endswith("flow26.htm") else "utf-8")) if page else httpx.Response(404)
    rows = await macro._tsf_pbc(httpx.MockTransport(handler), today=date(2026, 10, 9))
    assert rows == [{"date": "202608", "tiosfs": 16577.0}, {"date": "202607", "tiosfs": 14068.0}, {"date": "202512", "tiosfs": 22000.0}]
    assert "/a/stock.htm" not in visited                                 # 取的是“增量”那张表，不是排在前面的“存量”
    point = macro.tsf_point(rows, "2026-08-01")
    assert (point["value"], point["as_of"], point["previous"]) == (16577.0, "2026-08-01", 14068.0) and "lag_note" not in point
    january = await macro._tsf_pbc(httpx.MockTransport(handler), today=date(2027, 1, 5))        # 新一年的页面还没建：用去年的，不算出错
    assert january[0]["date"] == "202608"
    with pytest.raises(SourceError, match="结构变了"):
        await macro._tsf_pbc(httpx.MockTransport(lambda r: httpx.Response(200, text="<html>改版了</html>")), today=date(2026, 10, 9))
    with pytest.raises(SourceError):
        await macro._tsf_pbc(httpx.MockTransport(lambda r: httpx.Response(503)), today=date(2026, 10, 9))

    async def pbc_down():
        raise SourceError("改版了")

    async def mofcom():
        return [{"date": "202604", "tiosfs": 6245}]
    monkeypatch.setattr(macro, "_tsf_pbc", pbc_down)
    monkeypatch.setattr(macro, "_tsf_mofcom", mofcom)
    late = macro.tsf_point(await macro._tsf_rows(), "2026-08-01")
    assert late["value"] == 6245 and "晚 4 个月" in late["lag_note"]         # 退到转载的那一家：晚了就写明
    assert {s["name"]: s["status"] for s in sources.health()}["pbc"] == "failing"


async def test_lpr_comes_from_the_interbank_centre_within_its_one_year_window():
    asked = {}

    def handler(request):
        asked.update(request.url.params)
        return httpx.Response(200, json={"data": {"message": ""}, "records": [{"5Y": "3.50", "1Y": "3.00", "showDateCN": "2026-08-20"}, {"5Y": "3.50", "1Y": "3.10", "showDateCN": "2026-09-20"}, {"bad": 1}]})
    rows = await macro._lpr_chinamoney(httpx.MockTransport(handler), today=date(2026, 10, 9))
    assert rows == [{"TRADE_DATE": "2026-09-20", "LPR1Y": 3.1, "LPR5Y": 3.5}, {"TRADE_DATE": "2026-08-20", "LPR1Y": 3.0, "LPR5Y": 3.5}]
    assert request_span(asked) <= 365 and macro._point(rows, "LPR1Y", "TRADE_DATE")["change"] == 0.1
    with pytest.raises(SourceError, match="只提供一年"):
        await macro._lpr_chinamoney(httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {"message": "只提供一年历史数据查询及下载"}, "records": []})))
    with pytest.raises(SourceError, match="字段改名"):
        await macro._lpr_chinamoney(httpx.MockTransport(lambda r: httpx.Response(200, json={"records": [{"x": 1}]})))


def request_span(params) -> int:
    return (date.fromisoformat(params["strEndDate"]) - date.fromisoformat(params["strStartDate"])).days


# ── 主动探测、接口、自检 ─────────────────────────────────

async def test_checking_now_probes_every_source_and_the_page_and_doctor_show_the_result(monkeypatch):
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    from wealthpilot.services import doctor

    async def works(*a, **k):
        return [{"x": 1}]

    async def nothing(*a, **k):
        return []

    async def broken(*a, **k):
        raise SourceError("返回 501，不是预期的结构")

    async def datacenter(*a, **k):
        return [{"x": 1}], 1
    for name in ("_tencent_quote", "_sina_indicators", "_em_announcements", "_baidu_valuation", "_cninfo_announcements"):
        monkeypatch.setattr(stocks, name, works)
    monkeypatch.setattr(stocks, "datacenter", datacenter)
    monkeypatch.setattr(stocks, "_tencent_kline", broken)
    monkeypatch.setattr(stocks, "_eastmoney_kline", nothing)
    for name in ("_lpr_chinamoney", "_tsf_pbc", "_tsf_mofcom", "_sina_macro"):
        monkeypatch.setattr(macro, name, works)
    from wealthpilot.services import capital, fx
    monkeypatch.setattr(capital, "_margin_sse", works)
    monkeypatch.setattr(capital, "_margin_szse", works)
    monkeypatch.setattr(fx, "_chinamoney", works)
    sources.fail("baidu", "x")
    sources.fail("baidu", "x")                                                # 正在跳过的，明说要查时也照样去问
    report = await sources.check()
    by_name = {s["name"]: s for s in report["sources"]}
    assert by_name["baidu"]["status"] == "ok" and by_name["tencent_kline"]["status"] == "failing" and "501" in by_name["tencent_kline"]["error"]
    assert by_name["eastmoney_kline"]["error"] == "连上了，但没有返回数据" and len(by_name) == len(sources.SOURCES) and report["checked_at"]
    states = {d["key"]: d["state"] for d in report["datasets"]}
    assert states["kline"] == "fallback" and states["quote"] == "ok" and states["tsf"] == "ok"
    assert sources.problems(report) == ["A 股日线在用备用来源（腾讯财经不通）：最后一个备用源是不复权价，会标出来",
                                        "港股、美股日线在用备用来源（腾讯财经不通）：备用源只有美股，而且是不复权价；港股日线只有腾讯"]
    assert all(set(d["chain"]) <= set(sources.SOURCES) for d in sources.DATASETS)        # 每类数据写的来源都登记过

    client = TestClient(app)
    shown = client.get("/api/market/sources").json()
    assert {d["key"]: d["state"] for d in shown["datasets"]}["kline"] == "fallback" and "只供个人研究" in shown["statement"]
    assert client.post("/api/market/sources/check").json()["checked_at"]

    async def flow(*a, **k):
        return [1]
    monkeypatch.setattr(capital, "_sina_json", flow)

    async def no_search():
        return doctor._item("联网搜索", "ok", "")
    monkeypatch.setattr(doctor, "_web_search", no_search)
    items = {i["name"]: i for i in await doctor._sources()}
    assert items["A 股日线"]["status"] == "warn" and "在用备用来源" in items["A 股日线"]["detail"] and "501" in items["A 股日线"]["fix"]
    assert items["公告"]["status"] == "ok" and "巨潮资讯（官方）" in items["公告"]["detail"]
