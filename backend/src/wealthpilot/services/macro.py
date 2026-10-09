"""宏观数据：景气、物价、货币信贷、利率。个股研究之外的那层背景。

PMI、物价、货币、GDP、国债收益率来自东方财富数据中心整理的官方口径（统计局、央行、中债、美国财政部），不调用模型。
能直接用发布方自己的，就用发布方的：
  LPR           中国货币网（全国银行间同业拆借中心）；不通时退回东方财富
  社会融资规模   中国人民银行官网的统计表；不通时退回商务部商务数据中心的转载 —— 那个转载更新得慢，经常晚几个月，
                晚了就在这一项上写明"只更新到哪个月"，不拿旧数字冒充最新的
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from urllib.parse import urljoin

import httpx

from wealthpilot.services import cache, sources
from wealthpilot.services.sources import SourceError
from wealthpilot.services.stocks import _HEADERS, datacenter

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


async def _tsf_mofcom(transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    """商务部商务数据中心转载的社融数据：[{date: '202604', tiosfs: 6245, …}]。"""
    async with httpx.AsyncClient(timeout=10, transport=transport, headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.post(TSF_URL)
    try:
        rows = resp.json()
    except ValueError as e:
        raise SourceError(f"商务数据中心返回 {resp.status_code}，不是预期的结构") from e
    if resp.status_code != 200 or not isinstance(rows, list):
        raise SourceError(f"商务数据中心返回 {resp.status_code}，不是预期的结构")
    return rows


PBC_INDEX = "http://www.pbc.gov.cn/diaochatongjisi/116219/116319/index.html"
_LINK = re.compile(r"""<a[^>]+href=['"]([^'"]+)['"][^>]*>(.*?)</a>""", re.S)


def _pbc_link(html: str, text: str) -> str:
    """页面里文字是 text 的那个链接。"""
    return next((href for href, label in _LINK.findall(html) if re.sub(r"<[^>]+>|\s+", "", label).startswith(text)), "")


def parse_pbc_table(html: str) -> list[dict]:
    """央行“社会融资规模增量统计表”：每行第一格是 2026.08 这样的月份，第二格是当月增量（亿元）。"""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;|\s+", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 2 and re.fullmatch(r"20\d\d\.\d\d", cells[0]):
            try:
                out.append({"date": cells[0].replace(".", ""), "tiosfs": float(cells[1].replace(",", ""))})
            except ValueError:
                continue
    return out


async def _tsf_pbc(transport: httpx.AsyncBaseTransport | None = None, today: date | None = None) -> list[dict]:
    """中国人民银行官网：统计数据 → 某年 → 社会融资规模 → 增量统计表。今年和去年各取一张，够算上期和近十二个月。"""
    today = today or date.today()

    async def page(client: httpx.AsyncClient, url: str) -> str:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise SourceError(f"央行官网返回 {resp.status_code}")
        text = resp.content.decode("utf-8", errors="replace")
        return text if "统计" in text or "社会融资" in text else resp.content.decode("gb18030", errors="replace")

    async def year_rows(client: httpx.AsyncClient, index: str, year: int) -> list[dict]:
        year_url = _pbc_link(index, f"{year}年统计数据")
        if not year_url:
            return []                                       # 一月份新一年的页面还没建：不算出错
        year_page = await page(client, urljoin(PBC_INDEX, year_url))
        tsf_url = _pbc_link(year_page, "社会融资规模")
        if not tsf_url:
            raise SourceError(f"央行 {year} 年统计数据的页面里找不到“社会融资规模”")
        tsf_page = await page(client, urljoin(urljoin(PBC_INDEX, year_url), tsf_url))
        at = tsf_page.find("社会融资规模增量统计表")
        match = re.search(r"""href=['"]([^'"]+\.htm)['"]""", tsf_page[at:]) if at >= 0 else None
        if not match:
            raise SourceError(f"央行 {year} 年的社融页面里找不到增量统计表")
        return parse_pbc_table(await page(client, urljoin(urljoin(urljoin(PBC_INDEX, year_url), tsf_url), match.group(1))))

    async with httpx.AsyncClient(timeout=15, transport=transport, headers=_HEADERS, follow_redirects=True) as client:
        index = await page(client, PBC_INDEX)
        if "年统计数据" not in index:
            raise SourceError("央行统计数据的页面结构变了：找不到按年份的链接")
        this_year, last_year = await asyncio.gather(year_rows(client, index, today.year), year_rows(client, index, today.year - 1))
    rows = sorted(this_year + last_year, key=lambda r: r["date"], reverse=True)
    if not rows:
        raise SourceError("央行的社融统计表里没有认出任何月份")
    return rows


async def _tsf_rows() -> list[dict]:
    rows, _ = await sources.first([("pbc", _tsf_pbc), ("mofcom", _tsf_mofcom)])
    return rows or []


async def _lpr_chinamoney(transport: httpx.AsyncBaseTransport | None = None, today: date | None = None) -> list[dict]:
    """中国货币网的 LPR 历史，整理成和东方财富那张表一样的行：[{TRADE_DATE, LPR1Y, LPR5Y}]，新的在前。"""
    today = today or date.today()
    async with httpx.AsyncClient(timeout=10, transport=transport, headers={**_HEADERS, "Referer": "https://www.chinamoney.com.cn/chinese/bklpr/"}) as client:
        resp = await client.post("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis",
                                 params={"lang": "CN", "strStartDate": (today - timedelta(days=360)).isoformat(), "strEndDate": today.isoformat()})   # 它只给一年以内的
    try:
        body = resp.json()
        records = body["records"]
    except (ValueError, KeyError, TypeError) as e:
        raise SourceError(f"中国货币网返回 {resp.status_code}，不是预期的结构") from e
    if not records:
        raise SourceError(f"中国货币网没有给出 LPR 记录：{(body.get('data') or {}).get('message') or '空'}")
    rows = []
    for r in records or []:
        try:
            rows.append({"TRADE_DATE": str(r["showDateCN"])[:10], "LPR1Y": float(r["1Y"]), "LPR5Y": float(r["5Y"])})
        except (KeyError, TypeError, ValueError):
            continue
    if records and not rows:
        raise SourceError("中国货币网的 LPR 记录里找不到 showDateCN / 1Y / 5Y，字段改名了")
    return sorted(rows, key=lambda r: r["TRADE_DATE"], reverse=True)


async def _lpr_rows() -> list[dict]:
    async def eastmoney():
        rows, _ = await datacenter("RPTA_WEB_RATE", sort="TRADE_DATE", page_size=14, strict=True)
        return rows
    rows, _ = await sources.first([("chinamoney", _lpr_chinamoney), ("eastmoney", eastmoney)])
    return rows or []


async def snapshot() -> dict:
    async def load():
        reports = sorted({s[2] for s in SERIES})
        tsf_task = asyncio.create_task(_tsf_rows())            # 和东方财富那几张表同时取
        lpr_task = asyncio.create_task(_lpr_rows())
        loaded = await asyncio.gather(*(datacenter(r, sort="REPORT_DATE", page_size=14) for r in reports),
                                      datacenter("RPTA_WEB_TREASURYYIELD", sort="SOLAR_DATE", page_size=30), return_exceptions=True)
        tsf_rows = await tsf_task
        by_report = {r: (v[0] if isinstance(v, tuple) else []) for r, v in zip(reports, loaded, strict=False)}
        lpr_rows = await lpr_task
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
