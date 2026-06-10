"""分析引擎路由 — 全量接入真实净值数据。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.analysis import (
    calculate_attribution_by_category,
    calculate_attribution_by_fund,
    calculate_attribution_by_industry,
    calculate_correlation,
    calculate_drawdown,
    calculate_health,
    calculate_overview,
    generate_suggestions,
)
from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _load_data(holdings: list[PortfolioHolding]):
    """统一加载最新净值 + 历史净值。"""
    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info and info.get("nav"):
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price
        hist = await fetch_fund_nav(h.fund_code, 60)
        if hist:
            nav_history[h.fund_code] = hist
    return nav_data, nav_history


@router.get("/overview")
async def get_overview(db: Session = Depends(get_session)):
    """持仓总览（含 Sharpe 比率、真实周收益）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据，请先添加持仓"}
    nav_data, nav_history = await _load_data(holdings)
    overview = calculate_overview(holdings, nav_data, nav_history)
    overview["holdings_count"] = len(holdings)
    # 生成文字描述
    wr = overview.get("weekly_return", 0)
    wg = overview.get("weekly_growth_pct", 0)
    ex = overview.get("excess_return_pct", 0)
    sharpe = overview.get("sharpe_ratio")
    overview["description"] = (
        f"本周组合收益 {'+' if wr >= 0 else ''}{wr:.0f} 元（{'+' if wg >= 0 else ''}{wg:.2f}%），"
        f"{'跑赢' if ex >= 0 else '跑输'}基准 {abs(ex):.2f} 个百分点。"
        + (f" 年化 Sharpe 比率 {sharpe:.2f}。" if sharpe is not None else "")
    )
    return overview


@router.get("/attribution")
async def get_attribution(by: str = "fund", db: Session = Depends(get_session)):
    """收益归因。by=fund|category|industry"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return []
    nav_data, _ = await _load_data(holdings)
    if by == "category":
        return calculate_attribution_by_category(holdings, nav_data)
    elif by == "industry":
        return calculate_attribution_by_industry(holdings, nav_data)
    return calculate_attribution_by_fund(holdings, nav_data)


@router.get("/drawdown")
async def get_drawdown(db: Session = Depends(get_session)):
    """回撤分析（含最大回撤 + 恢复天数）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"funds": [], "summary": {}}
    nav_data, nav_history = await _load_data(holdings)
    funds = calculate_drawdown(holdings, nav_data, nav_history)
    # 组合级别汇总
    total_dd = sum(float(f["value"].replace("%", "")) for f in funds) / max(len(funds), 1)
    avg_recovery = sum(f.get("recovery_days", 0) for f in funds) / max(len(funds), 1)
    return {
        "funds": funds,
        "summary": {
            "avg_drawdown_pct": round(total_dd, 2),
            "avg_recovery_days": round(avg_recovery),
            "high_risk_count": sum(1 for f in funds if f["severity"] == "high"),
        },
    }


@router.get("/health")
async def get_health(db: Session = Depends(get_session)):
    """组合健康度（5 维雷达 + 综合评分）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"dimensions": [], "overall_score": 0}
    nav_data, nav_history = await _load_data(holdings)
    dimensions = calculate_health(holdings, nav_data, nav_history)
    overall = sum(d["score"] for d in dimensions) / len(dimensions)
    return {
        "dimensions": dimensions,
        "overall_score": round(overall),
        "overall_status": "优秀" if overall >= 75 else "良好" if overall >= 60 else "需改善",
    }


@router.get("/correlation")
async def get_correlation(db: Session = Depends(get_session)):
    """持仓间相关性矩阵。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if len(holdings) < 2:
        return {"message": "至少需要2只基金才能计算相关性", "matrix": {}}
    _, nav_history = await _load_data(holdings)
    matrix = calculate_correlation(nav_history)
    # 附加基金名称映射
    name_map = {h.fund_code: h.fund_name for h in holdings}
    return {"matrix": matrix, "names": name_map}


@router.get("/suggestions")
async def get_suggestions(db: Session = Depends(get_session)):
    """AI 建议（规则引擎 + 数据驱动）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return [{"title": "添加持仓", "desc": "请先在持仓管理中添加您的基金持仓", "priority": "high"}]

    nav_data, nav_history = await _load_data(holdings)
    suggestions = generate_suggestions(holdings, nav_data, nav_history)

    suggestions.append({
        "title": "使用 Pilot AI 深入分析",
        "desc": "围绕您的组合进行更深度的问答和分析",
        "priority": "low",
        "action": "chat",
    })

    return suggestions
