"""资金与筹码：钱往哪走、票在谁手里、内部人在干什么。

数据来自东方财富数据中心（和财务、估值同一个来源）与新浪的资金流向。每个函数只做取数和换算单位，
取不到返回空 —— 由工具层如实告诉模型"没取到"，不拿默认值顶替。

两家对"主力"的口径不一样，所以分开标注、不混着算：
- 新浪：按单笔成交金额分特大单 / 大单 / 小单 / 散单；"净流入"是全部主动买入减主动卖出。
- 东方财富：主力 = 超大单 + 大单。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

from wealthpilot.services import cache, sources
from wealthpilot.services.assets import sina_symbol
from wealthpilot.services.sources import SourceError
from wealthpilot.services.stocks import (
    _HEADERS,
    SLOW,
    _r,
    datacenter,
    fetch_stock_kline,
    plain_code,
)

_SINA_FLOW = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
_SINA_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://vip.stock.finance.sina.com.cn/"}


def _day(value) -> str:
    return str(value or "")[:10]


def _yi(value, digits: int = 2):
    """元 → 亿元。"""
    return round(value / 1e8, digits) if isinstance(value, (int, float)) else None


def _wan(value, digits: int = 2):
    """股（或元） → 万。"""
    return round(value / 1e4, digits) if isinstance(value, (int, float)) else None


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _code_filter(code: str, field: str = "SECURITY_CODE") -> str:
    return f'({field}="{plain_code(code)}")'


# ── 资金流向 ────────────────────────────────────────────

async def _sina_json(path: str, params: dict):
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_SINA_HEADERS) as client:
            resp = await client.get(f"{_SINA_FLOW}/{path}", params=params)
        return resp.json() if resp.status_code == 200 else None
    except Exception:  # noqa: BLE001 — 取不到就是取不到
        return None


async def fetch_fund_flow(code: str, days: int = 30) -> dict | None:
    """近 N 个交易日的资金净流入（新浪口径），加上最近一个交易日按单子大小的拆分与主力成本（东方财富口径）。"""
    symbol = sina_symbol(code)

    async def load():
        history, today, em = await asyncio.gather(
            _sina_json("MoneyFlow.ssl_qsfx_zjlrqs", {"page": 1, "num": max(5, min(days, 120)), "sort": "opendate", "asc": 0, "daima": symbol}),
            _sina_json("MoneyFlow.ssi_ssfx_flzjtj", {"daima": symbol}),
            datacenter("RPT_DMSK_TS_STOCKNEW", filter=_code_filter(code), page_size=1),
        )
        rows = [{
            "date": r.get("opendate", ""), "close": _f(r.get("trade")),
            "change_pct": _r((_f(r.get("changeratio")) or 0) * 100),
            "net_yi": _yi(_f(r.get("netamount"))), "net_ratio_pct": _r((_f(r.get("ratioamount")) or 0) * 100),
            "xlarge_net_yi": _yi(_f(r.get("r0_net"))),
        } for r in history or [] if isinstance(r, dict) and r.get("opendate")]
        out: dict = {"daily": rows}
        if isinstance(today, dict) and today.get("r0_in") is not None:
            def bucket(key: str) -> dict:
                buy, sell = _f(today.get(f"{key}_in")) or 0, _f(today.get(f"{key}_out")) or 0
                return {"buy_yi": _yi(buy), "sell_yi": _yi(sell), "net_yi": _yi(buy - sell)}
            out["breakdown"] = {"特大单": bucket("r0"), "大单": bucket("r1"), "小单": bucket("r2"), "散单": bucket("r3")}
        em_rows = em[0] if isinstance(em, tuple) else []
        if em_rows:
            e = em_rows[0]
            out["main"] = {
                "date": _day(e.get("TRADE_DATE")), "main_net_yi": _yi(e.get("PRIME_INFLOW")),
                "xlarge_net_yi": _yi((e.get("SUPERDEAL_INFLOW") or 0) - (e.get("SUPERDEAL_OUTFLOW") or 0)),
                "large_net_yi": _yi((e.get("BIGDEAL_INFLOW") or 0) - (e.get("BIGDEAL_OUTFLOW") or 0)),
                "main_cost": _r(e.get("PRIME_COST")), "main_cost_20d": _r(e.get("PRIME_COST_20DAYS")),
                "main_cost_60d": _r(e.get("PRIME_COST_60DAYS")), "close": e.get("CLOSE_PRICE"),
            }
        return out if rows or "main" in out else None

    return await cache.resilient(f"flow:{plain_code(code)}:{days}", 10 * cache.MINUTE, load, keep=3 * cache.DAY, what=f"{plain_code(code)} 的资金流向")


def summarize_flow(flow: dict) -> dict:
    """把逐日数据收成几句能直接引用的话：近 5 / 10 / 20 日累计净流入，连续流入或流出了几天。"""
    daily = flow.get("daily") or []
    out: dict = {"as_of": daily[0]["date"] if daily else (flow.get("main") or {}).get("date", "")}
    for n in (5, 10, 20):
        window = [d["net_yi"] for d in daily[:n] if d["net_yi"] is not None]
        if len(window) == n:
            out[f"net_{n}d_yi"] = round(sum(window), 2) + 0.0   # 加 0.0 是为了不出现 -0.0
    streak = 0
    for d in daily:
        if d["net_yi"] is None or d["net_yi"] == 0 or (streak and (d["net_yi"] > 0) != (streak > 0)):
            break
        streak += 1 if d["net_yi"] > 0 else -1
    out["streak_days"] = streak   # 正数：连续净流入的天数；负数：连续净流出
    return out


# ── 融资融券 ────────────────────────────────────────────

async def fetch_margin(code: str, days: int = 60) -> list[dict]:
    """逐日融资融券，最新在前。不是两融标的的股票没有数据。

    先问东方财富（一次给全，带融资余额占流通市值的比例）；不通时直接问交易所 —— 两融数据本来就是交易所每天公布的。
    交易所的那份没有收盘价和占比，深交所一天一个请求，所以只取最近一个月。
    """
    days = max(5, min(days, 250))

    async def eastmoney():
        rows, _ = await datacenter("RPTA_WEB_RZRQ_GGMX", filter=_code_filter(code, "SCODE"), page_size=days, sort="DATE", strict=True)
        return [{
            "date": _day(r.get("DATE")), "close": r.get("SPJ"),
            "financing_balance_yi": _yi(r.get("RZYE")), "financing_buy_yi": _yi(r.get("RZMRE")),
            "financing_net_buy_yi": _yi(r.get("RZJME")), "short_balance_yi": _yi(r.get("RQYE"), 4),
            "financing_to_float_mv_pct": _r(r.get("RZYEZB")),
        } for r in rows]

    async def load():
        plain = plain_code(code)
        exchange = [("exchange", lambda: _margin_sse(plain, days))] if plain.startswith(("6", "5")) else \
                   [("exchange", lambda: _margin_szse(plain, min(days, 21)))] if plain.startswith(("0", "3", "1")) else []
        rows, _ = await sources.first([("eastmoney", eastmoney), *exchange])
        return rows or []
    return await cache.resilient(f"margin:{plain_code(code)}:{days}", 2 * cache.HOUR, load, keep=14 * cache.DAY, what=f"{plain_code(code)} 的融资融券") or []


async def _margin_sse(plain: str, days: int, today: date | None = None) -> list[dict]:
    """上海证券交易所公布的融资融券明细：一个请求给一段日期。金额原始单位是元。"""
    today = today or date.today()
    params = {"isPagination": "true", "tabType": "mxtype", "detailsDate": "", "stockCode": plain,
              "beginDate": (today - timedelta(days=int(days * 1.6) + 10)).strftime("%Y%m%d"), "endDate": today.strftime("%Y%m%d"),
              "pageHelp.pageSize": str(days + 5), "pageHelp.pageNo": "1"}
    async with httpx.AsyncClient(timeout=12.0, headers={**_HEADERS, "Referer": "http://www.sse.com.cn/market/othersdata/margin/detail/"}) as client:
        resp = await client.get("http://query.sse.com.cn/marketdata/tradedata/queryMargin.do", params=params)
    try:
        items = resp.json()["pageHelp"]["data"]
    except (ValueError, KeyError, TypeError) as e:
        raise SourceError(f"上交所融资融券返回 {resp.status_code}，不是预期的结构") from e
    out = []
    for r in items or []:
        day, balance = str(r.get("opDate") or ""), r.get("rzye")
        if len(day) != 8 or not isinstance(balance, (int, float)):
            continue
        buy, repay = r.get("rzmre"), r.get("rzche")
        out.append({"date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "close": None, "financing_balance_yi": _yi(balance), "financing_buy_yi": _yi(buy),
                    "financing_net_buy_yi": _yi(buy - repay) if isinstance(buy, (int, float)) and isinstance(repay, (int, float)) else None,
                    "short_balance_yi": _yi(r.get("rqylje"), 4), "financing_to_float_mv_pct": None, "source": "上海证券交易所"})
    if items and not out:
        raise SourceError("上交所融资融券的字段变了：找不到 opDate / rzye")
    return sorted(out, key=lambda r: r["date"], reverse=True)[:days]


async def _margin_szse(plain: str, days: int) -> list[dict]:
    """深圳证券交易所公布的融资融券明细：一天一个请求，所以先用日线拿到最近的交易日，再逐日取。"""
    bars = await fetch_stock_kline(plain, days + 1)
    dates = [b["nav_date"] for b in bars][1:days + 1] or [b["nav_date"] for b in bars][:days]     # 当天的两融第二天早上才公布：从上一个交易日起
    if not dates:
        raise SourceError("拿不到最近的交易日，没法逐日问深交所")
    gate = asyncio.Semaphore(4)

    def number(text) -> float | None:
        return _f(str(text or "").replace(",", ""))

    async def one(client: httpx.AsyncClient, day: str) -> dict | None:
        async with gate:
            resp = await client.get("https://www.szse.cn/api/report/ShowReport/data", params={
                "SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "txtDate": day, "tab2PAGENO": "1", "TABKEY": "tab2", "txtZqdm": plain})
        try:
            table = next(t for t in resp.json() if t["metadata"]["tabkey"] == "tab2")
        except (ValueError, KeyError, TypeError, StopIteration) as e:
            raise SourceError(f"深交所融资融券返回 {resp.status_code}，不是预期的结构") from e
        row = next((r for r in table.get("data") or [] if r.get("zqdm") == plain), None)
        if row is None:
            return None                               # 那天它不是两融标的，或者还没公布
        if "jrrzye" not in row:
            raise SourceError("深交所融资融券的字段变了：找不到 jrrzye")
        short = number(row.get("jrrjye"))             # 万元
        return {"date": day, "close": None, "financing_balance_yi": number(row.get("jrrzye")), "financing_buy_yi": number(row.get("jrrzmr")),
                "financing_net_buy_yi": None, "short_balance_yi": round(short / 1e4, 4) if short is not None else None,
                "financing_to_float_mv_pct": None, "source": "深圳证券交易所"}

    async with httpx.AsyncClient(timeout=12.0, headers={**_HEADERS, "Referer": "https://www.szse.cn/disclosure/margin/margin/index.html"}) as client:
        rows = await asyncio.gather(*(one(client, day) for day in dates))
    return sorted((r for r in rows if r), key=lambda r: r["date"], reverse=True)


def summarize_margin(rows: list[dict]) -> dict:
    latest = rows[0]
    out = {"as_of": latest["date"], "financing_balance_yi": latest["financing_balance_yi"],
           "short_balance_yi": latest["short_balance_yi"], "financing_to_float_mv_pct": latest["financing_to_float_mv_pct"]}
    for n in (5, 20, 60):
        if len(rows) > n and rows[n]["financing_balance_yi"]:
            out[f"financing_balance_change_{n}d_pct"] = round((latest["financing_balance_yi"] / rows[n]["financing_balance_yi"] - 1) * 100, 2)
    return out


# ── 股东与机构 ──────────────────────────────────────────

async def fetch_holder_counts(code: str, periods: int = 8) -> list[dict]:
    """股东户数，最新在前。户数减少、户均持股上升，通常说明筹码在集中。"""
    async def load():
        rows, _ = await datacenter("RPT_HOLDERNUM_DET", filter=_code_filter(code), page_size=max(2, min(periods, 20)), sort="END_DATE")
        return [{
            "end_date": _day(r.get("END_DATE")), "holders": r.get("HOLDER_NUM"), "change_pct": _r(r.get("HOLDER_NUM_RATIO")),
            "avg_shares": _r(r.get("AVG_HOLD_NUM"), 0), "avg_value_wan": _wan(r.get("AVG_MARKET_CAP")),
            "price_change_pct": _r(r.get("INTERVAL_CHRATE")), "close": r.get("CLOSE_PRICE"), "notice_date": _day(r.get("HOLD_NOTICE_DATE")),
        } for r in rows]
    return await cache.resilient(f"holders:{plain_code(code)}:{periods}", cache.DAY, load, keep=SLOW, what=f"{plain_code(code)} 的股东户数") or []


async def fetch_top_holders(code: str) -> dict | None:
    """最新一期的十大流通股东。"""
    async def load():
        rows, _ = await datacenter("RPT_F10_EH_FREEHOLDERS", filter=_code_filter(code), page_size=20, sort="END_DATE")
        if not rows:
            return None
        latest = rows[0].get("END_DATE")
        top = sorted((r for r in rows if r.get("END_DATE") == latest), key=lambda r: r.get("HOLDER_RANK") or 99)
        return {"end_date": _day(latest), "report": top[0].get("REPORT_DATE_NAME") or "", "holders": [{
            "rank": r.get("HOLDER_RANK"), "name": r.get("HOLDER_NAME") or "", "type": r.get("HOLDER_TYPE") or "",
            "shares_wan": _wan(r.get("HOLD_NUM")), "float_ratio_pct": _r(r.get("FREE_HOLDNUM_RATIO")),
            # 接口里"变动"一列有时是文字（不变 / 新进），有时是股数
            "change": r.get("HOLDNUM_CHANGE_NAME") or str(r.get("HOLD_NUM_CHANGE") or ""),
            "change_shares_wan": _wan(_f(r.get("HOLD_NUM_CHANGE"))),
        } for r in top[:10]]}
    return await cache.resilient(f"topholders:{plain_code(code)}", cache.DAY, load, keep=SLOW, what=f"{plain_code(code)} 的十大流通股东")


async def fetch_institutions(code: str) -> dict | None:
    """各类机构（基金、社保、QFII、保险、券商…）最近两期的持仓合计。"""
    async def load():
        rows, _ = await datacenter("RPT_MAIN_ORGHOLD", filter=_code_filter(code), page_size=40, sort="REPORT_DATE")
        if not rows:
            return None
        dates = sorted({r.get("REPORT_DATE") for r in rows if r.get("REPORT_DATE")}, reverse=True)[:2]

        def period(day) -> dict:
            items = [{
                "type": r.get("ORG_TYPE_NAME") or "", "count": r.get("HOULD_NUM"), "shares_wan": _wan(r.get("TOTAL_SHARES")),
                "float_ratio_pct": _r(r.get("FREESHARES_RATIO")), "value_yi": _yi(r.get("HOLD_VALUE")),
                "change": r.get("HOLDCHA") or "", "change_shares_wan": _wan(r.get("HOLDCHA_NUM")),
            } for r in rows if r.get("REPORT_DATE") == day and r.get("ORG_TYPE_NAME")]
            return {"report_date": _day(day), "by_type": sorted(items, key=lambda i: -(i["float_ratio_pct"] or 0))}
        return {"latest": period(dates[0]), "previous": period(dates[1]) if len(dates) > 1 else None}
    return await cache.resilient(f"orghold:{plain_code(code)}", cache.DAY, load, keep=SLOW, what=f"{plain_code(code)} 的机构持仓")


async def fetch_northbound(code: str, periods: int = 4) -> list[dict]:
    """北向（沪深股通）持股。2024 年 8 月起交易所只按季度披露，所以是季末数据。"""
    async def load():
        rows, _ = await datacenter("RPT_MUTUAL_HOLDSTOCKNORTH_STA", filter=_code_filter(code), page_size=max(1, periods), sort="TRADE_DATE")
        return [{"date": _day(r.get("TRADE_DATE")), "shares_wan": _wan(r.get("HOLD_SHARES")), "value_yi": _yi(r.get("HOLD_MARKET_CAP")),
                 "float_ratio_pct": _r(r.get("FREE_SHARES_RATIO"))} for r in rows]
    return await cache.resilient(f"north:{plain_code(code)}:{periods}", cache.DAY, load, keep=SLOW, what=f"{plain_code(code)} 的北向持股") or []


# ── 内部人与大额交易 ────────────────────────────────────

async def fetch_holder_trades(code: str, limit: int = 8) -> list[dict]:
    """重要股东增减持。"""
    rows, _ = await datacenter("RPT_SHARE_HOLDER_INCREASE", filter=_code_filter(code), page_size=limit, sort="NOTICE_DATE")
    return [{
        "notice_date": _day(r.get("NOTICE_DATE")), "holder": r.get("HOLDER_NAME") or "", "direction": r.get("DIRECTION") or "",
        "shares_wan": _r(r.get("CHANGE_NUM")), "float_ratio_pct": _r(r.get("CHANGE_FREE_RATIO"), 4),
        "avg_price": _r(r.get("TRADE_AVERAGE_PRICE")), "start": _day(r.get("START_DATE")), "end": _day(r.get("END_DATE")),
        "holding_after_pct": _r(r.get("HOLD_RATIO")),
    } for r in rows]


async def fetch_executive_trades(code: str, limit: int = 8) -> list[dict]:
    """董监高及其亲属的持股变动。"""
    rows, _ = await datacenter("RPT_EXECUTIVE_HOLD_DETAILS", filter=_code_filter(code), page_size=limit, sort="CHANGE_DATE")
    return [{
        "date": _day(r.get("CHANGE_DATE")), "person": r.get("PERSON_NAME") or "", "position": r.get("POSITION_NAME") or "",
        "relation": r.get("PERSON_DSE_RELATION") or "", "shares": r.get("CHANGE_SHARES"), "avg_price": _r(r.get("AVERAGE_PRICE")),
        "amount_wan": _wan(r.get("CHANGE_AMOUNT")), "reason": r.get("CHANGE_REASON") or "",
    } for r in rows]


async def fetch_buybacks(code: str, limit: int = 3) -> list[dict]:
    rows, _ = await datacenter("RPTA_WEB_GETHGLIST_NEW", filter=_code_filter(code, "DIM_SCODE"), page_size=limit, sort="DIM_DATE")
    return [{
        "notice_date": _day(r.get("DIM_DATE")), "amount_lower_yi": _yi(r.get("REPURAMOUNTLOWER")), "amount_upper_yi": _yi(r.get("REPURAMOUNTLIMIT")),
        "price_cap": _r(r.get("REPURPRICECAP")), "start": _day(r.get("REPURSTARTDATE")), "end": _day(r.get("REPURENDDATE")),
        "finished": _day(r.get("FINISHDATE")), "purpose": (r.get("REPUROBJECTIVE") or "")[:120],
    } for r in rows]


async def fetch_unlocks(code: str, months_ahead: int = 12) -> list[dict]:
    """限售股解禁：未来一年要解禁的，加上最近已经解禁的一批。"""
    rows, _ = await datacenter("RPT_LIFT_STAGE", filter=_code_filter(code), page_size=20, sort="FREE_DATE")
    today, horizon = str(date.today()), str(date.today() + timedelta(days=31 * months_ahead))
    items = [{
        "date": _day(r.get("FREE_DATE")), "type": r.get("FREE_SHARES_TYPE") or "",
        "shares_wan": _r(r.get("ABLE_FREE_SHARES")), "value_yi": _wan(r.get("ALIFT_MARKET_CAP")),
        # FREE_RATIO 是占解禁前流通股的比例（小数）
        "float_ratio_pct": _r((r.get("FREE_RATIO") or 0) * 100) if isinstance(r.get("FREE_RATIO"), (int, float)) else None,
        "total_ratio_pct": _r((r.get("TOTAL_RATIO") or 0) * 100) if isinstance(r.get("TOTAL_RATIO"), (int, float)) else None,
        "upcoming": _day(r.get("FREE_DATE")) >= today,
    } for r in rows]
    upcoming = sorted((i for i in items if i["upcoming"] and i["date"] <= horizon), key=lambda i: i["date"])
    past = [i for i in items if not i["upcoming"]][:1]
    return upcoming + past


async def fetch_block_trades(code: str, limit: int = 8) -> list[dict]:
    rows, _ = await datacenter("RPT_DATA_BLOCKTRADE", filter=_code_filter(code), page_size=limit, sort="TRADE_DATE")
    return [{
        "date": _day(r.get("TRADE_DATE")), "price": r.get("DEAL_PRICE"), "close": r.get("CLOSE_PRICE"),
        "premium_pct": _r((r.get("PREMIUM_RATIO") or 0) * 100), "amount_yi": _yi(r.get("DEAL_AMT"), 4),
        "buyer": r.get("BUYER_NAME") or "", "seller": r.get("SELLER_NAME") or "",
    } for r in rows]


async def fetch_billboard(code: str, limit: int = 5) -> list[dict]:
    """龙虎榜上榜记录。大盘股很少上榜，查不到是常态。"""
    rows, _ = await datacenter("RPT_DAILYBILLBOARD_DETAILSNEW", filter=_code_filter(code), page_size=limit, sort="TRADE_DATE")
    return [{
        "date": _day(r.get("TRADE_DATE")), "reason": r.get("EXPLANATION") or "", "change_pct": _r(r.get("CHANGE_RATE")),
        "net_buy_yi": _yi(r.get("BILLBOARD_NET_AMT")), "summary": r.get("EXPLAIN") or "",
    } for r in rows]
