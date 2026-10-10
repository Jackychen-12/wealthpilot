"""预期与消息：卖方怎么看、公司自己怎么预告、最近有什么新闻。

财务数字回答"已经发生了什么"，这里回答"市场原本以为会怎样"——没有它，就分不清一份财报是好于预期还是只是看起来不错。
一致预期来自卖方研报的汇总：覆盖机构少的小公司样本很薄，评级又普遍偏乐观，这两点会随数据一起告诉模型。
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import httpx

from wealthpilot.services import cache
from wealthpilot.services.stocks import _r, datacenter, plain_code

_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
_REPORTS = "https://reportapi.eastmoney.com/report/list"
_SEARCH = "https://search-api-web.eastmoney.com/search/jsonp"


def _day(value) -> str:
    return str(value or "")[:10]


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _yi(value, digits: int = 2):
    return round(value / 1e8, digits) if isinstance(value, (int, float)) else None


async def fetch_consensus(code: str) -> dict | None:
    """卖方一致预期：评级分布、未来几年的 EPS 预测、目标价区间。"""
    async def load():
        rows, _ = await datacenter("RPT_WEB_RESPREDICT", filter=f'(SECURITY_CODE="{plain_code(code)}")', page_size=1)
        if not rows:
            return None
        r = rows[0]
        eps = [{"year": r.get(f"YEAR{i}"), "eps": _r(r.get(f"EPS{i}")), "actual": r.get(f"YEAR_MARK{i}") == "A"}
               for i in range(1, 5) if r.get(f"YEAR{i}") and r.get(f"EPS{i}") is not None]
        for prev, cur in zip(eps, eps[1:], strict=False):
            if prev["eps"] and prev["eps"] > 0:
                cur["growth_pct"] = round((cur["eps"] / prev["eps"] - 1) * 100, 2)
        ratings = {"买入": r.get("RATING_BUY_NUM") or 0, "增持": r.get("RATING_ADD_NUM") or 0, "中性": r.get("RATING_NEUTRAL_NUM") or 0,
                   "减持": r.get("RATING_REDUCE_NUM") or 0, "卖出": r.get("RATING_SALE_NUM") or 0}
        return {"name": r.get("SECURITY_NAME_ABBR") or "", "org_count": r.get("RATING_ORG_NUM") or 0, "ratings": ratings, "eps": eps,
                "target_price_low": _r(r.get("DEC_AIMPRICEMIN")), "target_price_high": _r(r.get("DEC_AIMPRICEMAX")),
                "concepts": [c for c in str(r.get("CONCEPTINDEX_BOARD") or "").split(",") if c][:12]}
    return await cache.resilient(f"consensus:{plain_code(code)}", 6 * cache.HOUR, load, keep=45 * cache.DAY, what=f"{plain_code(code)} 的一致预期")


async def fetch_research_reports(code: str, limit: int = 8, months: int = 6) -> list[dict]:
    """近期的卖方研报：标题、机构、评级、给出的 EPS 预测。"""
    async def load():
        params = {"industryCode": "*", "pageSize": max(1, min(limit, 30)), "industry": "*", "rating": "*", "ratingChange": "*",
                  "beginTime": str(date.today() - timedelta(days=31 * months)), "endTime": str(date.today() + timedelta(days=1)),
                  "pageNo": 1, "fields": "", "qType": 0, "orgCode": "", "code": plain_code(code), "rcode": "", "p": 1, "pageNum": 1, "pageNumber": 1}
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS) as client:
                data = (await client.get(_REPORTS, params=params)).json()
        except Exception:  # noqa: BLE001
            return []
        change = {"0": "调高", "1": "调低", "2": "首次", "3": "维持", "4": "无"}
        return [{
            "date": _day(r.get("publishDate")), "org": r.get("orgSName") or "", "title": r.get("title") or "",
            "rating": r.get("emRatingName") or "", "rating_change": change.get(str(r.get("ratingChange")), ""),
            "eps_this_year": _r(_f(r.get("predictThisYearEps"))), "eps_next_year": _r(_f(r.get("predictNextYearEps"))),
            "url": f"https://data.eastmoney.com/report/info/{r['infoCode']}.html" if r.get("infoCode") else "",
        } for r in data.get("data") or []]
    return await cache.resilient(f"reports:{plain_code(code)}:{limit}:{months}", 6 * cache.HOUR, load, keep=45 * cache.DAY, what=f"{plain_code(code)} 的研报列表") or []


async def fetch_guidance(code: str) -> dict | None:
    """公司自己给的数：最近一次业绩预告，和最近一份业绩快报。"""
    flt = f'(SECURITY_CODE="{plain_code(code)}")'
    forecasts, _ = await datacenter("RPT_PUBLIC_OP_NEWPREDICT", filter=flt, page_size=8, sort="NOTICE_DATE")
    express, _ = await datacenter("RPT_FCI_PERFORMANCEE", filter=flt, page_size=1, sort="NOTICE_DATE")
    out: dict = {}
    if forecasts:
        period = forecasts[0].get("REPORT_DATE")
        out["forecast"] = {"notice_date": _day(forecasts[0].get("NOTICE_DATE")), "report_date": _day(period), "items": [{
            "metric": r.get("PREDICT_FINANCE") or "", "type": r.get("PREDICT_TYPE") or "",
            "lower_yi": _yi(r.get("PREDICT_AMT_LOWER")), "upper_yi": _yi(r.get("PREDICT_AMT_UPPER")),
            "yoy_lower_pct": _r(r.get("ADD_AMP_LOWER")), "yoy_upper_pct": _r(r.get("ADD_AMP_UPPER")),
            "content": r.get("PREDICT_CONTENT") or "", "reason": (r.get("CHANGE_REASON_EXPLAIN") or "")[:300],
        } for r in forecasts if r.get("REPORT_DATE") == period]}
    if express:
        e = express[0]
        out["express"] = {"notice_date": _day(e.get("NOTICE_DATE")), "report_date": _day(e.get("REPORT_DATE")), "period": e.get("DATATYPE") or "",
                          "revenue_yi": _yi(e.get("TOTAL_OPERATE_INCOME")), "revenue_yoy_pct": _r(e.get("YSTZ")),
                          "net_profit_yi": _yi(e.get("PARENT_NETPROFIT")), "net_profit_yoy_pct": _r(e.get("JLRTBZCL"))}
    return out or None


async def fetch_stock_news(keyword: str, limit: int = 8) -> list[dict]:
    """按公司名搜最近的新闻：标题、摘要、媒体、时间。"""
    async def load():
        param = {"uid": "", "keyword": keyword, "type": ["cmsArticleWebOld"], "client": "web", "clientType": "web", "clientVersion": "curr",
                 "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "time", "pageIndex": 1, "pageSize": max(1, min(limit, 20)),
                                                "preTag": "", "postTag": ""}}}
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
                text = (await client.get(_SEARCH, params={"cb": "cb", "param": json.dumps(param, ensure_ascii=False)})).text
            data = json.loads(re.sub(r"^[^(]*\(|\)\s*;?\s*$", "", text))
        except Exception:  # noqa: BLE001
            return []
        return [{
            "date": str(r.get("date") or "")[:16], "title": re.sub(r"</?em>", "", r.get("title") or ""),
            "summary": re.sub(r"</?em>|\s+", " ", r.get("content") or "").strip()[:200],
            "media": r.get("mediaName") or "", "url": r.get("url") or "",
        } for r in (data.get("result") or {}).get("cmsArticleWebOld") or []]
    return await cache.cached(f"stocknews:{keyword}:{limit}", 20 * cache.MINUTE, load) or []


async def fetch_surveys(code: str, limit: int = 3) -> list[dict]:
    """机构调研 / 业绩说明会记录，带问答内容的开头一段。"""
    rows, _ = await datacenter("RPT_ORG_SURVEY", filter=f'(SECURITY_CODE="{plain_code(code)}")', page_size=40, sort="NOTICE_DATE")
    seen: dict[str, dict] = {}
    for r in rows:   # 一次调研每家参会机构一行，按日期合并
        key = _day(r.get("NOTICE_DATE"))
        item = seen.setdefault(key, {"notice_date": key, "date": _day(r.get("RECEIVE_START_DATE")), "way": r.get("RECEIVE_WAY_EXPLAIN") or "",
                                     "place": r.get("RECEIVE_PLACE") or "", "participants": 0,
                                     "content": re.sub(r"\s+", " ", r.get("CONTENT") or "").strip()[:800]})
        item["participants"] += 1
    return list(seen.values())[:limit]
