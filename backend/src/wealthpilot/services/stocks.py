"""A 股个股 / ETF 数据：K 线、行情与估值、财务、公司概况。

全部走免费源，各有脾气：
    腾讯 K 线   前复权日线，回撤和回测必须用复权价，否则分红除权日会算出假的暴跌
    腾讯行情   一条请求带出价格、PE、PB、市值、换手率；GBK 编码，`~` 分隔
    东方财富   业绩报表（按报告期）与所属行业（数据中心接口；push2 行情接口不稳定，不用）

这些源都没有服务保障，所以行情、日线、财务指标、估值历史、公告各排了一个互相独立的备用源（顺序见 sources.DATASETS）：
主源出错或被限流就换备用的；都取不到时用上一次取到的那份，并写明是什么时候的（cache.resilient）。
实在什么都没有才返回空（[] / None），由工具层如实说"没取到"，不在这里编默认值。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import time

import httpx

from wealthpilot.services import cache, sources
from wealthpilot.services.assets import sina_symbol
from wealthpilot.services.sources import SourceError

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}
_SUFFIX_RE = re.compile(r"^(\d{6})\.(sh|sz|bj)$", re.IGNORECASE)


def market_symbol(code: str) -> str:
    """统一成带市场前缀的写法：600519 / 600519.SH / sh600519 → sh600519。"""
    code = code.strip()
    m = _SUFFIX_RE.match(code)
    if m:
        return f"{m.group(2).lower()}{m.group(1)}"
    return sina_symbol(code)


def plain_code(code: str) -> str:
    """6 位纯数字代码，用于和基金季报里的重仓股代码对齐。"""
    return market_symbol(code)[2:]


def _f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def fetch_stock_kline(code: str, days: int = 60) -> list[dict]:
    """最近 N 个交易日的前复权日线，最新在前。

    输出沿用基金净值的字段名（nav_date / nav / daily_return），这样回撤、相关性、
    回测这些已有的分析不用区分资产类型；另带 open / high / low / volume。
    三个来源依次试（腾讯 → 东方财富 → 新浪）；都不通时给上一次取到的那份。
    """
    from wealthpilot.services import global_stocks
    if global_stocks.is_global(code):
        return await global_stocks.fetch_kline(code, days)
    days = max(2, int(days))
    return await cache.resilient(f"kline:{market_symbol(code)}:{days}", 5 * cache.MINUTE, lambda: _load_kline(code, days), keep=7 * cache.DAY,
                                 what=f"{plain_code(code)} 的日线") or []


async def _load_kline(code: str, days: int) -> list[dict]:
    symbol = market_symbol(code)
    rows: list = []
    # 主源偶尔单次失败：先原地重试一次，再考虑换源
    for attempt in range(1 if _is_down("tencent_kline") else 2):
        if _is_down("tencent_kline"):
            break
        try:
            rows = await _tencent_kline(symbol, days + 1)      # 多取一根，用来算第一天的涨跌幅
        except Exception as e:  # noqa: BLE001
            rows = []
            if attempt == 1:
                sources.fail("tencent_kline", e)
        if rows:
            sources.ok("tencent_kline")
            break
        if attempt == 0:
            await asyncio.sleep(0.4)
    if not rows:
        # 主行情源对突发请求会临时限流；换东方财富的前复权日线，字段顺序整理成一致的
        rows = [] if _is_down("eastmoney_kline") else await _eastmoney_kline(symbol, days + 1)
        if rows:
            sources.ok("eastmoney_kline")
        else:
            _mark_down("eastmoney_kline")
    basis = "前复权"
    if not rows:
        # 最后的备用：新浪日线，只有不复权价。画图和看近期走势够用；跨越除权日的收益会略有偏差，所以打上标记
        rows, basis = await _sina_kline(symbol, days + 1), "不复权"

    records = []
    for prev, row in zip(rows, rows[1:], strict=False):
        try:
            close, prev_close = float(row[2]), float(prev[2])
            records.append({
                "fund_code": code,
                "nav_date": row[0],
                "nav": close,
                "daily_return": round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
                "open": float(row[1]), "high": float(row[3]), "low": float(row[4]),
                "volume": float(row[5]), "price_basis": basis,
            })
        except (ValueError, IndexError):
            continue
    return list(reversed(records))[:days]


# 同一份数据的两个入口。2026-10-09 原来的 fqkline 被对方的防火墙拦了（返回 501），换成 newfqkline；
# 第二个是它的另一个域名，前一个再出事时顶上
_TENCENT_KLINE = ("https://web.ifzq.gtimg.cn/appstock/app/newfqkline/get", "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get")


async def _tencent_kline(symbol: str, count: int) -> list[list]:
    """腾讯前复权日线：[日期, 开, 收, 高, 低, 量, …]，日期升序。A 股、港股（hk00700）、美股（usAAPL.OQ）都是这个接口。

    两个入口都不通抛 SourceError；连上了但没有这只股票返回 []。
    """
    problem: Exception | None = None
    for url in _TENCENT_KLINE:
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
                resp = await client.get(url, params={"param": f"{symbol},day,,,{count},qfq"})
            data = resp.json()["data"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            problem = SourceError(f"腾讯日线没有返回预期的结构（{type(e).__name__}）")
            continue
        node = data.get(symbol) if isinstance(data, dict) else None
        return (node.get("qfqday") or node.get("day") or []) if isinstance(node, dict) else []
    raise problem or SourceError("腾讯日线取不到")


# 某个行情源刚失败过，就先跳过它几分钟 —— 否则每次请求都要把超时等一遍，页面会慢到像是坏了。
# 成败记录和“跳过”都在 sources 里：连续失败两次才跳过，单次抖动就切换会让同一张图一会儿前复权一会儿不复权。
def _is_down(source: str) -> bool:
    return sources.is_down(source)


def _mark_down(source: str) -> None:
    sources.fail(source, "没有返回日线")


async def _sina_kline(symbol: str, count: int) -> list[list]:
    """新浪日线（不复权），整理成 [日期, 开, 收, 高, 低, 量(手)]。"""
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"Referer": "https://finance.sina.com.cn"}) as client:
            resp = await client.get("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData",
                                    params={"symbol": symbol, "scale": 240, "ma": "no", "datalen": min(count, 1000)})
        match = re.search(r"\(\s*(\[.*\])\s*\)", resp.text, re.DOTALL)
        items = json.loads(match.group(1)) if match else []
        return [[i["day"], i["open"], i["close"], i["high"], i["low"], str(float(i["volume"]) / 100)] for i in items]
    except Exception:
        return []


async def _eastmoney_kline(symbol: str, count: int) -> list[list]:
    """返回与主行情源相同的行结构：[日期, 开, 收, 高, 低, 量]，日期升序。取不到返回 []。"""
    secid = f"{1 if symbol.startswith('sh') else 0}.{symbol[2:]}"
    params = {"secid": secid, "klt": 101, "fqt": 1, "lmt": count, "end": "20500101",
              "fields1": "f1,f2,f3", "fields2": "f51,f52,f53,f54,f55,f56"}
    # 这个接口经常直接断开连接，换节点重试几次
    for host in ("push2his", "63.push2his"):
        try:
            async with httpx.AsyncClient(timeout=4.0, headers=_HEADERS) as client:
                resp = await client.get(f"https://{host}.eastmoney.com/api/qt/stock/kline/get", params=params)
            lines = (resp.json().get("data") or {}).get("klines") or []
            if lines:
                return [line.split(",") for line in lines]
        except Exception:
            await asyncio.sleep(0.3)
    return []


async def fetch_stock_quote(code: str) -> dict | None:
    """实时行情 + 估值。停牌或代码不存在返回 None。港股、美股代码转给 global_stocks。

    先问腾讯；它不通就问新浪（只有价格，没有市盈率和市值）。两边都不通时给上一次取到的，带 stale_as_of。
    """
    from wealthpilot.services import global_stocks
    if global_stocks.is_global(code):
        return await global_stocks.fetch_quote(code)
    symbol = market_symbol(code)

    async def load():
        value, _ = await sources.first([("tencent", lambda: _tencent_quote(symbol, code)), ("sina", lambda: _sina_quote(symbol, code))])
        return value
    # 15 秒：一次研究里几个 Agent 会同时要同一只股票的行情，不必各打一次
    return await cache.resilient(f"quote:{symbol}", 15, load, keep=3 * cache.DAY, what=f"{plain_code(code)} 的行情")


async def _tencent_quote(symbol: str, code: str) -> dict | None:
    async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
        resp = await client.get(f"https://qt.gtimg.cn/q={symbol}")
    text = resp.content.decode("gbk", errors="replace")
    if resp.status_code != 200 or "=" not in text:
        raise SourceError(f"腾讯行情返回 {resp.status_code}，内容不是预期的格式")
    if "none_match" in text or '"' not in text:
        return None                                   # 代码不存在：不是它的错
    fields = text.split('"')[1].split("~")
    if len(fields) < 47:
        raise SourceError(f"腾讯行情的字段数变了：{len(fields)} 个，至少应有 47 个")
    price = _f(fields[3])
    if not fields[1] or not price:
        return None
    stamp = fields[30]
    return {
        "code": plain_code(code), "symbol": symbol, "name": fields[1],
        "price": price, "prev_close": _f(fields[4]), "open": _f(fields[5]),
        "high": _f(fields[33]), "low": _f(fields[34]),
        "change": _f(fields[31]), "change_pct": _f(fields[32]),
        # 原始单位是万元；统一成亿元，免得模型自己换算
        "amount_yi": round(_f(fields[37]) / 1e4, 2) if _f(fields[37]) is not None else None,
        "turnover_pct": _f(fields[38]),
        "pe_ttm": _f(fields[39]), "pb": _f(fields[46]),
        "float_mv_yi": _f(fields[44]), "total_mv_yi": _f(fields[45]),
        "quote_time": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}" if len(stamp) >= 12 else "",
        "source": "腾讯行情",
    }


async def _sina_quote(symbol: str, code: str) -> dict | None:
    """新浪行情：腾讯不通时的备用。只有价格和成交额，没有市盈率、市净率、市值、换手率 —— 这几项留空，不估。"""
    async with httpx.AsyncClient(timeout=8.0, headers={**_HEADERS, "Referer": "https://finance.sina.com.cn"}) as client:
        resp = await client.get(f"https://hq.sinajs.cn/list={symbol}")
    text = resp.content.decode("gbk", errors="replace")
    if resp.status_code != 200 or "hq_str_" not in text:
        raise SourceError(f"新浪行情返回 {resp.status_code}，内容不是预期的格式")
    fields = text.split('"')[1].split(",") if '"' in text else []
    if len(fields) < 2:
        return None                                   # 代码不存在时是一对空引号
    if len(fields) < 32:
        raise SourceError(f"新浪行情的字段数变了：{len(fields)} 个，至少应有 32 个")
    price, prev = _f(fields[3]), _f(fields[2])
    if not price:
        return None
    return {
        "code": plain_code(code), "symbol": symbol, "name": fields[0],
        "price": price, "prev_close": prev, "open": _f(fields[1]), "high": _f(fields[4]), "low": _f(fields[5]),
        "change": round(price - prev, 3) if prev else None, "change_pct": round((price - prev) / prev * 100, 2) if prev else None,
        "amount_yi": round(_f(fields[9]) / 1e8, 2) if _f(fields[9]) is not None else None,
        "turnover_pct": None, "pe_ttm": None, "pb": None, "float_mv_yi": None, "total_mv_yi": None,
        "quote_time": f"{fields[30]} {fields[31][:5]}", "source": "新浪行情（备用源：没有市盈率、市净率和市值）",
    }


async def fetch_stock_financials(code: str, periods: int = 4) -> list[dict]:
    """最近几期业绩报表，最新在前。先问东方财富，不通换新浪。"""
    from wealthpilot.services import global_stocks
    if global_stocks.is_global(code):
        return await global_stocks.fetch_indicators(code, periods)
    periods = max(1, min(int(periods), 12))

    async def eastmoney():
        rows, _ = await datacenter("RPT_LICO_FN_CPD", filter=f'(SECURITY_CODE="{plain_code(code)}")', page_size=periods, sort="REPORTDATE", strict=True)

        def r2(v):
            return round(v, 2) if isinstance(v, (int, float)) else None
        return [{
            "report_date": str(row.get("REPORTDATE", ""))[:10],
            "revenue_yi": r2(row["TOTAL_OPERATE_INCOME"] / 1e8) if row.get("TOTAL_OPERATE_INCOME") else None,
            "revenue_yoy_pct": r2(row.get("YSTZ")),
            "net_profit_yi": r2(row["PARENT_NETPROFIT"] / 1e8) if row.get("PARENT_NETPROFIT") else None,
            "net_profit_yoy_pct": r2(row.get("SJLTZ")),
            "roe_pct": r2(row.get("WEIGHTAVG_ROE")),
            "eps": r2(row.get("BASIC_EPS")),
            "gross_margin_pct": r2(row.get("XSMLL")),
        } for row in rows]

    async def sina():
        keep = ("report_date", "revenue_yi", "revenue_yoy_pct", "net_profit_yi", "net_profit_yoy_pct", "roe_pct", "eps", "gross_margin_pct", "source")
        return [{k: row.get(k) for k in keep} for row in await _sina_indicators(code, periods)]

    async def load():
        value, _ = await sources.first([("eastmoney", eastmoney), ("sina", sina)])
        return value or []
    return await cache.resilient(f"fin:{plain_code(code)}:{periods}", 6 * cache.HOUR, load, keep=45 * cache.DAY, what=f"{plain_code(code)} 的业绩报表") or []


_SINA_REPORT_NAME = {1: "一季报", 2: "中报", 3: "三季报", 4: "年报"}


async def _sina_indicators(code: str, periods: int) -> list[dict]:
    """新浪的“关键指标”：东方财富数据中心不通时的备用。字段整理成和主源一样的名字和单位。"""
    async with httpx.AsyncClient(timeout=10.0, headers={**_HEADERS, "Referer": "https://finance.sina.com.cn"}) as client:
        resp = await client.get("https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022",
                                params={"paperCode": market_symbol(code), "source": "gjzb", "type": "0", "page": "1", "num": str(periods)})
    try:
        result = resp.json()["result"]
    except (ValueError, KeyError, TypeError) as e:
        raise SourceError(f"新浪财务指标返回 {resp.status_code}，不是预期的结构") from e
    data = result.get("data")
    if not data:
        return []                                     # 这只股票它没有数据
    dates, reports = data.get("report_date"), data.get("report_list")
    if not isinstance(dates, list) or not isinstance(reports, dict):
        raise SourceError("新浪财务指标的结构变了：找不到 report_date / report_list")
    out = []
    for d in dates[:periods]:
        stamp = str(d.get("date_value") or "")
        items = (reports.get(stamp) or {}).get("data") or []
        got: dict[str, float] = {}
        for item in items:                            # 同一个指标在几个分组里重复出现，取第一次
            try:
                got.setdefault(item["item_title"], float(item["item_value"]))
            except (KeyError, TypeError, ValueError):
                continue
        if "营业总收入" not in got and "归母净利润" not in got:
            continue

        def yi(key: str, got=got):
            return _r(got[key] / 1e8) if key in got else None
        out.append({
            "report_date": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}", "report_name": f"{stamp[:4]}{_SINA_REPORT_NAME.get(d.get('date_type'), '')}",
            "revenue_yi": yi("营业总收入"), "revenue_yoy_pct": _r(got.get("营业总收入增长率")),
            "net_profit_yi": yi("归母净利润"), "net_profit_yoy_pct": _r(got.get("归属母公司净利润增长率")),
            "deducted_net_profit_yi": yi("扣非净利润"),
            "roe_pct": _r(got.get("净资产收益率(ROE)")), "gross_margin_pct": _r(got.get("毛利率")), "net_margin_pct": _r(got.get("销售净利率")),
            "debt_ratio_pct": _r(got.get("资产负债率")), "eps": _r(got.get("基本每股收益")), "bps": _r(got.get("每股净资产")),
            "operating_cashflow_per_share": _r(got.get("每股经营现金流")), "source": "新浪财经（备用源）",
        })
    if dates and not out:
        raise SourceError("新浪财务指标里找不到“营业总收入”“归母净利润”这两项，多半是字段改名了")
    return out


async def fetch_stock_profile(code: str) -> dict | None:
    """所属行业、上市板块、市值。

    行业取自东方财富业绩报表里的板块归属（它的行情接口 push2 经常直接断开连接，不能依赖），
    市值取自腾讯行情。两边都取不到才返回 None。
    """
    from wealthpilot.services import global_stocks
    if global_stocks.is_global(code):
        return await global_stocks.fetch_profile(code)
    rows, quote = [], None
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(
                "https://datacenter-web.eastmoney.com/api/data/v1/get",
                params={
                    "reportName": "RPT_LICO_FN_CPD",
                    "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,TRADE_MARKET,REPORTDATE",
                    "filter": f'(SECURITY_CODE="{plain_code(code)}")',
                    "pageSize": 1, "sortColumns": "REPORTDATE", "sortTypes": -1,
                },
            )
        rows = (resp.json().get("result") or {}).get("data") or []
    except Exception:
        rows = []
    quote = await fetch_stock_quote(code)
    if not rows and not quote:
        return None
    row = rows[0] if rows else {}
    return {
        "code": plain_code(code),
        "name": row.get("SECURITY_NAME_ABBR") or (quote or {}).get("name", ""),
        "industry": row.get("BOARD_NAME") or "",
        "listing_board": row.get("TRADE_MARKET") or "",
        "total_mv_yi": (quote or {}).get("total_mv_yi"),
        "float_mv_yi": (quote or {}).get("float_mv_yi"),
        "source": "东方财富（行业）+ 腾讯行情（市值）",
    }


_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"


# 按报告期更新的数据（分红、股东、机构持仓、主营构成）：上一次取到的那份留这么久。
# 这些数一个季度甚至一年才变一次，断线期间拿出来的多半就是最新的那一期
SLOW = 150 * cache.DAY

_EM_EMPTY = 9201     # “返回数据为空”：这只股票本来就没有这项数据，不是接口坏了


async def datacenter(report: str, *, filter: str = "", columns: str = "ALL", page_size: int = 50,
                     page: int = 1, sort: str = "", desc: bool = True, strict: bool = False) -> tuple[list[dict], int]:
    """东方财富数据中心报表查询。返回 (行列表, 总页数)；失败返回 ([], 0)。

    strict=True 时失败不吞掉，抛 SourceError —— 给有备用源的调用方用，它要分得清“没有数据”和“这一家不通”。
    不管哪种，成败都记进 sources：连不上、超时、返回的不是预期的结构（报表改名、参数变了）算失败；数据为空不算。
    """
    params: dict = {"reportName": report, "columns": columns, "pageSize": page_size, "pageNumber": page}
    if filter:
        params["filter"] = filter
    if sort:
        params["sortColumns"] = sort
        params["sortTypes"] = -1 if desc else 1
    try:
        if sources.is_down("eastmoney"):
            raise SourceError("东方财富数据中心刚刚连续失败，先跳过两分钟")
        try:
            async with _em_gate(), httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                resp = await client.get(_DATACENTER, params=params)
            body = resp.json()
        except SourceError:
            raise
        except Exception as e:  # noqa: BLE001
            sources.fail("eastmoney", e)
            raise SourceError(f"东方财富数据中心没连上：{type(e).__name__}") from e
        if not isinstance(body, dict) or ("result" not in body and "success" not in body):
            sources.fail("eastmoney", f"{report} 返回的不是预期的结构")
            raise SourceError(f"东方财富数据中心 {report} 返回的不是预期的结构")
        result = body.get("result")
        if not result:
            if body.get("code") in (_EM_EMPTY, 0, None) or "为空" in str(body.get("message") or ""):
                sources.ok("eastmoney")
                return [], 0
            sources.fail("eastmoney", f"{report}：{body.get('message')}（{body.get('code')}）")   # 报表不存在、参数不对：对方改了
            raise SourceError(f"东方财富数据中心 {report}：{body.get('message')}")
        sources.ok("eastmoney")
        return result.get("data") or [], int(result.get("pages") or 0)
    except SourceError:
        if strict:
            raise
        return [], 0


# 东方财富数据中心是这里用得最重的一个源：一次深度研究六个 Agent 并行，几秒内能打出去几十个请求。
# 打得太密会被对方按 IP 限流甚至封一段时间，那时所有财务、估值、筹码数据一起没有。
# 所以在这一个出口上限速：同时最多几个，两个请求的起始时间至少隔开一小段，再加一点抖动。
EM_MAX_CONCURRENT = 4
EM_MIN_INTERVAL = 0.12
_em_state: dict = {"loop": None, "sem": None, "lock": None, "last": 0.0}


@contextlib.asynccontextmanager
async def _em_gate():
    loop = asyncio.get_running_loop()
    if _em_state["loop"] is not loop:      # 信号量绑在事件循环上；换了循环（测试、命令行里多次 asyncio.run）就重建
        _em_state.update(loop=loop, sem=asyncio.Semaphore(EM_MAX_CONCURRENT), lock=asyncio.Lock(), last=0.0)
    async with _em_state["sem"]:
        async with _em_state["lock"]:
            wait = _em_state["last"] + EM_MIN_INTERVAL + random.uniform(0, EM_MIN_INTERVAL / 2) - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            _em_state["last"] = loop.time()
        yield


def _r(value, digits: int = 2):
    return round(value, digits) if isinstance(value, (int, float)) else None


async def fetch_valuation_history(code: str, years: int = 5) -> list[dict]:
    """PE(TTM) / PB / PS 历史，最新在前。

    A 股先问东方财富（每个交易日一个点，带行业归属）；不通换百度股市通（点稀一些，没有 PS 和行业）。
    港股、美股只有百度有。
    """
    from wealthpilot.services import global_stocks
    market = global_stocks.parse(code)
    if market:
        key, what = f"valuation:{market[0]}:{market[1]}", f"{global_stocks.canonical(code)} 的估值历史"

        async def load_overseas():
            value, _ = await sources.first([("baidu", lambda: _baidu_valuation(market[1], market[0], years))])
            return value or []
        return await cache.resilient(key, 6 * cache.HOUR, load_overseas, keep=45 * cache.DAY, what=what) or []

    async def eastmoney():
        rows, _ = await datacenter(
            "RPT_VALUEANALYSIS_DET", filter=f'(SECURITY_CODE="{plain_code(code)}")',
            columns="TRADE_DATE,PE_TTM,PB_MRQ,PS_TTM,CLOSE_PRICE,TOTAL_MARKET_CAP,BOARD_NAME,ORIG_BOARD_CODE,SECURITY_NAME_ABBR",
            page_size=min(3000, max(60, years * 250)), sort="TRADE_DATE", strict=True,
        )
        return [{
            "date": str(r.get("TRADE_DATE", ""))[:10], "pe_ttm": _r(r.get("PE_TTM")), "pb": _r(r.get("PB_MRQ")),
            "ps_ttm": _r(r.get("PS_TTM")), "close": r.get("CLOSE_PRICE"),
            "industry": r.get("BOARD_NAME") or "", "board_code": str(r.get("ORIG_BOARD_CODE") or ""),
            "name": r.get("SECURITY_NAME_ABBR") or "",
        } for r in rows]

    async def load():
        value, _ = await sources.first([("eastmoney", eastmoney), ("baidu", lambda: _baidu_valuation(plain_code(code), "ab", years))])
        return value or []
    return await cache.resilient(f"valuation:{plain_code(code)}:{years}", 6 * cache.HOUR, load, keep=45 * cache.DAY, what=f"{plain_code(code)} 的估值历史") or []


_BAIDU_WINDOW = {1: "近一年", 3: "近三年", 5: "近五年", 10: "近十年"}


async def _baidu_valuation(ticker: str, market: str, years: int = 5) -> list[dict]:
    """百度股市通的市盈率(TTM)、市净率历史。market：ab（A 股）/ hk / us。整理成和主源一样的行，最新在前。"""
    window = _BAIDU_WINDOW[min((y for y in _BAIDU_WINDOW if y >= years), default=10)]

    async def series(client: httpx.AsyncClient, tag: str) -> dict[str, float]:
        resp = await client.get("https://finance.baidu.com/opendata", params={
            "openapi": "1", "dspName": "iphone", "tn": "tangram", "client": "app", "query": tag, "code": ticker, "word": "", "resource_id": "51171",
            "market": market, "tag": tag, "chart_select": window, "industry_select": "", "skip_industry": "1", "finClientType": "pc"})
        try:
            results = resp.json()["Result"]
        except (ValueError, KeyError, TypeError) as e:
            raise SourceError(f"百度股市通返回 {resp.status_code}，不是预期的结构") from e
        if not results:
            return {}                                 # 这只股票它没有
        try:
            result = results[0]["DisplayData"]["resultData"]["tplData"].get("result") or {}
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise SourceError("百度股市通的结构变了：找不到 tplData") from e
        chart = result.get("chartInfo") if isinstance(result, dict) else None
        if not chart:
            return {}                                 # 结构还在，只是这只股票没有图：代码不存在，或者它没收录
        body = chart[0].get("body") or []
        out = {}
        for point in body:
            try:
                out[str(point[0])[:10]] = float(point[1])
            except (IndexError, TypeError, ValueError):
                continue
        return out

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={**_HEADERS, "Referer": "https://finance.baidu.com/"}) as client:
        pe, pb = await asyncio.gather(series(client, "市盈率(TTM)"), series(client, "市净率"))
    return [{"date": day, "pe_ttm": _r(pe.get(day)), "pb": _r(pb.get(day)), "ps_ttm": None, "close": None, "industry": "", "board_code": "", "name": "",
             "source": "百度股市通"} for day in sorted(set(pe) | set(pb), reverse=True)]


def percentile_of(values: list[float], current: float) -> float | None:
    """current 在 values 中的分位（0–100）：有多少比例的历史值不高于它。"""
    valid = [v for v in values if v is not None]
    if len(valid) < 20:
        return None
    return round(sum(v <= current for v in valid) / len(valid) * 100, 1)


def summarize_valuation(history: list[dict]) -> dict:
    """历史估值分位。亏损期的负 PE 不参与分位计算（负值无法和正值比较贵贱）。"""
    latest = history[0]
    out: dict = {"as_of": latest["date"], "window_start": history[-1]["date"], "trading_days": len(history)}
    for key, label in (("pe_ttm", "pe"), ("pb", "pb"), ("ps_ttm", "ps")):
        series = [h[key] for h in history if h[key] is not None and h[key] > 0]
        current = latest[key]
        if current is None or current <= 0 or len(series) < 20:
            out[label] = {"current": current, "percentile": None,
                          "note": "当前值为负或缺失，或历史样本不足，无法计算分位"}
            continue
        ordered = sorted(series)
        out[label] = {
            "current": current, "percentile": percentile_of(series, current),
            "min": ordered[0], "median": ordered[len(ordered) // 2], "max": ordered[-1],
        }
    return out


async def fetch_financial_indicators(code: str, periods: int = 8) -> list[dict]:
    """主要财务指标（盈利能力、成长、杠杆、现金流），按报告期，最新在前。"""
    from wealthpilot.services import global_stocks
    if global_stocks.is_global(code):
        return await global_stocks.fetch_indicators(code, periods)
    periods = max(1, min(int(periods), 20))

    async def eastmoney():
        rows, _ = await datacenter("RPT_F10_FINANCE_MAINFINADATA", filter=f'(SECURITY_CODE="{plain_code(code)}")', page_size=periods, sort="REPORT_DATE", strict=True)

        def yi(v):
            return _r(v / 1e8) if isinstance(v, (int, float)) else None
        return [{
            "report_date": str(r.get("REPORT_DATE", ""))[:10], "report_name": r.get("REPORT_DATE_NAME") or "",
            "revenue_yi": yi(r.get("TOTALOPERATEREVE")), "revenue_yoy_pct": _r(r.get("TOTALOPERATEREVETZ")),
            "net_profit_yi": yi(r.get("PARENTNETPROFIT")), "net_profit_yoy_pct": _r(r.get("PARENTNETPROFITTZ")),
            "deducted_net_profit_yi": yi(r.get("KCFJCXSYJLR")),
            "roe_pct": _r(r.get("ROEJQ")), "gross_margin_pct": _r(r.get("XSMLL")), "net_margin_pct": _r(r.get("XSJLL")),
            "debt_ratio_pct": _r(r.get("ZCFZL")), "eps": _r(r.get("EPSJB")), "bps": _r(r.get("BPS")),
            "operating_cashflow_per_share": _r(r.get("MGJYXJJE")),
        } for r in rows]

    async def load():
        value, _ = await sources.first([("eastmoney", eastmoney), ("sina", lambda: _sina_indicators(code, periods))])
        return value or []
    return await cache.resilient(f"indicators:{plain_code(code)}:{periods}", 6 * cache.HOUR, load, keep=45 * cache.DAY, what=f"{plain_code(code)} 的财务指标") or []


async def fetch_dividends(code: str, limit: int = 8) -> list[dict]:
    """分红记录。一年变一两次，只有东方财富这一个来源：取不到时用上一次取到的，最多留满大半年。"""
    return await cache.resilient(f"dividends:{plain_code(code)}:{limit}", cache.DAY, lambda: _load_dividends(code, limit), keep=SLOW,
                                 what=f"{plain_code(code)} 的分红记录") or []


async def _load_dividends(code: str, limit: int) -> list[dict]:
    rows, _ = await datacenter(
        "RPT_SHAREBONUS_DET", filter=f'(SECURITY_CODE="{plain_code(code)}")',
        page_size=max(1, min(limit, 30)), sort="EX_DIVIDEND_DATE",
    )
    return [{
        "report_date": str(r.get("REPORT_DATE", ""))[:10], "plan": r.get("IMPL_PLAN_PROFILE") or "",
        "cash_per_10_shares": _r(r.get("PRETAX_BONUS_RMB"), 4), "dividend_yield_pct": _r((r.get("DIVIDENT_RATIO") or 0) * 100)
        if isinstance(r.get("DIVIDENT_RATIO"), (int, float)) else None,
        "ex_dividend_date": str(r.get("EX_DIVIDEND_DATE") or "")[:10], "progress": r.get("ASSIGN_PROGRESS") or "",
    } for r in rows]


async def fetch_industry_peers(code: str, limit: int = 30) -> dict | None:
    """同行业公司的估值与市值（同一交易日），按市值降序。"""
    own = await fetch_valuation_history(code, years=1)
    if not own or not own[0]["board_code"]:
        return None
    latest = own[0]
    rows, _ = await datacenter(
        "RPT_VALUEANALYSIS_DET",
        filter=f"(ORIG_BOARD_CODE=\"{latest['board_code']}\")(TRADE_DATE='{latest['date']}')",
        columns="SECURITY_CODE,SECURITY_NAME_ABBR,PE_TTM,PB_MRQ,PS_TTM,TOTAL_MARKET_CAP,CHANGE_RATE,CLOSE_PRICE",
        page_size=200, sort="TOTAL_MARKET_CAP",
    )
    peers = [{
        "code": r["SECURITY_CODE"], "name": r.get("SECURITY_NAME_ABBR") or "",
        "pe_ttm": _r(r.get("PE_TTM")), "pb": _r(r.get("PB_MRQ")),
        "total_mv_yi": _r((r.get("TOTAL_MARKET_CAP") or 0) / 1e8), "change_pct": _r(r.get("CHANGE_RATE")),
    } for r in rows]
    if not peers:
        return None
    target = plain_code(code)
    positive_pe = sorted(p["pe_ttm"] for p in peers if p["pe_ttm"] and p["pe_ttm"] > 0)
    return {
        "industry": latest["industry"], "as_of": latest["date"], "peer_count": len(peers),
        "industry_median_pe": positive_pe[len(positive_pe) // 2] if positive_pe else None,
        "mv_rank": next((i + 1 for i, p in enumerate(peers) if p["code"] == target), None),
        "target": next((p for p in peers if p["code"] == target), None),
        "peers": peers[:limit],
    }


async def fetch_announcements(code: str, limit: int = 10) -> list[dict]:
    """最近的公告，新的在前。先问东方财富（它的公告能接着读正文）；不通换巨潮资讯 —— 证监会指定的披露网站，给的是官方 PDF 的链接。"""
    limit = max(1, min(limit, 30))

    async def load():
        value, _ = await sources.first([("eastmoney_notice", lambda: _em_announcements(code, limit)), ("cninfo", lambda: _cninfo_announcements(code, limit))])
        return value or []
    return await cache.resilient(f"ann:{plain_code(code)}:{limit}", 30 * cache.MINUTE, load, keep=7 * cache.DAY, what=f"{plain_code(code)} 的公告") or []


async def _em_announcements(code: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
        resp = await client.get("https://np-anotice-stock.eastmoney.com/api/security/ann",
                                params={"sr": -1, "page_size": limit, "page_index": 1, "ann_type": "A", "client_source": "web", "stock_list": plain_code(code)})
    try:
        data = resp.json()["data"]
    except (ValueError, KeyError, TypeError) as e:
        raise SourceError(f"东方财富公告返回 {resp.status_code}，不是预期的结构") from e
    return [{"date": str(i.get("notice_date", ""))[:10], "title": i.get("title", ""),
             "url": f"https://data.eastmoney.com/notices/detail/{plain_code(code)}/{i.get('art_code', '')}.html"} for i in (data or {}).get("list") or []]


async def _cninfo_org(code: str) -> str:
    """巨潮查公告要用它自己的机构编号。全市场的对照表一个月取一次。"""
    async def load():
        async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
            resp = await client.get("http://www.cninfo.com.cn/new/data/szse_stock.json")
        try:
            return {item["code"]: item["orgId"] for item in resp.json()["stockList"]}
        except (ValueError, KeyError, TypeError) as e:
            raise SourceError(f"巨潮的股票对照表返回 {resp.status_code}，不是预期的结构") from e
    table = await cache.cached("cninfo:orgs", 30 * cache.DAY, load) or {}
    return table.get(plain_code(code), "")


async def _cninfo_announcements(code: str, limit: int) -> list[dict]:
    plain = plain_code(code)
    org = await _cninfo_org(code)
    if not org:
        return []
    form = {"stock": f"{plain},{org}", "tabName": "fulltext", "pageSize": str(limit), "pageNum": "1", "column": "sse" if plain.startswith(("6", "9")) else "szse",
            "category": "", "plate": "", "seDate": "", "searchkey": "", "secid": "", "sortName": "", "sortType": "", "isHLtitle": "false"}
    async with httpx.AsyncClient(timeout=12.0, headers={**_HEADERS, "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
                                                        "X-Requested-With": "XMLHttpRequest"}) as client:
        resp = await client.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=form)
    try:
        items = resp.json().get("announcements")
    except (ValueError, AttributeError) as e:
        raise SourceError(f"巨潮公告返回 {resp.status_code}，不是预期的结构") from e
    return [{"date": time.strftime("%Y-%m-%d", time.localtime(int(i["announcementTime"]) / 1000)), "title": re.sub(r"<[^>]+>", "", str(i.get("announcementTitle") or "")),
             "url": f"http://static.cninfo.com.cn/{i.get('adjunctUrl', '')}", "source": "巨潮资讯（官方披露，PDF）"} for i in items or [] if i.get("announcementTime")]


def summarize_technicals(records: list[dict]) -> dict:
    """均线与波动（纯计算）。records 最新在前，建议至少 60 根。"""
    closes = [r["nav"] for r in records]
    latest = closes[0]

    def ma(n):
        return round(sum(closes[:n]) / n, 3) if len(closes) >= n else None

    def vs(avg):
        return round((latest - avg) / avg * 100, 2) if avg else None

    returns = [r["daily_return"] for r in records[:20] if r.get("daily_return") is not None]
    mean = sum(returns) / len(returns) if returns else 0.0
    daily_vol = (sum((x - mean) ** 2 for x in returns) / (len(returns) - 1)) ** 0.5 if len(returns) > 1 else None
    ma5, ma20, ma60 = ma(5), ma(20), ma(60)
    return {
        "as_of": records[0]["nav_date"], "latest_close": latest,
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "vs_ma20_pct": vs(ma20), "vs_ma60_pct": vs(ma60),
        "ma_alignment": ("多头排列（MA5 > MA20 > MA60）" if ma5 and ma20 and ma60 and ma5 > ma20 > ma60
                         else "空头排列（MA5 < MA20 < MA60）" if ma5 and ma20 and ma60 and ma5 < ma20 < ma60
                         else "均线交织，无明确排列"),
        "volatility_20d_annualized_pct": round(daily_vol * (252 ** 0.5), 2) if daily_vol is not None else None,
        "price_basis": "前复权收盘价",
        "note": "均线排列只描述已发生的走势，不构成对后续涨跌的预测",
    }


def summarize_kline(records: list[dict]) -> dict:
    """K 线摘要：区间涨跌、高低点、当前价在区间内的位置。records 最新在前。"""
    closes = [r["nav"] for r in records]
    latest, first = closes[0], closes[-1]
    high = max(r.get("high", r["nav"]) for r in records)
    low = min(r.get("low", r["nav"]) for r in records)
    return {
        "trading_days": len(records),
        "start_date": records[-1]["nav_date"], "end_date": records[0]["nav_date"],
        "start_close": first, "latest_close": latest,
        "period_return_pct": round((latest - first) / first * 100, 2) if first else None,
        "period_high": high, "period_low": low,
        # 0 = 贴着区间最低，100 = 贴着区间最高
        "range_position_pct": round((latest - low) / (high - low) * 100, 1) if high > low else None,
        "price_basis": "前复权收盘价",
    }


async def fetch_business_segments(code: str) -> dict | None:
    """最新一期的主营构成：按产品、按地区、按行业各自的收入占比与毛利率。半年变一次，取不到时用上一次的。"""
    return await cache.resilient(f"segments:{plain_code(code)}", cache.DAY, lambda: _load_segments(code), keep=SLOW, what=f"{plain_code(code)} 的主营构成")


async def _load_segments(code: str) -> dict | None:
    rows, _ = await datacenter("RPT_F10_FN_MAINOP", filter=f'(SECURITY_CODE="{plain_code(code)}")', page_size=60, sort="REPORT_DATE")
    if not rows:
        return None
    latest = rows[0].get("REPORT_DATE")
    kinds = {"1": "by_industry", "2": "by_product", "3": "by_region"}
    out: dict = {"report_date": str(latest or "")[:10], "report_name": rows[0].get("REPORT_NAME") or "",
                 "by_industry": [], "by_product": [], "by_region": []}
    for r in rows:
        if r.get("REPORT_DATE") != latest or str(r.get("MAINOP_TYPE")) not in kinds:
            continue
        ratio, margin = r.get("MBI_RATIO"), r.get("GROSS_RPOFIT_RATIO")
        out[kinds[str(r["MAINOP_TYPE"])]].append({
            "name": r.get("ITEM_NAME") or "", "revenue_yi": _r((r.get("MAIN_BUSINESS_INCOME") or 0) / 1e8),
            "revenue_ratio_pct": _r(ratio * 100) if isinstance(ratio, (int, float)) else None,
            "gross_margin_pct": _r(margin * 100) if isinstance(margin, (int, float)) else None,
        })
    for key in kinds.values():
        out[key].sort(key=lambda i: -(i["revenue_ratio_pct"] or 0))
    return out


async def fetch_minute(code: str, days: int = 1) -> dict | None:
    """分时：每分钟的价格、当日均价与成交量。days=1 是最近一个交易日，days=5 是最近五个交易日。"""
    symbol = market_symbol(code)
    path = "minute/query" if days <= 1 else "day/query"
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(f"https://web.ifzq.gtimg.cn/appstock/app/{path}", params={"code": symbol})
        node = (resp.json().get("data") or {}).get(symbol) or {}
    except Exception:
        return None
    quote = (node.get("qt") or {}).get(symbol) or []
    sessions = [{"date": str((node.get("data") or {}).get("date") or ""), "data": (node.get("data") or {}).get("data") or []}] if days <= 1 \
        else [{"date": str(d.get("date") or ""), "data": d.get("data") or [], "prev_close": d.get("prec")} for d in reversed(node.get("data") or [])]
    points: list[dict] = []
    for session in sessions:
        last_volume = 0.0
        for line in session["data"]:
            parts = str(line).split()
            if len(parts) < 3:
                continue
            price, volume = _f(parts[1]), _f(parts[2]) or 0.0
            amount = _f(parts[3]) if len(parts) > 3 else None
            if price is None:
                continue
            day = session["date"]
            points.append({
                "time": f"{day[:4]}-{day[4:6]}-{day[6:8]} {parts[0][:2]}:{parts[0][2:]}" if len(day) == 8 else f"{parts[0][:2]}:{parts[0][2:]}",
                "price": price,
                # 接口给的是累计成交量（手）和累计成交额：均价 = 累计额 / 累计量，每分钟的量 = 两个累计值之差
                "avg": round(amount / (volume * 100), 3) if amount and volume else None,
                "volume": max(0.0, volume - last_volume),
            })
            last_volume = volume
    if not points:
        return None
    prev_close = _f(quote[4]) if len(quote) > 4 else None
    if days > 1 and sessions and sessions[0].get("prev_close"):
        prev_close = _f(sessions[0]["prev_close"])
    return {"code": plain_code(code), "name": quote[1] if len(quote) > 1 else "", "prev_close": prev_close, "days": 1 if days <= 1 else len(sessions), "points": points}
