"""大盘复盘、宏观、概念板块、反向 DCF —— 这一批工具的定义和执行。

约定和其他工具一样：返回 JSON 字符串；取不到就返回一句以"未获取到"开头的话。
"""

from __future__ import annotations

import asyncio
import json

from wealthpilot.services import macro, recap
from wealthpilot.services import valuation_models as vm
from wealthpilot.services.stocks import (
    fetch_financial_indicators,
    fetch_stock_profile,
    fetch_stock_quote,
    plain_code,
)

DEPTH_TOOLS = [
    {"name": "get_market_recap",
     "description": "今天市场发生了什么：指数与涨跌家数、涨停 / 炸板 / 跌停数量与封板率、连板梯队、涨停集中在哪些题材（带涨停原因）、"
                    "概念板块领涨领跌、龙虎榜上机构和营业部席位的净买卖，以及一个按固定尺子得出的情绪刻度。回答“今天行情怎么样、热点在哪、情绪热不热”。",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_macro_indicators",
     "description": "宏观数据：制造业与非制造业 PMI、CPI、PPI、M1 / M2、新增人民币贷款、GDP、LPR、中美国债收益率与利差，每项带最新值、上期值和所属月份。"
                    "回答“宏观环境怎么样、利率和信用是松是紧”。没有社会融资规模。",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_concept_boards",
     "description": "概念板块今天的强弱：涨幅靠前和靠后的板块，各自的成分股数和领涨股。找题材热点用。",
     "input_schema": {"type": "object", "properties": {"top": {"type": "integer", "description": "两头各要几个，默认 10"}}}},
    {"name": "get_concept_stocks",
     "description": "一个概念板块里有哪些股票（按今天涨跌幅排），带市值、市盈率、换手率。研究一个题材或产业链时用它拿到候选公司，再逐只去查。",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "概念板块名或其中一部分，如 固态电池、机器人、CPO"},
         "limit": {"type": "integer", "description": "要几只，默认 30，最多 80"}}, "required": ["name"]}},
    {"name": "compute_reverse_dcf",
     "description": "反向 DCF：按现在的市值倒推，利润要以多高的速度增长十年才配得上这个价钱；同时给出过去三年利润的实际增速，和几档增长假设下“算出来的价值是市值的几倍”。"
                    "结果是“现价隐含了什么”，不是目标价。亏损公司算不了；金融类公司只作参考。",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string", "description": "A 股代码，如 600519"}}, "required": ["code"]}},
]
NAMES = frozenset(t["name"] for t in DEPTH_TOOLS)


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


async def reverse_dcf_for(code: str) -> dict | None:
    """页面和工具共用：取市值和财务指标，算反向 DCF。行情取不到返回 None。"""
    code = plain_code(code)
    quote, rows, profile = await asyncio.gather(fetch_stock_quote(code), fetch_financial_indicators(code, 20), fetch_stock_profile(code), return_exceptions=True)
    if not isinstance(quote, dict):
        return None
    industry = (profile or {}).get("industry", "") if isinstance(profile, dict) else ""
    out = vm.reverse_dcf(quote.get("total_mv_yi") or 0, rows if isinstance(rows, list) else [], name=quote.get("name") or code, industry=industry)
    return {"code": code, "price": quote.get("price"), "industry": industry, **out}


async def execute(name: str, input_data: dict) -> str:
    if name == "get_market_recap":
        report = await recap.build()
        if not report:
            return "未获取到今天的市场数据（休市，或者还没开盘）"
        return _dump({**{k: v for k, v in report.items() if k != "limit_up_stocks"}, "limit_up_stocks": report["limit_up_stocks"][:25],
                      "note": "mood 是按 basis 里那几个数字套固定尺子得出的粗略刻度，不是预测。涨停原因来自同花顺的整理，是题材归类，不是公司公告。"
                              "seats 是龙虎榜买入前五席位的净买卖，只覆盖上榜的股票。"})
    if name == "get_macro_indicators":
        snap = await macro.snapshot()
        if not snap.get("indicators") and not snap.get("rates"):
            return "未获取到宏观数据"
        slim = lambda item: {k: v for k, v in item.items() if k != "series"}  # noqa: E731
        return _dump({"indicators": [slim(i) for i in snap["indicators"]], "rates": [slim(r) for r in snap["rates"]], "spread": snap["spread"],
                      "missing": snap["missing"], "note": snap["note"]})
    if name == "get_concept_boards":
        boards = await recap.concept_boards()
        if not boards:
            return "未获取到概念板块数据"
        top = max(1, min(int(input_data.get("top") or 10), 30))
        ranked = sorted(boards, key=lambda b: -b["change_pct"])
        strip = lambda b: {k: v for k, v in b.items() if k != "node"}  # noqa: E731
        return _dump({"count": len(boards), "top": [strip(b) for b in ranked[:top]], "bottom": [strip(b) for b in ranked[-top:][::-1]],
                      "note": "change_pct 是成分股的平均涨跌幅（新浪的板块口径）。板块是人为归类，同一只股票会出现在好几个板块里。"})
    if name == "get_concept_stocks":
        query = str(input_data.get("name") or "").strip()
        found = await recap.concept_stocks(query, int(input_data.get("limit") or 30)) if query else None
        if not found or not found["stocks"]:
            return f"未获取到概念板块「{query}」的成分股（没有这个板块，或者暂时取不到）。可以先用 get_concept_boards 看有哪些板块"
        return _dump({**found, "note": "属于这个板块不等于主营业务就是它：很多公司只是沾边。要看一家公司到底有多少收入来自这个题材，用 get_business_segments。"})
    if name == "compute_reverse_dcf":
        code = plain_code(str(input_data.get("code") or ""))
        result = await reverse_dcf_for(code) if code else None
        if result is None:
            return f"未获取到 {code} 的行情，算不了反向 DCF"
        if not result["ok"]:
            return f"未获取到 {code} 的反向 DCF 结果：{result['reason']}"
        return _dump(result)
    return f"未知工具: {name}"
