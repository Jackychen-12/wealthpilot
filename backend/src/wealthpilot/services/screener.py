"""全市场快照与选股。

快照 = 某个交易日全部 A 股的估值（PE / PB / 市值 / 涨跌幅 / 行业）+ 最近一期业绩（ROE / 营收与净利同比）。
一天拉一次、落本地缓存；筛选、板块排行、市场宽度、名称 → 代码索引都从这一份快照里算，
不各自去打接口。筛选是确定性的代码逻辑：条件可以由模型来填，结果由这里出。
"""

from __future__ import annotations

import asyncio
from datetime import date

from wealthpilot.services.cache import DAY, cached
from wealthpilot.services.stocks import datacenter

BENCHMARK = "510300"
_PAGE = 500
_VALUATION_COLUMNS = "SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_NAME,TOTAL_MARKET_CAP,CLOSE_PRICE,CHANGE_RATE,PE_TTM,PB_MRQ,PS_TTM"
_REPORT_COLUMNS = "SECURITY_CODE,WEIGHTAVG_ROE,YSTZ,SJLTZ,REPORTDATE"


async def _all_pages(report: str, filter_: str, columns: str, sort: str) -> list[dict]:
    first, pages = await datacenter(report, filter=filter_, columns=columns, page_size=_PAGE, sort=sort, desc=False)
    if pages <= 1:
        return first
    rest = await asyncio.gather(*[
        datacenter(report, filter=filter_, columns=columns, page_size=_PAGE, page=p, sort=sort, desc=False)
        for p in range(2, pages + 1)
    ])
    return first + [row for rows, _ in rest for row in rows]


def _recent_quarter_ends(today: date, n: int = 4) -> list[str]:
    ends = []
    year, quarter = today.year, (today.month - 1) // 3  # 已结束的最近一个季度
    while len(ends) < n:
        if quarter == 0:
            year, quarter = year - 1, 4
        ends.append(f"{year}-{['03-31', '06-30', '09-30', '12-31'][quarter - 1]}")
        quarter -= 1
    return ends


def annualized_roe(fin: dict) -> float | None:
    """报表里的 ROE 是年初至报告期末的累计值：一季报的 4% 和年报的 16% 是一回事。
    筛选"ROE ≥ 15"指的是全年水平，所以按报告期简单年化（一季报×4、中报×2、三季报×4/3）。"""
    roe, report = fin.get("WEIGHTAVG_ROE"), str(fin.get("REPORTDATE") or "")
    if not isinstance(roe, (int, float)) or len(report) < 7:
        return None
    quarter = {"03": 1, "06": 2, "09": 3, "12": 4}.get(report[5:7])
    return round(roe * 4 / quarter, 2) if quarter else None


async def _load_snapshot() -> dict:
    latest, _ = await datacenter("RPT_VALUEANALYSIS_DET", filter='(SECURITY_CODE="000001")',
                                 columns="TRADE_DATE", page_size=1, sort="TRADE_DATE")
    if not latest:
        return {}
    trade_date = str(latest[0]["TRADE_DATE"])[:10]
    valuation = await _all_pages("RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{trade_date}')",
                                 _VALUATION_COLUMNS, "SECURITY_CODE")
    if len(valuation) < 1000:
        return {}  # 没取全就不落缓存，免得用半份数据筛一整天

    # 业绩：从最近的季度往回找第一个"多数公司已披露"的报告期
    report_date, reports = "", []
    for candidate in _recent_quarter_ends(date.fromisoformat(trade_date)):
        rows = await _all_pages("RPT_LICO_FN_CPD", f"(REPORTDATE='{candidate}')", _REPORT_COLUMNS, "SECURITY_CODE")
        if len(rows) >= len(valuation) * 0.6:
            report_date, reports = candidate, rows
            break
    by_code = {r["SECURITY_CODE"]: r for r in reports}

    def r2(v):
        return round(v, 2) if isinstance(v, (int, float)) else None

    stocks = []
    for v in valuation:
        fin = by_code.get(v["SECURITY_CODE"], {})
        stocks.append({
            "code": v["SECURITY_CODE"], "name": v.get("SECURITY_NAME_ABBR") or "",
            "industry": v.get("BOARD_NAME") or "",
            "price": v.get("CLOSE_PRICE"), "change_pct": r2(v.get("CHANGE_RATE")),
            "total_mv_yi": r2((v.get("TOTAL_MARKET_CAP") or 0) / 1e8),
            "pe_ttm": r2(v.get("PE_TTM")), "pb": r2(v.get("PB_MRQ")), "ps_ttm": r2(v.get("PS_TTM")),
            "roe_pct": r2(fin.get("WEIGHTAVG_ROE")), "roe_annual_pct": annualized_roe(fin),
            "revenue_yoy_pct": r2(fin.get("YSTZ")), "profit_yoy_pct": r2(fin.get("SJLTZ")),
        })
    return {"trade_date": trade_date, "report_date": report_date, "stocks": stocks}


async def snapshot() -> dict:
    """当日全市场快照；取不到返回 {}。"""
    return await cached("market_snapshot", DAY / 2, _load_snapshot) or {}


# 筛选条件：字段 → (快照里的键, 比较方向)
_RANGES = {
    "pe_min": ("pe_ttm", ">="), "pe_max": ("pe_ttm", "<="), "pb_min": ("pb", ">="), "pb_max": ("pb", "<="),
    "mv_min_yi": ("total_mv_yi", ">="), "mv_max_yi": ("total_mv_yi", "<="),
    "roe_min": ("roe_annual_pct", ">="), "revenue_yoy_min": ("revenue_yoy_pct", ">="),
    "profit_yoy_min": ("profit_yoy_pct", ">="),
    "change_min": ("change_pct", ">="), "change_max": ("change_pct", "<="),
}
SORT_KEYS = ("total_mv_yi", "pe_ttm", "pb", "roe_pct", "roe_annual_pct", "revenue_yoy_pct", "profit_yoy_pct", "change_pct")


def _value(row: dict, field: str):
    # 旧缓存里的快照没有年化 ROE 这一列，退回累计值
    return row.get(field, row.get("roe_pct")) if field == "roe_annual_pct" else row.get(field)


def screen(snap: dict, criteria: dict) -> dict:
    """按条件筛选。条件里缺失的数据（如亏损股没有正的 PE）视为不满足该条件。"""
    rows = snap.get("stocks", [])
    applied: dict = {}
    if criteria.get("exclude_st", True):
        rows = [r for r in rows if "ST" not in r["name"].upper() and "退" not in r["name"]]
        applied["exclude_st"] = True
    industry = str(criteria.get("industry") or "").strip()
    if industry:
        rows = [r for r in rows if industry in r["industry"]]
        applied["industry"] = industry
    # 估值上限隐含"要求为正"：PE ≤ 20 不应把亏损股（负 PE）筛进来
    for key in ("pe_max", "pb_max"):
        if criteria.get(key) is not None:
            field = _RANGES[key][0]
            rows = [r for r in rows if r[field] is not None and r[field] > 0]
    for key, (field, op) in _RANGES.items():
        bound = criteria.get(key)
        if bound is None:
            continue
        bound = float(bound)
        applied[key] = bound
        rows = [r for r in rows if _value(r, field) is not None
                and (_value(r, field) >= bound if op == ">=" else _value(r, field) <= bound)]

    sort_by = criteria.get("sort_by") if criteria.get("sort_by") in SORT_KEYS else "total_mv_yi"
    descending = bool(criteria.get("descending", True))
    rows = sorted((r for r in rows if r[sort_by] is not None), key=lambda r: r[sort_by], reverse=descending)
    limit = max(1, min(int(criteria.get("limit", 20)), 100))
    return {
        "criteria": applied, "sort_by": sort_by, "descending": descending,
        "matched": len(rows), "shown": min(limit, len(rows)), "stocks": rows[:limit],
        "trade_date": snap.get("trade_date"), "report_date": snap.get("report_date"),
        "note": "估值与涨跌幅为 trade_date 当日数据；ROE 与同比增速取自 report_date 这一期业绩，是滞后数据。"
                "roe_pct 是报告期累计值，roe_annual_pct 是按报告期简单年化后的值，ROE 条件按年化值筛选",
    }


def sector_ranking(snap: dict, top: int = 10) -> dict:
    """行业涨跌排行：按成分股涨跌幅中位数。成分股少于 5 只的行业不参与排名。"""
    groups: dict[str, list[dict]] = {}
    for r in snap.get("stocks", []):
        if r["industry"] and r["change_pct"] is not None:
            groups.setdefault(r["industry"], []).append(r)
    sectors = []
    for name, members in groups.items():
        if len(members) < 5:
            continue
        changes = sorted(m["change_pct"] for m in members)
        leader = max(members, key=lambda m: m["change_pct"])
        sectors.append({
            "industry": name, "stock_count": len(members),
            "median_change_pct": changes[len(changes) // 2],
            "up_ratio_pct": round(sum(c > 0 for c in changes) / len(changes) * 100, 1),
            "leader": {"code": leader["code"], "name": leader["name"], "change_pct": leader["change_pct"]},
        })
    sectors.sort(key=lambda s: s["median_change_pct"], reverse=True)
    return {"trade_date": snap.get("trade_date"), "sector_count": len(sectors),
            "top": sectors[:top], "bottom": sectors[-top:][::-1],
            "method": "各行业成分股当日涨跌幅的中位数；up_ratio_pct 为上涨家数占比"}


def market_breadth(snap: dict) -> dict:
    changes = [r["change_pct"] for r in snap.get("stocks", []) if r["change_pct"] is not None]
    if not changes:
        return {}
    ordered = sorted(changes)
    return {
        "trade_date": snap.get("trade_date"), "stock_count": len(changes),
        "up": sum(c > 0 for c in changes), "down": sum(c < 0 for c in changes), "flat": sum(c == 0 for c in changes),
        "median_change_pct": ordered[len(ordered) // 2],
        "limit_up_like": sum(c >= 9.8 for c in changes), "limit_down_like": sum(c <= -9.8 for c in changes),
    }


# ── 选股条件的历史回测 ──────────────────────────────────
# 每年三个调仓日，都在财报披露截止日（4/30、8/31、10/31）之后，保证当时能看到这些业绩
_REBALANCE_DAYS = ((5, 6), (9, 3), (11, 3))
_HIST_REPORT_COLUMNS = _REPORT_COLUMNS + ",NOTICE_DATE"
_FOREVER = 3650 * 86400.0


async def _trade_date_on_or_after(day: str) -> str:
    rows, _ = await datacenter("RPT_VALUEANALYSIS_DET", filter=f"(SECURITY_CODE=\"000001\")(TRADE_DATE>='{day}')",
                               columns="TRADE_DATE", page_size=1, sort="TRADE_DATE", desc=False)
    return str(rows[0]["TRADE_DATE"])[:10] if rows else ""


async def cross_section(day: str) -> dict:
    """某个历史交易日的全市场截面：当日估值 + 当时已经披露的最新一期业绩（按公告日判断，避免用到未来数据）。"""
    from wealthpilot.services import cache

    trade_date = await _trade_date_on_or_after(day)
    if not trade_date:
        return {}
    valuation = await cache.cached(f"xsec:val:{trade_date}", _FOREVER, lambda: _all_pages(
        "RPT_VALUEANALYSIS_DET", f"(TRADE_DATE='{trade_date}')", _VALUATION_COLUMNS, "SECURITY_CODE"))
    if not valuation or len(valuation) < 1000:
        return {}
    known: dict[str, dict] = {}
    # 从新到旧看最近三个报告期：每只股票取公告日不晚于调仓日的最新一期
    for report_date in _recent_quarter_ends(date.fromisoformat(trade_date), 3):
        rows = await cache.cached(f"xsec:fin:{report_date}", _FOREVER, lambda rd=report_date: _all_pages(
            "RPT_LICO_FN_CPD", f"(REPORTDATE='{rd}')", _HIST_REPORT_COLUMNS, "SECURITY_CODE"))
        for r in rows or []:
            if str(r.get("NOTICE_DATE") or "9999")[:10] <= trade_date:
                known.setdefault(r["SECURITY_CODE"], r)

    def r2(v):
        return round(v, 2) if isinstance(v, (int, float)) else None

    stocks = []
    for v in valuation:
        fin = known.get(v["SECURITY_CODE"], {})
        stocks.append({
            "code": v["SECURITY_CODE"], "name": v.get("SECURITY_NAME_ABBR") or "", "industry": v.get("BOARD_NAME") or "",
            "price": v.get("CLOSE_PRICE"), "change_pct": r2(v.get("CHANGE_RATE")),
            "total_mv_yi": r2((v.get("TOTAL_MARKET_CAP") or 0) / 1e8),
            "pe_ttm": r2(v.get("PE_TTM")), "pb": r2(v.get("PB_MRQ")), "ps_ttm": r2(v.get("PS_TTM")),
            "roe_pct": r2(fin.get("WEIGHTAVG_ROE")), "roe_annual_pct": annualized_roe(fin),
            "revenue_yoy_pct": r2(fin.get("YSTZ")), "profit_yoy_pct": r2(fin.get("SJLTZ")),
        })
    return {"trade_date": trade_date, "report_date": "", "stocks": stocks}


def rebalance_dates(today: date, years: float) -> list[str]:
    start = today.toordinal() - int(years * 365)
    days = [date(y, m, d) for y in range(today.year - int(years) - 1, today.year + 1) for m, d in _REBALANCE_DAYS]
    return [str(d) for d in days if start <= d.toordinal() < today.toordinal() - 20]


def _close_on(rows: list[dict], day: str) -> float | None:
    """day 当日或之前最近一个交易日的收盘价。rows 按日期升序。"""
    price = None
    for r in rows:
        if r["nav_date"] > day:
            break
        price = r["nav"]
    return price


async def backtest_screen(criteria: dict, years: float = 2, top_n: int = 20, fee_pct: float = 0.1,
                          today: date | None = None) -> dict:
    """把一组选股条件放回历史：每个调仓日按当时的数据筛出前 top_n 只，等权持有到下一个调仓日。"""
    from wealthpilot.services import cache
    from wealthpilot.services.stocks import fetch_stock_kline

    today = today or date.today()
    top_n = max(3, min(int(top_n), 30))
    dates = rebalance_dates(today, max(0.5, min(float(years), 2.5)))
    picks: list[tuple[str, list[dict]]] = []
    for day in dates:
        snap = await cross_section(day)
        if not snap:
            continue
        chosen = screen(snap, {**criteria, "limit": top_n})["stocks"]
        picks.append((snap["trade_date"], chosen))
    if len(picks) < 2:
        return {"error": "可用的历史调仓日不足两个，无法回测"}

    # 行情源对突发请求很敏感（一次上百只会被限流）：两路并发、每次间隔一下，当天取过的走缓存
    gate = asyncio.Semaphore(2)

    async def kline(code: str) -> list[dict]:
        async def load() -> list[dict]:
            async with gate:
                await asyncio.sleep(0.15)
                return await fetch_stock_kline(code, 640)

        rows = await cache.cached(f"bt:kline:{code}:{today}", cache.DAY, load)
        return sorted(rows or [], key=lambda r: r["nav_date"])

    codes = sorted({s["code"] for _, chosen in picks for s in chosen} | {BENCHMARK})
    series = dict(zip(codes, await asyncio.gather(*[kline(c) for c in codes]), strict=True))
    unadjusted = any(rows and rows[0].get("price_basis") == "不复权" for rows in series.values())
    if not series[BENCHMARK]:
        return {"error": "行情源暂时取不到历史价格（可能被限流），过一会儿再试"}
    last_day = series[BENCHMARK][-1]["nav_date"]

    periods, equity, bench_equity, peak, max_dd = [], 1.0, 1.0, 1.0, 0.0
    for i, (start, chosen) in enumerate(picks):
        end = picks[i + 1][0] if i + 1 < len(picks) else last_day
        returns, missing = [], 0
        for s in chosen:
            a, b = _close_on(series[s["code"]], start), _close_on(series[s["code"]], end)
            if a and b:
                returns.append((s, (b / a - 1) * 100))
            else:
                missing += 1
        ba, bb = _close_on(series[BENCHMARK], start), _close_on(series[BENCHMARK], end)
        if not ba or not bb or (chosen and not returns):
            periods.append({"start": start, "end": end, "picked": len(chosen), "return_pct": None, "benchmark_pct": None,
                            "no_price": missing, "top": []})
            continue
        # 当期没有符合条件的股票就空仓；否则每期全部换仓，买卖各收一次
        ret = sum(r for _, r in returns) / len(returns) - 2 * fee_pct if returns else 0.0
        bench = (bb / ba - 1) * 100
        equity *= 1 + ret / 100
        bench_equity *= 1 + bench / 100
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        best = sorted(returns, key=lambda x: -x[1])
        periods.append({"start": start, "end": end, "picked": len(chosen), "held": len(returns), "no_price": missing,
                        "return_pct": round(ret, 2), "benchmark_pct": round(bench, 2), "equity": round(equity, 4),
                        "benchmark_equity": round(bench_equity, 4),
                        "top": [{"code": s["code"], "name": s["name"], "return_pct": round(r, 2)} for s, r in best[:3]],
                        "bottom": [{"code": s["code"], "name": s["name"], "return_pct": round(r, 2)} for s, r in best[-2:]]})
    valid = [p for p in periods if p["return_pct"] is not None]
    if not valid:
        return {"error": "筛出的股票都取不到历史价格，无法回测"}
    span_years = max((date.fromisoformat(valid[-1]["end"]) - date.fromisoformat(valid[0]["start"])).days / 365, 0.1)
    return {
        "criteria": screen({"stocks": []}, criteria)["criteria"], "top_n": top_n, "fee_pct": fee_pct,
        "start": valid[0]["start"], "end": valid[-1]["end"], "periods": periods,
        "total_return_pct": round((equity - 1) * 100, 2), "benchmark_return_pct": round((bench_equity - 1) * 100, 2),
        "excess_return_pct": round((equity - bench_equity) * 100, 2),
        "annualized_pct": round((equity ** (1 / span_years) - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "periods_beating_benchmark": sum(1 for p in valid if p["return_pct"] > p["benchmark_pct"]), "period_count": len(valid),
        "benchmark": "沪深300ETF（510300）",
        "limitations": [
            f"只有 {len(valid)} 个持有期（免费日线最多回溯约 2.5 年），结果的偶然性很大，不能当作统计结论",
            "回撤只在调仓日之间逐期计算，期内的最大回撤会更大",
            "已退市或取不到历史价格的股票被剔除，结果偏乐观（幸存者偏差）",
            "ST 是按当时的名称剔除；涨跌停、停牌导致买不进卖不出的情况没有处理",
            f"等权持有、每期全部换仓，单边费率 {fee_pct}%；未计冲击成本",
            "历史表现不代表未来",
            *(["本次行情取自备用源（不复权价）：分红除权会被算成下跌，组合与基准的收益都偏低"] if unadjusted else []),
        ],
    }
