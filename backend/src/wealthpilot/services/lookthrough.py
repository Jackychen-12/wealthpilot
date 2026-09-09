"""持仓穿透 — 从基金层下沉到个股层。

此前相关性只算到净值层（Pearson），那是**结果相关性**：两只基金同涨同跌，
但说不出为什么。穿透到重仓股之后才能回答"因为你这两只基金重仓股重叠 7 只、
合计权重 41%"这类真正有解释力的判断。

数据来自东财 f10 的季报持仓明细。AKShare 的 fund_portfolio_hold_em 在当前
上游格式下已解析失败，因此直接走 HTTP + 正则解析。

**口径警告**：季报只披露前十大重仓股，且滞后 1–3 个月。所以穿透结果是
"部分持仓的旧快照"，不是实时全持仓 —— 每个返回值都带 report_date 与
coverage_pct，调用方必须把它呈现出来，不能当成当前真实暴露。
"""

from __future__ import annotations

import re

import httpx

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.market_data import EM_HEADERS
from wealthpilot.services.simulation import portfolio_weights

_F10_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"截止至：<font[^>]*>([^<]+)</font>")
_BOX_RE = re.compile(r"<div class='boxitem[^']*'>(.*?)(?=<div class='boxitem|$)", re.S)


def parse_holdings_html(text: str) -> dict:
    """解析东财 f10 返回的 JS 包裹 HTML，取**最近一期**季报的重仓股。

    单独抽出来是为了能脱网单测 —— 网络那层只负责把字符串取回来。
    """
    dates = _DATE_RE.findall(text)
    boxes = _BOX_RE.findall(text)
    if not boxes:
        return {"report_date": "", "stocks": [], "coverage_pct": 0.0}

    # 页面按季度倒序排列，第一个 box 即最近一期
    block, report_date = boxes[0], (dates[0] if dates else "")

    stocks: list[dict] = []
    for row in _ROW_RE.findall(block):
        cells = [_TAG_RE.sub("", c).strip() for c in _CELL_RE.findall(row)]
        if len(cells) < 7:
            continue
        code, name, weight_raw = cells[1], cells[2], cells[6]
        if not code or not weight_raw.endswith("%"):
            continue
        try:
            weight = float(weight_raw.rstrip("%"))
        except ValueError:
            continue
        stocks.append({"stock_code": code, "stock_name": name, "weight_pct": weight})

    return {
        "report_date": report_date,
        "stocks": stocks,
        "coverage_pct": round(sum(s["weight_pct"] for s in stocks), 2),
    }


async def fetch_fund_holdings(fund_code: str, year: int | str = "") -> dict:
    """拉取某只基金最近一期季报重仓股。失败时返回空结构而非抛错。"""
    params = {"type": "jjcc", "code": fund_code, "topline": 10}
    if year:
        params["year"] = str(year)
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                _F10_URL,
                params=params,
                headers={**EM_HEADERS, "Referer": "https://fundf10.eastmoney.com/"},
            )
            resp.raise_for_status()
            parsed = parse_holdings_html(resp.text)
    except Exception:
        parsed = {"report_date": "", "stocks": [], "coverage_pct": 0.0}

    parsed["fund_code"] = fund_code
    return parsed


# ══════════════════════════════════════════════════════════
# 纯计算部分（可完整单测）
# ══════════════════════════════════════════════════════════


def overlap_between(a: dict, b: dict) -> dict:
    """两只基金的重仓股重叠。

    combined_weight 取两侧权重的**较小值**之和 —— 表示"同一批股票上，
    两只基金共同承担的最小暴露"，比取平均或求和更保守也更好解释。
    """
    a_map = {s["stock_code"]: s for s in a.get("stocks", [])}
    b_map = {s["stock_code"]: s for s in b.get("stocks", [])}
    shared_codes = sorted(set(a_map) & set(b_map))

    shared = []
    for code in shared_codes:
        wa, wb = a_map[code]["weight_pct"], b_map[code]["weight_pct"]
        shared.append({
            "stock_code": code,
            "stock_name": a_map[code]["stock_name"],
            "weight_a": wa,
            "weight_b": wb,
            "min_weight": round(min(wa, wb), 2),
        })

    return {
        "fund_a": a.get("fund_code", ""),
        "fund_b": b.get("fund_code", ""),
        "shared_count": len(shared),
        "combined_weight_pct": round(sum(s["min_weight"] for s in shared), 2),
        "shared_stocks": shared,
        "report_dates": {
            a.get("fund_code", "a"): a.get("report_date", ""),
            b.get("fund_code", "b"): b.get("report_date", ""),
        },
    }


def aggregate_exposure(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    fund_holdings: dict[str, dict],
) -> dict:
    """把组合穿透到个股层，汇总真实暴露。

    个股暴露 = Σ（该基金在组合中的权重 × 该股在该基金中的权重）。
    """
    fund_weights = portfolio_weights(holdings, nav_data)
    if not fund_weights:
        return {"stocks": [], "covered_fund_count": 0, "note": "当前没有持仓"}

    exposure: dict[str, dict] = {}
    covered = 0
    report_dates: dict[str, str] = {}
    coverage_by_fund: dict[str, float] = {}

    for code, fw in fund_weights.items():
        data = fund_holdings.get(code)
        if not data or not data.get("stocks"):
            continue
        covered += 1
        report_dates[code] = data.get("report_date", "")
        coverage_by_fund[code] = data.get("coverage_pct", 0.0)

        for s in data["stocks"]:
            e = exposure.setdefault(
                s["stock_code"],
                {"stock_code": s["stock_code"], "stock_name": s["stock_name"],
                 "exposure_pct": 0.0, "via_funds": []},
            )
            e["exposure_pct"] += fw * s["weight_pct"]
            e["via_funds"].append({"fund_code": code, "weight_pct": s["weight_pct"]})

    stocks = sorted(exposure.values(), key=lambda x: -x["exposure_pct"])
    for s in stocks:
        s["exposure_pct"] = round(s["exposure_pct"], 3)
        s["held_by_funds"] = len(s["via_funds"])

    multi = [s for s in stocks if s["held_by_funds"] > 1]

    return {
        "stocks": stocks,
        "top_exposure": stocks[:10],
        "multi_fund_stocks": multi,
        "multi_fund_exposure_pct": round(sum(s["exposure_pct"] for s in multi), 3),
        "covered_fund_count": covered,
        "total_fund_count": len(fund_weights),
        "report_dates": report_dates,
        "coverage_by_fund": coverage_by_fund,
        "note": (
            "季报仅披露前十大重仓股且滞后 1-3 个月，以上为部分持仓的旧快照，"
            "不代表当前真实暴露。coverage_by_fund 表示各基金前十大合计占其净值的比例。"
        ),
    }


def summarize_overlap(exposure: dict) -> str:
    """把穿透结果压成一句可直接引用的话。"""
    multi = exposure.get("multi_fund_stocks", [])
    if not multi:
        return "各基金的前十大重仓股没有交集（按最近一期季报）。"
    names = "、".join(s["stock_name"] for s in multi[:5])
    more = f" 等 {len(multi)} 只" if len(multi) > 5 else ""
    return (
        f"有 {len(multi)} 只个股被多只基金同时重仓（{names}{more}），"
        f"合计穿透暴露 {exposure['multi_fund_exposure_pct']:.2f}%。"
    )
