"""港股和美股：行情、日线、财务指标。

代码的写法：港股 00700.HK，美股 AAPL.US（A 股仍然是 6 位数字）。也认 hk00700、HK00700、5 位纯数字、纯字母的美股代码。
数据来自腾讯行情（报价、日线）和东方财富数据中心（财务指标），都是免费的公开接口。

和 A 股比，这里**没有**的：估值历史分位、同行对比、资金流向、融资融券、股东户数、龙虎榜、一致预期、公告正文。
这些工具遇到港美股代码会直接说"只覆盖 A 股"，不会拿 A 股的接口去硬查。

金额都是当地货币：港股报价是港元，美股是美元；财报的币种由公司决定（腾讯、阿里的财报是人民币），
每条数据都带着 currency，不做汇率换算 —— 换算一次就多一个会错的地方。
"""

from __future__ import annotations

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
                             "get_stock_financials", "get_financial_indicators", "compute_reverse_dcf", "get_stock_news"})


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
    """批量报价。键是 00700.HK / AAPL.US 这种写法。"""
    wanted = {}
    for code in codes:
        found = parse(code)
        if found:
            wanted[("hk" + found[1]) if found[0] == "hk" else ("us" + found[1])] = found
    if not wanted:
        return {}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_UA) as client:
            resp = await client.get("https://qt.gtimg.cn/q=" + ",".join(wanted))
        text = resp.content.decode("gbk", errors="replace")
    except httpx.HTTPError:
        return {}
    out = {}
    for line in text.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if not m or m.group(1) not in wanted:
            continue
        market, ticker = wanted[m.group(1)]
        quote = _quote_from(m.group(2).split("~"), market, ticker)
        if quote:
            out[quote["code"]] = quote
    return out


async def fetch_quote(code: str) -> dict | None:
    found = parse(code)
    if not found:
        return None
    return (await fetch_quotes([code])).get(f"{found[1]}.{found[0].upper()}")


async def fetch_kline(code: str, days: int = 60) -> list[dict]:
    """日线，前复权，最新在前；字段和 A 股的日线一样。"""
    found = parse(code)
    if not found:
        return []
    market, ticker = found
    symbol = f"hk{ticker}"
    if market == "us":           # 美股的日线接口要带交易所后缀（AAPL.OQ / BABA.N），报价里有
        quote = await cache.cached(f"global:symbol:{ticker}", 30 * cache.DAY, lambda: fetch_quote(code))
        if not quote:
            return []
        symbol = quote["symbol"]
    count = max(5, min(int(days), 1200))
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=_UA) as client:
            resp = await client.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params={"param": f"{symbol},day,,,{count},qfq"})
        data = (resp.json().get("data") or {}).get(symbol) or {}
    except (httpx.HTTPError, ValueError):
        return []
    rows = data.get("qfqday") or data.get("day") or []
    out, previous = [], None
    for row in rows:
        if len(row) < 6:
            continue
        close = _f(row[2])
        if close is None:
            continue
        out.append({"fund_code": f"{ticker}.{market.upper()}", "nav_date": row[0], "nav": close,
                    "daily_return": round((close / previous - 1) * 100, 2) if previous else 0.0,
                    "open": _f(row[1]), "high": _f(row[3]), "low": _f(row[4]), "volume": _f(row[5]), "price_basis": "前复权"})
        previous = close
    return out[::-1]


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
            f"{market}目前能查的是行情、日线与技术指标、财务指标、反向 DCF、新闻，其余可以用联网搜索补。")
