"""Agent 工具定义 + 统一执行器。"""

import json

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.analysis import (
    calculate_attribution_by_fund,
    calculate_correlation,
    calculate_drawdown,
    calculate_health,
    calculate_max_drawdown,
    calculate_overview,
    generate_suggestions,
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


async def execute_tool(
    name: str,
    input_data: dict,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> str:
    """统一工具执行器。"""
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
