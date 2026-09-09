"""Agent 工具定义 + 统一执行器。"""

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
from wealthpilot.services.simulation import (
    check_constraints,
    concentration_metrics,
    max_position_within_drawdown,
    portfolio_weights,
    simulate_change,
)
from wealthpilot.services.market_data import (
    fetch_fund_info,
    fetch_fund_nav,
    fetch_market_news,
    get_comprehensive_fund_info,
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
        "description": "查询某只基金近 N 天的净值历史数据（日期、净值、日涨跌幅）。用于分析走势和计算收益。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "查询天数，默认30", "default": 30},
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
        "description": "计算某只基金在指定天数内的累计收益率。用于回答'近1周/1月/3月表现如何'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "计算区间天数（7=近1周, 30=近1月, 90=近3月）"},
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


async def execute_tool(
    name: str,
    input_data: dict,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
    profile: InvestorProfile | None = None,
) -> str:
    """统一工具执行器。"""
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
        news = await fetch_market_news()
        if news:
            return "最新财经要闻：\n" + "\n".join(f"  [{n['tag']}] {n['text']}" for n in news[:5])
        return "暂无最新新闻"

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
        nav_list = await fetch_fund_nav(input_data["fund_code"], input_data["days"])
        if nav_list and len(nav_list) >= 2:
            first_nav = nav_list[-1]["nav"]
            last_nav = nav_list[0]["nav"]
            ret = (last_nav - first_nav) / first_nav * 100
            return (
                f"基金 {input_data['fund_code']} 近 {input_data['days']} 天收益率: {ret:+.2f}%\n"
                f"起始净值: {first_nav}（{nav_list[-1]['nav_date']}）\n"
                f"最新净值: {last_nav}（{nav_list[0]['nav_date']}）"
            )
        return "数据不足，无法计算"

    if name == "compare_funds":
        codes = input_data["fund_codes"][:5]
        results = []
        for code in codes:
            info = await fetch_fund_info(code)
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
            hist = await fetch_fund_nav(code, 60)
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
