"""WealthPilot MCP Server — 12 investment tools for Claude Code / Cursor."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.tools import execute_tool
from wealthpilot.storage.db import get_engine

mcp = FastMCP(
    "wealthpilot",
    instructions=(
        "WealthPilot 智能投顾工具集：12 个实时投资分析工具，覆盖基金查询、持仓分析、风险评估。"
        "市场工具无需持仓数据即可使用；持仓/风险工具会自动从本地数据库加载用户持仓。"
    ),
)

_ctx: dict = {"holdings": None, "nav_data": None, "nav_history": None}


async def _ensure_context() -> tuple[list, dict, dict]:
    """Lazy-load holdings + NAV data from SQLite."""
    if _ctx["holdings"] is not None:
        return _ctx["holdings"], _ctx["nav_data"], _ctx["nav_history"]

    from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav

    engine = get_engine()
    with Session(engine) as session:
        _ctx["holdings"] = list(session.exec(select(PortfolioHolding)).all())

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}
    for h in _ctx["holdings"]:
        info = await fetch_fund_info(h.fund_code)
        nav_data[h.fund_code] = info["nav"] if info else h.cost_price
        hist = await fetch_fund_nav(h.fund_code, 60)
        if hist:
            nav_history[h.fund_code] = hist

    _ctx["nav_data"] = nav_data
    _ctx["nav_history"] = nav_history
    return _ctx["holdings"], nav_data, nav_history


# ═══════════════════════════════════════════════════════════
# Market Tools (stateless — no portfolio needed)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def get_fund_info(fund_code: str) -> str:
    """Query fund basic info: name, NAV, valuation, type.
    查询基金基本信息（名称、最新净值、估值、类型）。fund_code 示例: 007340, 110011"""
    return await execute_tool("get_fund_info", {"fund_code": fund_code}, [], {}, None)


@mcp.tool()
async def get_nav_history(fund_code: str, days: int = 30) -> str:
    """Query fund NAV history for N days with daily returns.
    查询基金近 N 天净值走势（日期、净值、日涨跌幅），用于趋势分析。"""
    return await execute_tool("get_nav_history", {"fund_code": fund_code, "days": days}, [], {}, None)


@mcp.tool()
async def search_market_news(keyword: str = "") -> str:
    """Fetch latest financial news headlines.
    获取最新财经要闻，了解市场动态。"""
    return await execute_tool("search_market_news", {"keyword": keyword}, [], {}, None)


# ═══════════════════════════════════════════════════════════
# Portfolio Tools (load holdings from DB)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def get_portfolio_overview() -> str:
    """Calculate portfolio overview: total value, returns, weekly P&L, Sharpe ratio.
    持仓总览：总市值、总收益、周收益、Sharpe 比率。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_portfolio_overview", {}, h, nd, nh)


@mcp.tool()
async def get_attribution() -> str:
    """Per-fund return attribution analysis.
    按基金维度收益归因：哪只贡献最大、哪只拖累最多。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_attribution", {}, h, nd, nh)


@mcp.tool()
async def get_health_score() -> str:
    """5-dimension portfolio health score: returns, volatility, diversification, style, risk-return.
    组合健康度 5 维评分（收益表现、波动控制、分散度、风格匹配、风险收益比）。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_health_score", {}, h, nd, nh)


@mcp.tool()
async def get_investment_suggestions() -> str:
    """Rule-based investment suggestions: concentration, loss, correlation, category balance.
    规则引擎投资建议（集中度、亏损、相关性、类别均衡检查）。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_investment_suggestions", {}, h, nd, nh)


# ═══════════════════════════════════════════════════════════
# Risk Tools (load holdings from DB)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def calculate_return(fund_code: str, days: int) -> str:
    """Calculate cumulative return over N days. days: 7=1week, 30=1month, 90=3months.
    计算基金指定天数内的累计收益率。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("calculate_return", {"fund_code": fund_code, "days": days}, h, nd, nh)


@mcp.tool()
async def compare_funds(fund_codes: list[str]) -> str:
    """Compare multiple funds' recent performance (2-5 funds).
    对比多只基金近期表现（净值、涨跌幅），2-5 只。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("compare_funds", {"fund_codes": fund_codes}, h, nd, nh)


@mcp.tool()
async def get_drawdown_analysis() -> str:
    """Analyze drawdown for all holdings: current drop, max drawdown, recovery days.
    全部持仓回撤分析（当前跌幅、最大回撤、恢复天数）。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_drawdown_analysis", {}, h, nd, nh)


@mcp.tool()
async def get_max_drawdown(fund_code: str) -> str:
    """Calculate max drawdown + recovery days for a single fund.
    单只基金最大回撤 + 恢复天数。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_max_drawdown", {"fund_code": fund_code}, h, nd, nh)


@mcp.tool()
async def get_correlation_matrix() -> str:
    """Calculate correlation matrix across held funds to assess diversification.
    持仓基金相关性矩阵，评估分散化程度。"""
    h, nd, nh = await _ensure_context()
    return await execute_tool("get_correlation_matrix", {}, h, nd, nh)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
