"""A 股个股 / ETF 数据：K 线、行情与估值、财务、公司概况。

全部走免费源，各有脾气：
    腾讯 K 线   前复权日线，回撤和回测必须用复权价，否则分红除权日会算出假的暴跌
    腾讯行情   一条请求带出价格、PE、PB、市值、换手率；GBK 编码，`~` 分隔
    东方财富   业绩报表（按报告期）与所属行业（数据中心接口；push2 行情接口不稳定，不用）

取不到一律返回空（[] / None），由工具层如实说"没取到"，不在这里编默认值。
"""

from __future__ import annotations

import asyncio
import json
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
        rows = []
    if not rows:
        # 主行情源对突发请求会临时限流；换东方财富的前复权日线，字段顺序整理成一致的
        rows = await _eastmoney_kline(symbol, days + 1)
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
    for host in ("push2his", "63.push2his", "7.push2his", "push2his"):
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
                resp = await client.get(f"https://{host}.eastmoney.com/api/qt/stock/kline/get", params=params)
            lines = (resp.json().get("data") or {}).get("klines") or []
            if lines:
                return [line.split(",") for line in lines]
        except Exception:
            await asyncio.sleep(0.3)
    return []


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


_DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"


async def datacenter(report: str, *, filter: str = "", columns: str = "ALL", page_size: int = 50,
                     page: int = 1, sort: str = "", desc: bool = True) -> tuple[list[dict], int]:
    """东方财富数据中心报表查询。返回 (行列表, 总页数)；失败返回 ([], 0)。"""
    params: dict = {"reportName": report, "columns": columns, "pageSize": page_size, "pageNumber": page}
    if filter:
        params["filter"] = filter
    if sort:
        params["sortColumns"] = sort
        params["sortTypes"] = -1 if desc else 1
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
            resp = await client.get(_DATACENTER, params=params)
        result = resp.json().get("result") or {}
        return result.get("data") or [], int(result.get("pages") or 0)
    except Exception:
        return [], 0


def _r(value, digits: int = 2):
    return round(value, digits) if isinstance(value, (int, float)) else None


async def fetch_valuation_history(code: str, years: int = 5) -> list[dict]:
    """每日 PE(TTM) / PB / PS 历史，最新在前。"""
    rows, _ = await datacenter(
        "RPT_VALUEANALYSIS_DET", filter=f'(SECURITY_CODE="{plain_code(code)}")',
        columns="TRADE_DATE,PE_TTM,PB_MRQ,PS_TTM,CLOSE_PRICE,TOTAL_MARKET_CAP,BOARD_NAME,ORIG_BOARD_CODE,SECURITY_NAME_ABBR",
        page_size=min(3000, max(60, years * 250)), sort="TRADE_DATE",
    )
    return [{
        "date": str(r.get("TRADE_DATE", ""))[:10], "pe_ttm": _r(r.get("PE_TTM")), "pb": _r(r.get("PB_MRQ")),
        "ps_ttm": _r(r.get("PS_TTM")), "close": r.get("CLOSE_PRICE"),
        "industry": r.get("BOARD_NAME") or "", "board_code": str(r.get("ORIG_BOARD_CODE") or ""),
        "name": r.get("SECURITY_NAME_ABBR") or "",
    } for r in rows]


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
    rows, _ = await datacenter(
        "RPT_F10_FINANCE_MAINFINADATA", filter=f'(SECURITY_CODE="{plain_code(code)}")',
        page_size=max(1, min(int(periods), 20)), sort="REPORT_DATE",
    )

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


async def fetch_dividends(code: str, limit: int = 8) -> list[dict]:
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
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(
                "https://np-anotice-stock.eastmoney.com/api/security/ann",
                params={"sr": -1, "page_size": max(1, min(limit, 30)), "page_index": 1, "ann_type": "A",
                        "client_source": "web", "stock_list": plain_code(code)},
            )
        items = (resp.json().get("data") or {}).get("list") or []
    except Exception:
        return []
    return [{
        "date": str(i.get("notice_date", ""))[:10], "title": i.get("title", ""),
        "url": f"https://data.eastmoney.com/notices/detail/{plain_code(code)}/{i.get('art_code', '')}.html",
    } for i in items]


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
