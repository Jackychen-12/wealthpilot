"""港股和美股：行情、日线、财务指标。

代码的写法：港股 00700.HK，美股 AAPL.US（A 股仍然是 6 位数字）。也认 hk00700、HK00700、5 位纯数字、纯字母的美股代码。
数据来自腾讯行情（报价、日线）、东方财富数据中心（财务指标）和百度股市通（估值历史），都是免费的公开接口。
报价在腾讯不通时换新浪；美股日线也有新浪作备用（不复权）；港股日线只有腾讯。

和 A 股比，这里**没有**的：同行行业分类、资金流向、融资融券、股东户数、龙虎榜、一致预期、公告正文。
这些工具遇到港美股代码会直接说"只覆盖 A 股"，不会拿 A 股的接口去硬查。

金额都是当地货币：港股报价是港元，美股是美元；财报的币种由公司决定（腾讯、阿里的财报是人民币），
每条数据都带着 currency，不做汇率换算 —— 换算一次就多一个会错的地方。
"""

from __future__ import annotations

import json
import re

import httpx

from wealthpilot.services import cache

_UA = {"User-Agent": "Mozilla/5.0"}
_CN_RE = re.compile(r"^(?:(?:sh|sz|bj)\d{6}|\d{6}(?:\.(?:sh|sz|bj))?)$", re.IGNORECASE)
_HK_RE = re.compile(r"^(?:hk\.?(\d{1,5})|(\d{1,5})\.hk|(\d{5}))$", re.IGNORECASE)
_US_RE = re.compile(r"^(?:us\.?([A-Za-z][A-Za-z.\-]{0,6})|([A-Za-z][A-Za-z.\-]{0,6})\.us|([A-Za-z]{1,5}))$", re.IGNORECASE)
CURRENCY = {"hk": "港元", "us": "美元"}
MARKET_LABEL = {"hk": "港股", "us": "美股"}
# 这些工具对港美股也能用；其余带 code 参数的工具只覆盖 A 股
SUPPORTED_TOOLS = frozenset({"get_stock_quote", "get_stock_valuation", "get_stock_kline", "get_technical_indicators", "get_stock_profile",
                             "get_stock_financials", "get_financial_indicators", "compute_reverse_dcf", "get_stock_news", "get_valuation_history"})


def parse(code: str) -> tuple[str, str] | None:
    """认出港股或美股代码，返回（市场, 代码）；A 股、基金或认不出返回 None。"""
    text = (code or "").strip()
    if not text or _CN_RE.match(text):
        return None
    m = _HK_RE.match(text)
    if m:
        return "hk", next(g for g in m.groups() if g).zfill(5)
    m = _US_RE.match(text)
    if m:
        return "us", next(g for g in m.groups() if g).upper()
    return None


def canonical(code: str) -> str:
    """统一成 00700.HK / AAPL.US 的写法。不是港美股就原样返回。"""
    found = parse(code)
    return f"{found[1]}.{found[0].upper()}" if found else code


def is_global(code: str) -> bool:
    return parse(code) is not None


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_from(fields: list[str], market: str, ticker: str) -> dict | None:
    if len(fields) < 50 or not fields[1] or not _f(fields[3]):
        return None
    stamp = fields[30].replace("/", "-")[:16]
    return {
        "code": f"{ticker}.{market.upper()}", "symbol": f"{market}{fields[2]}" if market == "us" else f"hk{ticker}", "name": fields[1],
        "market": market, "currency": CURRENCY[market],
        "price": _f(fields[3]), "prev_close": _f(fields[4]), "open": _f(fields[5]), "high": _f(fields[33]), "low": _f(fields[34]),
        "change": _f(fields[31]), "change_pct": _f(fields[32]),
        "amount_yi": round(_f(fields[37]) / 1e8, 2) if _f(fields[37]) else None,
        "turnover_pct": _f(fields[38]) if market == "us" else None,
        "pe_ttm": _f(fields[39]) or None, "pb": _f(fields[51]) if market == "us" else None,
        "float_mv_yi": _f(fields[44]), "total_mv_yi": _f(fields[45]),
        "high_52w": _f(fields[48]), "low_52w": _f(fields[49]),
        "quote_time": stamp, "source": "腾讯行情",
    }


async def fetch_quotes(codes: list[str]) -> dict[str, dict]:
    """批量报价。键是 00700.HK / AAPL.US 这种写法。先问腾讯，不通换新浪（没有市净率；港股没有市值）。"""
    from wealthpilot.services import sources
    wanted = {}
    for code in codes:
        found = parse(code)
        if found:
            wanted[("hk" + found[1]) if found[0] == "hk" else ("us" + found[1])] = found
    if not wanted:
        return {}
    out, _ = await sources.first([("tencent", lambda: _tencent_quotes(wanted)), ("sina", lambda: _sina_quotes(wanted))])
    return out or {}


async def _tencent_quotes(wanted: dict[str, tuple[str, str]]) -> dict[str, dict]:
    from wealthpilot.services.sources import SourceError
    async with httpx.AsyncClient(timeout=8.0, headers=_UA) as client:
        resp = await client.get("https://qt.gtimg.cn/q=" + ",".join(wanted))
    text = resp.content.decode("gbk", errors="replace")
    if resp.status_code != 200 or "v_" not in text:
        raise SourceError(f"腾讯行情返回 {resp.status_code}，内容不是预期的格式")
    out = {}
    for line in text.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if not m or m.group(1) not in wanted:
            continue
        market, ticker = wanted[m.group(1)]
        fields = m.group(2).split("~")
        if 10 < len(fields) < 50:
            raise SourceError(f"腾讯港美股行情的字段数变了：{len(fields)} 个，至少应有 50 个")
        quote = _quote_from(fields, market, ticker)
        if quote:
            out[quote["code"]] = quote
    return out


async def _sina_quotes(wanted: dict[str, tuple[str, str]]) -> dict[str, dict]:
    """新浪的港股、美股行情：腾讯不通时的备用。字段比腾讯少，没有的留空。"""
    from wealthpilot.services.sources import SourceError
    names = {(f"rt_hk{ticker}" if market == "hk" else f"gb_{ticker.lower().replace('.', '$')}"): (market, ticker) for market, ticker in wanted.values()}
    async with httpx.AsyncClient(timeout=8.0, headers={**_UA, "Referer": "https://finance.sina.com.cn"}) as client:
        resp = await client.get("https://hq.sinajs.cn/list=" + ",".join(names))
    text = resp.content.decode("gbk", errors="replace")
    if resp.status_code != 200 or "hq_str_" not in text:
        raise SourceError(f"新浪行情返回 {resp.status_code}，内容不是预期的格式")
    out = {}
    for name, body in re.findall(r'hq_str_([\w$]+)="([^"]*)"', text):
        if name not in names or not body:
            continue
        market, ticker = names[name]
        f = body.split(",")
        if len(f) < (19 if market == "hk" else 27):
            raise SourceError(f"新浪{MARKET_LABEL[market]}行情的字段数变了：{len(f)} 个")
        if market == "hk":
            quote = {"name": f[1], "open": _f(f[2]), "prev_close": _f(f[3]), "high": _f(f[4]), "low": _f(f[5]), "price": _f(f[6]), "change": _f(f[7]), "change_pct": _f(f[8]),
                     "amount_yi": round(_f(f[11]) / 1e8, 2) if _f(f[11]) else None, "total_mv_yi": None,
                     "high_52w": _f(f[15]), "low_52w": _f(f[16]), "quote_time": f"{f[17].replace('/', '-')} {f[18][:5]}", "symbol": f"hk{ticker}"}
        else:
            quote = {"name": f[0], "price": _f(f[1]), "change_pct": _f(f[2]), "quote_time": f[3][:16], "change": _f(f[4]), "open": _f(f[5]), "high": _f(f[6]), "low": _f(f[7]),
                     "high_52w": _f(f[8]), "low_52w": _f(f[9]), "total_mv_yi": round(_f(f[12]) / 1e8, 2) if _f(f[12]) else None,
                     "prev_close": _f(f[26]), "amount_yi": round(_f(f[30]) / 1e8, 2) if len(f) > 30 and _f(f[30]) else None, "symbol": f"us{ticker}"}
        if not quote["price"]:
            continue
        # 两家的市盈率口径不一样（阿里巴巴同一天一家 24 倍一家 16 倍），备用源的不拿来用，留空
        out[f"{ticker}.{market.upper()}"] = {"code": f"{ticker}.{market.upper()}", "market": market, "currency": CURRENCY[market], "turnover_pct": None, "pb": None,
                                             "pe_ttm": None, "float_mv_yi": None, **quote,
                                             "source": "新浪行情（备用源：没有市盈率和市净率" + ("，也没有市值）" if market == "hk" else "）")}
    return out


async def fetch_quote(code: str) -> dict | None:
    found = parse(code)
    if not found:
        return None
    key = f"{found[1]}.{found[0].upper()}"

    async def load():
        return (await fetch_quotes([code])).get(key)
    return await cache.resilient(f"quote:{found[0]}{found[1]}", 15, load, keep=3 * cache.DAY, what=f"{key} 的行情")


async def _tencent_symbol(code: str, market: str, ticker: str) -> str:
    """腾讯日线接口要的代码。美股要带交易所后缀（AAPL.OQ / BABA.N），只有腾讯自己的报价里有；认到了就记一个月。"""
    if market == "hk":
        return f"hk{ticker}"
    known = cache.read(f"global:tencent-symbol:{ticker}", 30 * cache.DAY)
    if known:
        return known
    quote = await fetch_quote(code)
    symbol = (quote or {}).get("symbol") or ""
    if "." in symbol:                      # 新浪顶上来的报价没有后缀，不能拿去问腾讯
        cache.write(f"global:tencent-symbol:{ticker}", symbol)
        return symbol
    return ""


async def _sina_us_kline(ticker: str, count: int) -> list[list]:
    """新浪的美股日线：腾讯不通时的备用。是不复权价；它一次给全部历史，只留最近的。行：[日期, 开, 收, 高, 低, 量]。"""
    from wealthpilot.services.sources import SourceError
    async with httpx.AsyncClient(timeout=20.0, headers={**_UA, "Referer": "https://finance.sina.com.cn"}) as client:
        resp = await client.get("https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/var%20x=/US_MinKService.getDailyK", params={"symbol": ticker.lower(), "num": str(count)})
    text = resp.text
    try:
        rows = json.loads(text[text.index("(") + 1:text.rindex(")")])
    except ValueError as e:
        raise SourceError(f"新浪美股日线返回 {resp.status_code}，不是预期的结构") from e
    if not isinstance(rows, list):
        return []                              # 没有这只股票时它给 null
    try:
        return [[r["d"], r["o"], r["c"], r["h"], r["l"], r["v"]] for r in rows[-count:]]
    except (KeyError, TypeError) as e:
        raise SourceError("新浪美股日线的字段变了：找不到 d / o / c / h / l / v") from e


async def fetch_kline(code: str, days: int = 60) -> list[dict]:
    """日线，最新在前；字段和 A 股的日线一样。腾讯给前复权价；美股在腾讯不通时换新浪（不复权，会标出来）。港股只有腾讯。"""
    found = parse(code)
    if not found:
        return []
    market, ticker = found
    count = max(5, min(int(days), 1200))

    async def load():
        from wealthpilot.services import sources, stocks
        rows, basis = [], "前复权"
        symbol = await _tencent_symbol(code, market, ticker)
        if symbol and not sources.is_down("tencent_kline"):
            try:
                rows = await stocks._tencent_kline(symbol, count)
                sources.ok("tencent_kline")
            except Exception as e:  # noqa: BLE001
                sources.fail("tencent_kline", e)
        if not rows and market == "us":
            got, _ = await sources.first([("sina", lambda: _sina_us_kline(ticker, count))])
            rows, basis = got or [], "不复权"
        out, previous = [], None
        for row in rows:
            if len(row) < 6:
                continue
            close = _f(row[2])
            if close is None:
                continue
            out.append({"fund_code": f"{ticker}.{market.upper()}", "nav_date": row[0], "nav": close,
                        "daily_return": round((close / previous - 1) * 100, 2) if previous else 0.0,
                        "open": _f(row[1]), "high": _f(row[3]), "low": _f(row[4]), "volume": _f(row[5]), "price_basis": basis})
            previous = close
        return out[::-1]
    return await cache.resilient(f"kline:{market}{ticker}:{count}", 5 * cache.MINUTE, load, keep=7 * cache.DAY, what=f"{ticker}.{market.upper()} 的日线") or []


def _yi(value) -> float | None:
    return round(value / 1e8, 2) if isinstance(value, (int, float)) else None


def _r(value, digits: int = 2) -> float | None:
    return round(value, digits) if isinstance(value, (int, float)) else None


async def fetch_indicators(code: str, periods: int = 8) -> list[dict]:
    """主要财务指标，最新在前。字段名和 A 股的一致，多了 currency（财报币种）和 annual（是不是年报）。"""
    from wealthpilot.services.stocks import datacenter

    found = parse(code)
    if not found:
        return []
    market, ticker = found
    size = max(1, min(int(periods), 20))
    if market == "hk":
        rows, _ = await datacenter("RPT_HKF10_FN_MAININDICATOR", filter=f'(SECUCODE="{ticker}.HK")', page_size=size, sort="REPORT_DATE")
        return [{
            "report_date": str(r.get("REPORT_DATE", ""))[:10], "report_name": r.get("REPORT_TYPE") or "", "annual": "年报" in str(r.get("REPORT_TYPE") or ""),
            "currency": r.get("CURRENCY") or "财报币种见公司公告（多数内地公司为人民币）",
            "revenue_yi": _yi(r.get("OPERATE_INCOME")), "revenue_yoy_pct": _r(r.get("OPERATE_INCOME_YOY")),
            "net_profit_yi": _yi(r.get("HOLDER_PROFIT")), "net_profit_yoy_pct": _r(r.get("HOLDER_PROFIT_YOY")), "deducted_net_profit_yi": None,
            "roe_pct": _r(r.get("ROE_AVG")), "gross_margin_pct": _r(r.get("GROSS_PROFIT_RATIO")), "net_margin_pct": _r(r.get("NET_PROFIT_RATIO")),
            "debt_ratio_pct": _r(r.get("DEBT_ASSET_RATIO")), "eps": _r(r.get("BASIC_EPS")), "bps": _r(r.get("BPS")),
            "operating_cashflow_per_share": _r(r.get("PER_NETCASH_OPERATE")),
        } for r in rows]
    rows, _ = await datacenter("RPT_USF10_FN_GMAININDICATOR", filter=f'(SECURITY_CODE="{ticker}")', page_size=size * 2, sort="REPORT_DATE")
    out = []
    for r in rows:
        kind = str(r.get("DATE_TYPE") or "")
        if kind == "单季报":       # 和 A 股保持一致：只留年初至今的累计数和年报，单季的不要，免得同一期出现两行
            continue
        out.append({
            "report_date": str(r.get("REPORT_DATE", ""))[:10], "report_name": r.get("REPORT_DATA_TYPE") or kind, "annual": kind == "年报",
            "currency": r.get("CURRENCY") or "",
            "revenue_yi": _yi(r.get("OPERATE_INCOME")), "revenue_yoy_pct": _r(r.get("OPERATE_INCOME_YOY")),
            "net_profit_yi": _yi(r.get("PARENT_HOLDER_NETPROFIT")), "net_profit_yoy_pct": _r(r.get("PARENT_HOLDER_NETPROFIT_YOY")), "deducted_net_profit_yi": None,
            "roe_pct": _r(r.get("ROE_AVG")), "gross_margin_pct": _r(r.get("GROSS_PROFIT_RATIO")), "net_margin_pct": _r(r.get("NET_PROFIT_RATIO")),
            "debt_ratio_pct": _r(r.get("DEBT_ASSET_RATIO")), "eps": _r(r.get("BASIC_EPS")), "bps": None, "operating_cashflow_per_share": None,
        })
    return out[:size]


async def fetch_profile(code: str) -> dict | None:
    quote = await fetch_quote(code)
    if not quote:
        return None
    return {"code": quote["code"], "name": quote["name"], "industry": "", "listing_board": MARKET_LABEL[quote["market"]],
            "total_mv_yi": quote["total_mv_yi"], "currency": quote["currency"], "market": quote["market"]}


def only_a_share(tool: str, code: str) -> str:
    """A 股才有的数据遇到港美股代码时，给模型和用户的那句话。"""
    market = MARKET_LABEL[parse(code)[0]]
    return (f"未获取到 {canonical(code)} 的这项数据：这个工具（{tool}）只覆盖 A 股，{market}没有。"
            f"{market}目前能查的是行情、日线与技术指标、财务指标、估值历史分位（市盈率、市净率）、反向 DCF、新闻，其余可以用联网搜索补。")
