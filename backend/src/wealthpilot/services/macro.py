"""宏观数据：景气、物价、货币信贷、利率。个股研究之外的那层背景。

大部分来自东方财富数据中心整理的官方口径（统计局、央行、中债、美国财政部），不调用模型。
社会融资规模东方财富没有，用的是商务部商务数据中心转载的央行数据。这个来源更新得慢，经常比别的月度数据晚几个月 ——
晚了就在这一项上写明"只更新到哪个月"，不拿旧数字冒充最新的。
"""

from __future__ import annotations

import asyncio

import httpx

from wealthpilot.services import cache
from wealthpilot.services.stocks import datacenter

TSF_URL = "https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery"
TSF_HOW = "当月新增；贷款之外还算上债券、股票、表外融资，比新增贷款更全地反映实体拿到了多少钱（季节性很强，和去年同月比）"

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


def _months_between(earlier: str, later: str) -> int:
    return (int(later[:4]) - int(earlier[:4])) * 12 + int(later[5:7]) - int(earlier[5:7])


def tsf_point(rows: list[dict], reference: str = "") -> dict | None:
    """社会融资规模增量（亿元）。reference 是别的月度数据已经到了哪个月：比它晚两个月以上就标出来。"""
    usable = [{"REPORT_DATE": f"{str(r.get('date'))[:4]}-{str(r.get('date'))[4:6]}-01", "TSF": r.get("tiosfs")} for r in rows
              if len(str(r.get("date") or "")) == 6 and str(r.get("date")).isdigit()]
    point = _point(sorted(usable, key=lambda r: r["REPORT_DATE"], reverse=True), "TSF")
    if point is None:
        return None
    out = {"key": "tsf", "label": "社会融资规模增量", "unit": "亿元", "how_to_read": TSF_HOW, **point}
    behind = _months_between(point["as_of"], reference) if reference else 0
    if behind >= 2:
        out["lag_note"] = f"这个来源只更新到 {point['as_of'][:7]}，比其他月度数据晚 {behind} 个月"
    return out


async def _tsf_rows(transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.post(TSF_URL)
            rows = resp.json() if resp.status_code == 200 else []
            return rows if isinstance(rows, list) else []
    except (httpx.HTTPError, ValueError):
        return []


async def snapshot() -> dict:
    async def load():
        reports = sorted({s[2] for s in SERIES})
        tsf_task = asyncio.create_task(_tsf_rows())            # 和东方财富那几张表同时取
        loaded = await asyncio.gather(*(datacenter(r, sort="REPORT_DATE", page_size=14) for r in reports), datacenter("RPTA_WEB_RATE", sort="TRADE_DATE", page_size=14),
                                      datacenter("RPTA_WEB_TREASURYYIELD", sort="SOLAR_DATE", page_size=30), return_exceptions=True)
        tsf_rows = await tsf_task
        by_report = {r: (v[0] if isinstance(v, tuple) else []) for r, v in zip(reports, loaded, strict=False)}
        lpr_rows = loaded[-2][0] if isinstance(loaded[-2], tuple) else []
        yield_rows = loaded[-1][0] if isinstance(loaded[-1], tuple) else []
        indicators = []
        for key, label, report, field, unit, how in SERIES:
            point = _point(by_report.get(report) or [], field)
            if point:
                indicators.append({"key": key, "label": label, "unit": unit, "how_to_read": how, **point})
        loans = next((i for i in indicators if i["key"] == "loans"), None)
        tsf = tsf_point(tsf_rows, loans["as_of"] if loans else "")
        if tsf:
            indicators.insert(indicators.index(loans) + 1 if loans else len(indicators), tsf)
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
                "missing": [] if tsf else ["社会融资规模（这次没取到，先看新增人民币贷款和 M2）"],
                "note": "月度数据在次月中上旬公布，as_of 是数据所属的月份而不是公布日。LPR 每月 20 日报价。"}
    return await cache.cached("macro:snapshot", 6 * cache.HOUR, load) or {"indicators": [], "rates": [], "spread": None, "missing": [], "note": ""}


def text(snap: dict) -> str:
    if not snap.get("indicators") and not snap.get("rates"):
        return "暂时取不到宏观数据。"

    def line(item: dict, daily: bool = False) -> str:
        moved = "" if item.get("change") in (None, 0) else f"（比上期{'升' if item['change'] > 0 else '降'} {abs(item['change']):g}）"
        late = f"（注意：{item['lag_note']}）" if item.get("lag_note") else ""
        return f"{item['label']} {item['value']:g}{item['unit']}{moved} · {item['as_of'] if daily else item['as_of'][:7]}{late}"
    lines = [line(i) for i in snap["indicators"]] + [line(r, daily=True) for r in snap["rates"]]
    if snap.get("spread"):
        lines.append(f"{snap['spread']['label']} {snap['spread']['value']:+g} {snap['spread']['unit']}")
    return "\n".join(lines + [f"没有的：{m}" for m in snap.get("missing") or []])
