"""资金与筹码、预期与消息、主营构成 —— 这一批工具的定义和执行。

和 tools.py 里的工具是同一套约定：返回 JSON 字符串；取不到就返回一句以"未获取到"开头的话，
由证据记录标成"无数据"，而不是拿空壳去骗过审核。
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

from wealthpilot.services import capital, expectation
from wealthpilot.services.stocks import fetch_business_segments, fetch_stock_quote, plain_code

_CODE = {"type": "string", "description": "A 股代码，如 600519、000858（可带 sh/sz 前缀）"}


def _tool(name: str, description: str, **extra) -> dict:
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": {"code": _CODE, **extra}, "required": ["code"]}}


INSIGHT_TOOLS = [
    _tool("get_capital_flow",
          "查询个股的资金流向：近 5 / 10 / 20 个交易日累计净流入、连续流入或流出的天数、最近一个交易日按单子大小的拆分，"
          "以及主力资金的持仓成本。回答“最近是有人在买还是在卖”。"),
    _tool("get_margin_trading",
          "查询个股的融资融券：融资余额及其 5 / 20 / 60 日变化、融券余额、融资余额占流通市值的比例。"
          "融资余额是借钱买入还没还的钱，反映杠杆资金的态度。不是两融标的的股票没有数据。"),
    _tool("get_shareholder_structure",
          "查询个股的筹码结构：近几期股东户数与户均持股的变化、最新一期十大流通股东及增减、各类机构（基金、社保、保险、QFII、券商）"
          "的持仓合计与变化、北向持股。回答“票在谁手里、是在集中还是在分散”。"),
    _tool("get_insider_activity",
          "查询个股近两年的内部人动作：重要股东增减持、董监高持股变动、公司回购，以及未来一年的限售股解禁。"
          "回答“最了解公司的人在买还是在卖、后面有没有大额抛压”。"),
    _tool("get_large_trades", "查询个股近期的大宗交易（成交价相对收盘价的折溢价、买卖方）与龙虎榜上榜记录。"),
    _tool("get_consensus_forecast",
          "查询卖方对个股的一致预期：覆盖机构数、评级分布、未来几年的 EPS 预测及隐含增速、按预测 EPS 算的预期市盈率、券商给的目标价区间。"
          "回答“市场原本预期它怎么样”。"),
    _tool("get_research_reports", "查询个股近半年的卖方研报：日期、机构、标题、评级及评级变化、给出的今明两年 EPS。",
          limit={"type": "integer", "description": "条数，默认 8"}),
    _tool("get_earnings_guidance", "查询公司自己给出的业绩数字：最近一次业绩预告（预告类型、区间、同比、原因）和最近一份业绩快报。"),
    _tool("get_stock_news", "查询个股最近的新闻：标题、摘要、媒体、时间。新闻是媒体的转述，不等于事实。",
          limit={"type": "integer", "description": "条数，默认 8"}),
    _tool("get_investor_surveys", "查询个股最近的机构调研与业绩说明会：日期、方式、参与机构数、问答内容的开头一段。"),
    _tool("get_business_segments", "查询个股最新一期的主营构成：按产品、按地区、按行业拆分的收入、收入占比与毛利率。回答“它靠什么赚钱”。"),
]
NAMES = frozenset(t["name"] for t in INSIGHT_TOOLS)

CAPITAL = ("get_capital_flow", "get_margin_trading", "get_shareholder_structure", "get_insider_activity", "get_large_trades")
EXPECTATION = ("get_consensus_forecast", "get_research_reports", "get_earnings_guidance", "get_stock_news", "get_investor_surveys")


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _since(days: int) -> str:
    return str(date.today() - timedelta(days=days))


async def execute(name: str, input_data: dict) -> str:
    code = plain_code(str(input_data.get("code") or ""))
    if not code:
        return "未获取到数据：没有给出股票代码"

    if name == "get_capital_flow":
        flow = await capital.fetch_fund_flow(code, 30)
        if not flow:
            return f"未获取到 {code} 的资金流向"
        return _dump({
            "code": code, **capital.summarize_flow(flow), "latest_day_by_order_size": flow.get("breakdown"),
            "main_force": flow.get("main"), "daily": (flow.get("daily") or [])[:10],
            "note": "net_yi 是全部成交里主动买入减主动卖出（亿元，新浪口径），xlarge_net_yi 是其中特大单的净额；streak_days 正数为连续净流入天数、负数为连续净流出；"
                    "main_force 是东方财富口径的主力（超大单 + 大单）净流入与主力持仓成本。两家口径不同，数值不能相加减。"
                    "资金流向是按成交方向估算的，不等于机构的真实买卖。",
        })

    if name == "get_margin_trading":
        rows = await capital.fetch_margin(code, 70)
        if not rows:
            return f"未获取到 {code} 的融资融券数据（可能不是两融标的）"
        return _dump({"code": code, **capital.summarize_margin(rows), "recent": rows[:5],
                      "note": "金额单位亿元。融资余额上升说明借钱买入的资金在增加，同时也意味着下跌时的被动卖出压力更大。"})

    if name == "get_shareholder_structure":
        counts, top, orgs, north = await asyncio.gather(
            capital.fetch_holder_counts(code, 8), capital.fetch_top_holders(code),
            capital.fetch_institutions(code), capital.fetch_northbound(code, 2))
        if not counts and not top and not orgs:
            return f"未获取到 {code} 的股东与机构持仓数据"
        return _dump({
            "code": code, "holder_counts": counts, "top_float_holders": top, "institutions": orgs, "northbound": north,
            "note": "holder_counts 最新在前：change_pct 是户数环比，avg_shares 是户均持股；户数减少且户均持股上升通常说明筹码在集中。"
                    "机构持仓来自定期报告，滞后 1 到 3 个月；北向持股 2024 年 8 月起只按季度披露。",
        })

    if name == "get_insider_activity":
        holders, executives, buybacks, unlocks = await asyncio.gather(
            capital.fetch_holder_trades(code, 10), capital.fetch_executive_trades(code, 12),
            capital.fetch_buybacks(code, 3), capital.fetch_unlocks(code))
        since = _since(730)
        holders = [h for h in holders if h["notice_date"] >= since]
        executives = [e for e in executives if e["date"] >= since]
        buybacks = [b for b in buybacks if b["notice_date"] >= since]
        return _dump({
            "code": code, "window": f"{since} 至今", "holder_trades": holders, "executive_trades": executives, "buybacks": buybacks,
            "unlocks": unlocks,
            "note": "空列表表示这段时间没有查到记录。shares_wan 单位万股；executive_trades 的 shares 单位股，负数为减持。"
                    "unlocks 里 upcoming=true 是未来一年内要解禁的，float_ratio_pct 是占解禁前流通股的比例。",
        })

    if name == "get_large_trades":
        blocks, billboard = await asyncio.gather(capital.fetch_block_trades(code, 10), capital.fetch_billboard(code, 5))
        blocks = [b for b in blocks if b["date"] >= _since(180)]
        billboard = [b for b in billboard if b["date"] >= _since(365)]
        return _dump({
            "code": code, "block_trades_6m": blocks, "billboard_12m": billboard,
            "note": "空列表表示这段时间没有查到记录（大盘股很少上龙虎榜）。premium_pct 为负是折价成交，大宗折价卖出常见于股东减持。",
        })

    if name == "get_consensus_forecast":
        consensus, quote = await asyncio.gather(expectation.fetch_consensus(code), fetch_stock_quote(code))
        if not consensus or not consensus["org_count"]:
            return f"未获取到 {code} 的一致预期（可能没有券商覆盖）"
        price = (quote or {}).get("price")
        for item in consensus["eps"]:
            if price and item["eps"] and item["eps"] > 0:
                item["pe_at_current_price"] = round(price / item["eps"], 2)
        out = {"code": code, "name": consensus["name"], "price": price, "org_count": consensus["org_count"], "ratings": consensus["ratings"],
               "eps_forecast": consensus["eps"],
               "broker_target_price_low": consensus["target_price_low"], "broker_target_price_high": consensus["target_price_high"]}
        if price and consensus["target_price_low"] and consensus["target_price_high"]:
            out["broker_target_vs_price_pct"] = [round((consensus["target_price_low"] / price - 1) * 100, 1),
                                                 round((consensus["target_price_high"] / price - 1) * 100, 1)]
        out["note"] = ("eps_forecast 里 actual=true 是已披露的实际值，其余是券商预测的平均；growth_pct 是相对上一年的增速；"
                       "pe_at_current_price 是现价除以该年 EPS。卖方评级普遍偏乐观、很少给“卖出”，覆盖机构少于 5 家时参考价值有限。"
                       "目标价是券商的观点，转述时必须写明是“券商给出的目标价”，不能当成结论。")
        return _dump(out)

    if name == "get_research_reports":
        reports = await expectation.fetch_research_reports(code, int(input_data.get("limit") or 8))
        if not reports:
            return f"未获取到 {code} 近半年的研报"
        return _dump({"code": code, "count": len(reports), "reports": reports,
                      "note": "研报是券商的观点。rating_change 为“调高 / 调低”时比评级本身更有信息量。"})

    if name == "get_earnings_guidance":
        guidance = await expectation.fetch_guidance(code)
        recent = _since(460)   # 只要近 15 个月的：更早的预告对应的报告期早就出了正式财报
        out = {k: v for k, v in (guidance or {}).items() if v.get("notice_date", "") >= recent}
        if not out:
            return f"未获取到 {code} 近 15 个月的业绩预告或业绩快报（不是每家公司每期都会发）"
        return _dump({"code": code, **out, "note": "金额单位亿元。业绩预告的 type 是预告类型（预增 / 略增 / 预减 / 首亏 / 扭亏等），"
                                                "reason 是公司自己写的原因；预告是公司的预计，最终以定期报告为准。"})

    if name == "get_stock_news":
        keyword = str(input_data.get("keyword") or "").strip()
        if not keyword:
            keyword = ((await fetch_stock_quote(code)) or {}).get("name") or code
        news = await expectation.fetch_stock_news(keyword, int(input_data.get("limit") or 8))
        if not news:
            return f"未获取到「{keyword}」的相关新闻"
        return _dump({"code": code, "keyword": keyword, "news": [{**n, "source_url": n["url"], "published_at": n["date"]} for n in news],
                      "note": "按时间倒序。新闻是媒体的转述，标题常有夸张，引用时写明媒体和日期。"})

    if name == "get_investor_surveys":
        surveys = await expectation.fetch_surveys(code, 3)
        if not surveys:
            return f"未获取到 {code} 的机构调研记录"
        return _dump({"code": code, "surveys": surveys,
                      "note": "content 是调研纪要的开头一段（公司自己的回答），participants 是参与的机构数。公司的表述不等于事实。"})

    if name == "get_business_segments":
        segments = await fetch_business_segments(code)
        if not segments or not (segments["by_product"] or segments["by_industry"] or segments["by_region"]):
            return f"未获取到 {code} 的主营构成"
        return _dump({"code": code, **segments, "note": "revenue_yi 单位亿元，为该报告期的累计值；引用时写明 report_name。"})

    return f"未知工具: {name}"
