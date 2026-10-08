"""宏观数据：景气、物价、货币信贷、利率。个股研究之外的那层背景。

都来自东方财富数据中心整理的官方口径（统计局、央行、中债、美国财政部），不调用模型。
社会融资规模暂时没有接：试过的接口取不到，这里用"新增人民币贷款"和 M2 看信用松紧，并如实标出来。
"""

from __future__ import annotations

import asyncio

from wealthpilot.services import cache
from wealthpilot.services.stocks import datacenter

# (键, 名称, 报表, 字段, 单位, 怎么读)
SERIES = (
    ("pmi", "制造业 PMI", "RPT_ECONOMY_PMI", "MAKE_INDEX", "", "50 以上是扩张，以下是收缩"),
    ("pmi_services", "非制造业 PMI", "RPT_ECONOMY_PMI", "NMAKE_INDEX", "", "50 以上是扩张"),
    ("cpi", "CPI 同比", "RPT_ECONOMY_CPI", "NATIONAL_SAME", "%", "居民消费价格；长期贴近 0 说明需求偏弱"),
    ("ppi", "PPI 同比", "RPT_ECONOMY_PPI", "BASE_SAME", "%", "工业品出厂价格；和上游企业的盈利同向"),
    ("m2", "M2 同比", "RPT_ECONOMY_CURRENCY_SUPPLY", "BASIC_CURRENCY_SAME", "%", "广义货币增速"),
    ("m1", "M1 同比", "RPT_ECONOMY_CURRENCY_SUPPLY", "CURRENCY_SAME", "%", "企业活期存款多了，通常说明经营在变活跃"),
    ("loans", "新增人民币贷款", "RPT_ECONOMY_RMB_LOAN", "RMB_LOAN", "亿元", "当月新增；看信用扩张的力度（季节性很强，和去年同月比）"),
    ("gdp", "GDP 累计同比", "RPT_ECONOMY_GDP", "SUM_SAME", "%", "按季度公布"),
)
YIELDS = (("cn10y", "中国 10 年期国债收益率", "EMM00166466"), ("cn2y", "中国 2 年期国债收益率", "EMM00588704"),
          ("us10y", "美国 10 年期国债收益率", "EMG00001310"), ("us2y", "美国 2 年期国债收益率", "EMG00001306"))


def _point(rows: list[dict], field: str, date_field: str = "REPORT_DATE") -> dict | None:
    """最新一期和上一期（跳过空值），外加最近十二期的序列。"""
    seen = [(str(r.get(date_field) or "")[:10], r.get(field)) for r in rows if isinstance(r.get(field), (int, float))]
    if not seen:
        return None
    latest, previous = seen[0], seen[1] if len(seen) > 1 else None
    return {"value": round(latest[1], 2), "as_of": latest[0], "previous": round(previous[1], 2) if previous else None,
            "change": round(latest[1] - previous[1], 2) if previous else None,
            "series": [{"date": d, "value": round(v, 2)} for d, v in reversed(seen[:12])]}


async def snapshot() -> dict:
    async def load():
        reports = sorted({s[2] for s in SERIES})
        loaded = await asyncio.gather(*(datacenter(r, sort="REPORT_DATE", page_size=14) for r in reports), datacenter("RPTA_WEB_RATE", sort="TRADE_DATE", page_size=14),
                                      datacenter("RPTA_WEB_TREASURYYIELD", sort="SOLAR_DATE", page_size=30), return_exceptions=True)
        by_report = {r: (v[0] if isinstance(v, tuple) else []) for r, v in zip(reports, loaded, strict=False)}
        lpr_rows = loaded[-2][0] if isinstance(loaded[-2], tuple) else []
        yield_rows = loaded[-1][0] if isinstance(loaded[-1], tuple) else []
        indicators = []
        for key, label, report, field, unit, how in SERIES:
            point = _point(by_report.get(report) or [], field)
            if point:
                indicators.append({"key": key, "label": label, "unit": unit, "how_to_read": how, **point})
        rates = []
        for key, label, field in (("lpr1y", "LPR 1 年期", "LPR1Y"), ("lpr5y", "LPR 5 年期以上", "LPR5Y")):
            point = _point(lpr_rows, field, "TRADE_DATE")
            if point:
                rates.append({"key": key, "label": label, "unit": "%", **point})
        for key, label, field in YIELDS:
            point = _point(yield_rows, field, "SOLAR_DATE")
            if point:
                rates.append({"key": key, "label": label, "unit": "%", **point})
        by_key = {r["key"]: r for r in rates}
        spread = None
        if "cn10y" in by_key and "us10y" in by_key:
            spread = {"label": "中美 10 年期利差", "value": round(by_key["cn10y"]["value"] - by_key["us10y"]["value"], 2), "unit": "个百分点",
                      "how_to_read": "负得越多，人民币资产相对美元资产的利息越少，外资流入的动力越弱"}
        if not indicators and not rates:
            return None
        return {"indicators": indicators, "rates": rates, "spread": spread,
                "missing": ["社会融资规模（暂时没有接上数据源，先看新增人民币贷款和 M2）"],
                "note": "月度数据在次月中上旬公布，as_of 是数据所属的月份而不是公布日。LPR 每月 20 日报价。"}
    return await cache.cached("macro:snapshot", 6 * cache.HOUR, load) or {"indicators": [], "rates": [], "spread": None, "missing": [], "note": ""}


def text(snap: dict) -> str:
    if not snap.get("indicators") and not snap.get("rates"):
        return "暂时取不到宏观数据。"

    def line(item: dict, daily: bool = False) -> str:
        moved = "" if item.get("change") in (None, 0) else f"（比上期{'升' if item['change'] > 0 else '降'} {abs(item['change']):g}）"
        return f"{item['label']} {item['value']:g}{item['unit']}{moved} · {item['as_of'] if daily else item['as_of'][:7]}"
    lines = [line(i) for i in snap["indicators"]] + [line(r, daily=True) for r in snap["rates"]]
    if snap.get("spread"):
        lines.append(f"{snap['spread']['label']} {snap['spread']['value']:+g} {snap['spread']['unit']}")
    return "\n".join(lines + [f"没有的：{m}" for m in snap.get("missing") or []])
