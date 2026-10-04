"""Agent 工具定义 + 统一执行器。"""

import asyncio
import json

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.analysis import (
    calculate_attribution_by_fund,
    calculate_correlation,
    calculate_drawdown,
    calculate_health,
    calculate_max_drawdown,
    calculate_overview,
    generate_suggestions,
)
from wealthpilot.services.assets import fetch_price_history
from wealthpilot.services.backtest import backtest_rule
from wealthpilot.services.lookthrough import (
    aggregate_exposure,
    fetch_fund_holdings,
    overlap_between,
    summarize_overlap,
)
from wealthpilot.services.market_data import (
    fetch_fund_info,
    fetch_fund_nav,
    fetch_market_news,
    get_comprehensive_fund_info,
)
from wealthpilot.services.simulation import (
    check_constraints,
    concentration_metrics,
    max_position_within_drawdown,
    portfolio_weights,
    simulate_change,
)
from wealthpilot.services.stocks import (
    fetch_stock_financials,
    fetch_stock_kline,
    fetch_stock_profile,
    fetch_stock_quote,
    summarize_kline,
)

# ═══════════════════════════════════════════════════════════
# MarketAgent 工具
# ═══════════════════════════════════════════════════════════

MARKET_TOOLS = [
    {
        "name": "get_fund_info",
        "description": "查询某只基金的基本信息（名称、最新净值、估值、类型等）。当用户问某只基金的情况时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {
                    "type": "string",
                    "description": "基金代码，如 007340、110011",
                }
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "get_nav_history",
        "description": "查询某只基金近 N 个交易日的净值历史数据（日期、净值、日涨跌幅）。用于分析走势和计算收益。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "交易日数，默认30", "default": 30},
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "search_market_news",
        "description": "获取最新财经要闻。用于回答市场动态相关问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词（可选）", "default": ""},
            },
        },
    },
]

# ═══════════════════════════════════════════════════════════
# PortfolioAgent 工具
# ═══════════════════════════════════════════════════════════

PORTFOLIO_TOOLS = [
    {
        "name": "get_portfolio_overview",
        "description": "计算用户持仓总览：总市值、总收益、周收益、Sharpe 比率等。用于回答'我的持仓怎么样'类问题。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_attribution",
        "description": "按基金维度计算收益归因。用于回答'哪只基金贡献最大/最差'。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_health_score",
        "description": "计算组合健康度 5 维评分（收益表现、波动控制、分散度、风格匹配、风险收益比）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_investment_suggestions",
        "description": "基于规则引擎生成投资建议（集中度、亏损、相关性、类别均衡检查）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ═══════════════════════════════════════════════════════════
# RiskAgent 工具
# ═══════════════════════════════════════════════════════════

RISK_TOOLS = [
    {
        "name": "calculate_return",
        "description": "计算某只基金在最近 N 个交易日内的累计收益率。用于回答'近1周/1月/3月表现如何'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "区间交易日数（5≈近1周, 21≈近1月, 63≈近3月）"},
            },
            "required": ["fund_code", "days"],
        },
    },
    {
        "name": "compare_funds",
        "description": "对比多只基金的近期表现（净值、涨跌幅）。用于回答'哪只基金更好'类问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要对比的基金代码列表（2-5只）",
                }
            },
            "required": ["fund_codes"],
        },
    },
    {
        "name": "get_drawdown_analysis",
        "description": "分析持仓中每只基金的回撤情况（当前跌幅、最大回撤、恢复天数）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_max_drawdown",
        "description": "计算某只基金的最大回撤 + 恢复天数。",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "get_correlation_matrix",
        "description": "计算持仓基金之间的相关性矩阵。用于评估分散化程度。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ═══════════════════════════════════════════════════════════
# 计算 / 校验工具（确定性，不让模型自己算）
#
# 取数工具回答"是什么"，这组回答"如果……会怎样"和"这样行不行"。
# 目的是让最终答案里的每个数字都能追溯到某次工具返回。
# ═══════════════════════════════════════════════════════════

COMPUTE_TOOLS = [
    {
        "name": "compute_concentration",
        "description": (
            "计算当前持仓的集中度：各基金权重、最大单一权重、HHI 指数、有效持仓数。"
            "需要引用任何占比数字时调用本工具，不要自己按市值心算。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_portfolio_change",
        "description": (
            "推演一组仓位变动后的组合指标，返回变动前后的权重、集中度与加权回撤估计。"
            "回答'加仓到 X% 会怎样''减掉 Y 元之后呢'这类问题时必须调用本工具，"
            "不要自行推算变动后的占比。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "description": "变动列表。每项给 target_pct(目标占比 0-100) 或 amount(增减金额，可为负)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fund_code": {"type": "string", "description": "基金代码"},
                            "target_pct": {"type": "number", "description": "目标占比（0-100）"},
                            "amount": {"type": "number", "description": "增减金额，负数为减仓"},
                        },
                        "required": ["fund_code"],
                    },
                }
            },
            "required": ["changes"],
        },
    },
    {
        "name": "check_profile_constraint",
        "description": (
            "按用户风险画像逐条校验当前持仓，或校验一组拟议变动之后的状态。"
            "返回是否通过、违反了哪几条、检查了哪几项。"
            "给出任何仓位相关建议之前必须先调用本工具确认不越界。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "description": "可选。要校验的拟议变动，格式同 simulate_portfolio_change；不传则校验当前持仓",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fund_code": {"type": "string"},
                            "target_pct": {"type": "number"},
                            "amount": {"type": "number"},
                        },
                        "required": ["fund_code"],
                    },
                }
            },
        },
    },
    {
        "name": "compute_position_sizing",
        "description": (
            "在不突破用户回撤容忍度的前提下，计算某只基金最多能占多少比例，"
            "并给出相对当前仓位还有多少空间。用户问'还能加多少'时调用本工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
            },
            "required": ["fund_code"],
        },
    },
]


# ═══════════════════════════════════════════════════════════
# 穿透 / 回测工具（QuantAgent）
# ═══════════════════════════════════════════════════════════

QUANT_TOOLS = [
    {
        "name": "lookthrough_portfolio",
        "description": (
            "把组合穿透到个股层：汇总各基金重仓股的真实暴露，找出被多只基金"
            "同时重仓的个股。净值相关性只说明'同涨同跌'，穿透才能解释'为什么'。"
            "回答分散度、重叠、真实行业暴露类问题时调用。"
            "注意：季报只披露前十大且滞后 1-3 个月，结果里带 report_date 必须转述。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compute_stock_overlap",
        "description": (
            "对比两只基金的重仓股重叠：共有几只、合计权重多少、分别是哪些。"
            "用于回答'这两只基金是不是买的差不多'。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code_a": {"type": "string", "description": "基金代码 A"},
                "fund_code_b": {"type": "string", "description": "基金代码 B"},
            },
            "required": ["fund_code_a", "fund_code_b"],
        },
    },
    {
        "name": "backtest_rule",
        "description": (
            "回测一条分批建仓规则，并与'一次性买入''等额定投'两个基线对比。"
            "**给出任何分批加仓/止损规则之前，必须先用本工具验证它的历史表现**，"
            "不要凭空给出未经检验的规则。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
                "triggers": {
                    "type": "array",
                    "description": "触发档位，每档只触发一次",
                    "items": {
                        "type": "object",
                        "properties": {
                            "drawdown_pct": {"type": "number", "description": "自高点回调达到该比例时触发"},
                            "add_pct": {"type": "number", "description": "投入总资金的百分比"},
                        },
                        "required": ["drawdown_pct", "add_pct"],
                    },
                },
                "stop_loss_pct": {"type": "number", "description": "可选。相对持仓成本跌破该比例则清仓"},
                "days": {"type": "integer", "description": "回测使用的历史交易日数，默认 250"},
            },
            "required": ["fund_code", "triggers"],
        },
    },
]


# ═══════════════════════════════════════════════════════════
# StockAgent 工具 —— A 股个股 / ETF
# ═══════════════════════════════════════════════════════════

_STOCK_CODE = {"type": "string", "description": "A 股代码，如 600519、000858、510300（可带 sh/sz 前缀）"}

STOCK_TOOLS = [
    {
        "name": "get_stock_quote",
        "description": "查询个股或 ETF 的实时行情：现价、涨跌幅、成交额、换手率、总市值。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_stock_kline",
        "description": (
            "查询个股或 ETF 最近 N 个交易日的前复权日线摘要：区间涨跌幅、区间高低点、"
            "当前价在区间内的位置，以及最近几日收盘。用于回答'近期走势如何''现在在高位还是低位'。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": _STOCK_CODE,
                           "days": {"type": "integer", "description": "交易日数，默认 60（21≈1月，250≈1年）"}},
            "required": ["code"],
        },
    },
    {
        "name": "get_stock_valuation",
        "description": (
            "查询个股估值：PE(TTM)、PB、总市值，以及当前价在近一年价格区间里的位置。"
            "注意返回的是**价格**分位而不是估值分位——没有历史 PE 序列，不要把它说成'PE 处于历史 xx 分位'。"
        ),
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_stock_financials",
        "description": (
            "查询个股最近几期业绩：营收、归母净利润及同比、ROE、每股收益、毛利率。"
            "每条都带 report_date（报告期），引用时必须转述报告期——财报是滞后数据，不代表现状。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": _STOCK_CODE,
                           "periods": {"type": "integer", "description": "取最近几期，默认 4"}},
            "required": ["code"],
        },
    },
    {
        "name": "get_stock_profile",
        "description": "查询个股的所属行业、地域板块与市值。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
]


def _asset_type_of(code: str, input_data: dict, holdings: list[PortfolioHolding]) -> str:
    """工具入参没指明类型时：持仓里有就按持仓记录，否则按基金。"""
    explicit = input_data.get("asset_type")
    if explicit:
        return str(explicit).lower()
    return next((h.asset_type or "fund" for h in holdings if h.fund_code == code), "fund")


async def execute_tool(
    name: str,
    input_data: dict,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
    profile: InvestorProfile | None = None,
) -> str:
    """统一工具执行器。"""
    # === 个股工具 ===
    if name in ("get_stock_quote", "get_stock_valuation"):
        code = input_data["code"]
        quote = await fetch_stock_quote(code)
        if not quote:
            return f"未获取到 {code} 的行情（代码有误、已退市或处于停牌）"
        if name == "get_stock_quote":
            return json.dumps(quote, ensure_ascii=False)
        kline = await fetch_stock_kline(code, 250)
        result = {k: quote[k] for k in ("code", "name", "price", "pe_ttm", "pb", "total_mv_yi", "quote_time")}
        if kline:
            summary = summarize_kline(kline)
            result["price_range_1y"] = {k: summary[k] for k in
                                        ("period_high", "period_low", "range_position_pct", "trading_days")}
        result["note"] = ("pe_ttm 为滚动市盈率，亏损时为负或缺失；price_range_1y 是近一年**价格**所处位置，"
                          "不是估值分位；市值单位为亿元")
        return json.dumps(result, ensure_ascii=False)

    if name == "get_stock_kline":
        code = input_data["code"]
        days = max(5, min(int(input_data.get("days", 60)), 750))
        kline = await fetch_stock_kline(code, days)
        if not kline:
            return f"未获取到 {code} 的日线数据"
        recent = [{"date": r["nav_date"], "close": r["nav"], "change_pct": r["daily_return"]} for r in kline[:5]]
        return json.dumps({"code": code, **summarize_kline(kline), "recent": recent}, ensure_ascii=False)

    if name == "get_stock_financials":
        code = input_data["code"]
        rows = await fetch_stock_financials(code, int(input_data.get("periods", 4)))
        if not rows:
            return f"未获取到 {code} 的业绩报表"
        return json.dumps({"code": code, "reports": rows,
                           "note": "金额单位为亿元；同比为相对上年同期；各期为累计值（如 06-30 是上半年合计）"},
                          ensure_ascii=False)

    if name == "get_stock_profile":
        profile_data = await fetch_stock_profile(input_data["code"])
        if not profile_data:
            return f"未获取到 {input_data['code']} 的公司信息"
        return json.dumps(profile_data, ensure_ascii=False)

    # === 穿透 / 回测工具 ===
    if name == "lookthrough_portfolio":
        if not holdings:
            return "当前没有持仓，无法穿透。"
        # 只有基金有季报重仓股；直接持有的个股由 aggregate_exposure 并入
        codes = list(dict.fromkeys(h.fund_code for h in holdings if (h.asset_type or "fund") == "fund"))
        fetched = await asyncio.gather(*[fetch_fund_holdings(c) for c in codes])
        fund_holdings = dict(zip(codes, fetched, strict=True))
        result = aggregate_exposure(holdings, nav_data, fund_holdings)
        result["summary"] = summarize_overlap(result)
        return json.dumps(result, ensure_ascii=False)

    if name == "compute_stock_overlap":
        a, b = await asyncio.gather(
            fetch_fund_holdings(input_data["fund_code_a"]),
            fetch_fund_holdings(input_data["fund_code_b"]),
        )
        if not a["stocks"] or not b["stocks"]:
            missing = [c for c, d in ((a["fund_code"], a), (b["fund_code"], b)) if not d["stocks"]]
            return f"未取到以下基金的季报持仓：{'、'.join(missing)}（可能是新基金或非股票型）"
        return json.dumps(overlap_between(a, b), ensure_ascii=False)

    if name == "backtest_rule":
        code = input_data["fund_code"]
        days = max(2, min(int(input_data.get("days", 250)), 1500))
        asset_type = _asset_type_of(code, input_data, holdings)
        nav_list = (nav_history or {}).get(code, [])
        if len(nav_list) < days:
            nav_list = await fetch_price_history(code, asset_type, days)
        nav_list = sorted(nav_list, key=lambda r: r["nav_date"], reverse=True)[:days]
        if not nav_list:
            return f"未获取到 {code} 的历史价格，无法回测。"
        # A 股卖出有印花税 + 双边佣金；没指定费率时给股票一个保守的默认值
        default_fee = 0.1 if asset_type == "stock" else 0.0
        return json.dumps(
            backtest_rule(
                nav_list,
                input_data["triggers"],
                stop_loss_pct=input_data.get("stop_loss_pct"),
                fee_pct=input_data.get("fee_pct", default_fee),
                execution_lag=1,
                price_basis="forward_adjusted_close" if asset_type in ("stock", "etf") else "unit_nav_unadjusted",
            ),
            ensure_ascii=False,
        )

    # === 计算 / 校验工具 ===
    if name == "compute_concentration":
        weights = portfolio_weights(holdings, nav_data)
        if not weights:
            return "当前没有持仓，无法计算集中度。"
        return json.dumps(
            {"weights": {c: round(w, 4) for c, w in weights.items()},
             **concentration_metrics(weights)},
            ensure_ascii=False,
        )

    if name == "simulate_portfolio_change":
        changes = input_data.get("changes") or []
        if not changes:
            return "未提供变动内容，无法推演。"
        return json.dumps(
            simulate_change(holdings, nav_data, nav_history, changes), ensure_ascii=False
        )

    if name == "check_profile_constraint":
        return json.dumps(
            check_constraints(profile, holdings, nav_data, nav_history,
                              input_data.get("changes")),
            ensure_ascii=False,
        )

    if name == "compute_position_sizing":
        return json.dumps(
            max_position_within_drawdown(
                input_data["fund_code"], holdings, nav_data, nav_history, profile
            ),
            ensure_ascii=False,
        )

    # === Market 工具 ===
    if name == "get_fund_info":
        info = await get_comprehensive_fund_info(input_data["fund_code"])
        if info and info.get("name"):
            return json.dumps(info, ensure_ascii=False)
        return f"未找到基金 {input_data['fund_code']} 的信息"

    if name == "get_nav_history":
        nav_list = await fetch_fund_nav(input_data["fund_code"], input_data.get("days", 30))
        if nav_list:
            summary = f"基金 {input_data['fund_code']} 近 {len(nav_list)} 个交易日净值数据：\n"
            for item in nav_list[:5]:
                summary += f"  {item['nav_date']}: 净值{item['nav']}, 涨跌{item['daily_return']}%\n"
            if len(nav_list) > 5:
                first = nav_list[-1]
                last = nav_list[0]
                period_return = (last["nav"] - first["nav"]) / first["nav"] * 100
                summary += f"  ...（共{len(nav_list)}条）\n"
                summary += f"  区间收益率: {period_return:+.2f}%"
            return summary
        return f"未获取到基金 {input_data['fund_code']} 的净值数据"

    if name == "search_market_news":
        news = await fetch_market_news(input_data.get("keyword", ""))
        if news:
            return json.dumps({"news": news, "scope": "最新财经要闻标题过滤，非全网检索"}, ensure_ascii=False)
        return json.dumps({"status": "insufficient_data", "error": "未获取到匹配新闻，不能据此推断没有相关新闻"}, ensure_ascii=False)

    # === Portfolio 工具 ===
    if name == "get_portfolio_overview":
        overview = calculate_overview(holdings, nav_data, nav_history)
        return json.dumps(overview, ensure_ascii=False)

    if name == "get_attribution":
        attribution = calculate_attribution_by_fund(holdings, nav_data)
        return json.dumps(attribution, ensure_ascii=False)

    if name == "get_health_score":
        health = calculate_health(holdings, nav_data, nav_history)
        overall = sum(d["score"] for d in health) / len(health) if health else 0
        result = {"dimensions": health, "overall_score": round(overall)}
        return json.dumps(result, ensure_ascii=False)

    if name == "get_investment_suggestions":
        suggestions = generate_suggestions(holdings, nav_data, nav_history)
        return json.dumps(suggestions, ensure_ascii=False)

    # === Risk 工具 ===
    if name == "calculate_return":
        nav_list = await fetch_price_history(
            input_data["fund_code"], _asset_type_of(input_data["fund_code"], input_data, holdings),
            input_data["days"])
        if nav_list and len(nav_list) >= 2:
            first_nav = nav_list[-1]["nav"]
            last_nav = nav_list[0]["nav"]
            ret = (last_nav - first_nav) / first_nav * 100
            return (
                f"{input_data['fund_code']} 近 {len(nav_list)} 个交易日收益率: {ret:+.2f}%\n"
                f"起始: {first_nav}（{nav_list[-1]['nav_date']}）\n"
                f"最新: {last_nav}（{nav_list[0]['nav_date']}）"
            )
        return "数据不足，无法计算"

    if name == "compare_funds":
        codes = input_data["fund_codes"][:5]
        results = []
        infos = await asyncio.gather(*[fetch_fund_info(c) for c in codes])
        for code, info in zip(codes, infos, strict=True):
            if info:
                results.append(f"  {info['name']}（{code}）: 净值{info['nav']}, 估值涨跌{info.get('estimated_change', 'N/A')}%")
            else:
                results.append(f"  {code}: 信息获取失败")
        return "基金对比结果：\n" + "\n".join(results)

    if name == "get_drawdown_analysis":
        drawdown = calculate_drawdown(holdings, nav_data, nav_history)
        return json.dumps(drawdown, ensure_ascii=False)

    if name == "get_max_drawdown":
        code = input_data["fund_code"]
        hist = nav_history.get(code, []) if nav_history else []
        if not hist:
            hist = await fetch_price_history(code, _asset_type_of(code, input_data, holdings), 60)
        if hist:
            dd = calculate_max_drawdown(hist)
            return json.dumps(dd, ensure_ascii=False)
        return f"未获取到基金 {code} 的历史数据"

    if name == "get_correlation_matrix":
        if not nav_history or len(nav_history) < 2:
            return "至少需要2只基金的历史数据才能计算相关性"
        matrix = calculate_correlation(nav_history)
        name_map = {h.fund_code: h.fund_name for h in holdings}
        return json.dumps({"matrix": matrix, "names": name_map}, ensure_ascii=False)

    return f"未知工具: {name}"
