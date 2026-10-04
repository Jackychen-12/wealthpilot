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
            "roe_pct": r2(fin.get("WEIGHTAVG_ROE")), "revenue_yoy_pct": r2(fin.get("YSTZ")),
            "profit_yoy_pct": r2(fin.get("SJLTZ")),
        })
    return {"trade_date": trade_date, "report_date": report_date, "stocks": stocks}


async def snapshot() -> dict:
    """当日全市场快照；取不到返回 {}。"""
    return await cached("market_snapshot", DAY / 2, _load_snapshot) or {}


# 筛选条件：字段 → (快照里的键, 比较方向)
_RANGES = {
    "pe_min": ("pe_ttm", ">="), "pe_max": ("pe_ttm", "<="), "pb_min": ("pb", ">="), "pb_max": ("pb", "<="),
    "mv_min_yi": ("total_mv_yi", ">="), "mv_max_yi": ("total_mv_yi", "<="),
    "roe_min": ("roe_pct", ">="), "revenue_yoy_min": ("revenue_yoy_pct", ">="),
    "profit_yoy_min": ("profit_yoy_pct", ">="),
    "change_min": ("change_pct", ">="), "change_max": ("change_pct", "<="),
}
SORT_KEYS = ("total_mv_yi", "pe_ttm", "pb", "roe_pct", "revenue_yoy_pct", "profit_yoy_pct", "change_pct")


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
        rows = [r for r in rows if r[field] is not None and (r[field] >= bound if op == ">=" else r[field] <= bound)]

    sort_by = criteria.get("sort_by") if criteria.get("sort_by") in SORT_KEYS else "total_mv_yi"
    descending = bool(criteria.get("descending", True))
    rows = sorted((r for r in rows if r[sort_by] is not None), key=lambda r: r[sort_by], reverse=descending)
    limit = max(1, min(int(criteria.get("limit", 20)), 100))
    return {
        "criteria": applied, "sort_by": sort_by, "descending": descending,
        "matched": len(rows), "shown": min(limit, len(rows)), "stocks": rows[:limit],
        "trade_date": snap.get("trade_date"), "report_date": snap.get("report_date"),
        "note": "估值与涨跌幅为 trade_date 当日数据；ROE 与同比增速取自 report_date 这一期业绩（累计值），是滞后数据",
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
