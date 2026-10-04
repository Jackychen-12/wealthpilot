"""A 股个股 / ETF 数据：K 线、行情与估值、财务、公司概况。

全部走免费源，各有脾气：
    腾讯 K 线   前复权日线，回撤和回测必须用复权价，否则分红除权日会算出假的暴跌
    腾讯行情   一条请求带出价格、PE、PB、市值、换手率；GBK 编码，`~` 分隔
    东方财富   业绩报表（按报告期）与所属行业（数据中心接口；push2 行情接口不稳定，不用）

取不到一律返回空（[] / None），由工具层如实说"没取到"，不在这里编默认值。
"""

from __future__ import annotations

import re

import httpx

from wealthpilot.services.assets import sina_symbol

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
    """
    symbol = market_symbol(code)
    days = max(2, int(days))
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                # 多取一根，用来算第一天的涨跌幅
                params={"param": f"{symbol},day,,,{days + 1},qfq"},
            )
        node = resp.json()["data"][symbol]
        rows = node.get("qfqday") or node.get("day") or []
    except Exception:
        return []

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
                "volume": float(row[5]),
            })
        except (ValueError, IndexError):
            continue
    return list(reversed(records))[:days]


async def fetch_stock_quote(code: str) -> dict | None:
    """实时行情 + 估值。停牌或代码不存在返回 None。"""
    symbol = market_symbol(code)
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
            resp = await client.get(f"https://qt.gtimg.cn/q={symbol}")
        fields = resp.content.decode("gbk", errors="replace").split('"')[1].split("~")
    except Exception:
        return None
    if len(fields) < 47 or not fields[1]:
        return None
    price = _f(fields[3])
    if not price:
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


async def fetch_stock_financials(code: str, periods: int = 4) -> list[dict]:
    """最近几期业绩报表（东方财富），最新在前。"""
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(
                "https://datacenter-web.eastmoney.com/api/data/v1/get",
                params={
                    "reportName": "RPT_LICO_FN_CPD", "columns": "ALL",
                    "filter": f'(SECURITY_CODE="{plain_code(code)}")',
                    "pageSize": max(1, min(int(periods), 12)),
                    "sortColumns": "REPORTDATE", "sortTypes": -1,
                },
            )
        rows = (resp.json().get("result") or {}).get("data") or []
    except Exception:
        return []

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


async def fetch_stock_profile(code: str) -> dict | None:
    """所属行业、上市板块、市值。

    行业取自东方财富业绩报表里的板块归属（它的行情接口 push2 经常直接断开连接，不能依赖），
    市值取自腾讯行情。两边都取不到才返回 None。
    """
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
