"""分析引擎路由 — 全量接入真实净值数据。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from wealthpilot.services.deps import current_user_id, user_holdings
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
from wealthpilot.services.assets import fetch_prices_by_type
from wealthpilot.services.market_data import fetch_fund_nav
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/analysis", tags=["analysis"])


async def _load_data(holdings: list[PortfolioHolding]):
    """统一加载最新价 + 历史净值。

    最新价按资产类型分组批量取（基金走净值、股票/ETF 走新浪、加密走 CoinGecko）；
    历史序列目前只有场外基金有，股票/ETF/加密的历史行情尚未接入，
    因此这些标的不会进入依赖 nav_history 的指标（回撤、相关性）。
    """
    prices = await fetch_prices_by_type([(h.fund_code, h.asset_type) for h in holdings])
    nav_data = {h.fund_code: prices.get(h.fund_code, h.cost_price) for h in holdings}

    nav_history: dict[str, list[dict]] = {}
    for h in holdings:
        if (h.asset_type or "fund") != "fund":
            continue
        hist = await fetch_fund_nav(h.fund_code, 60)
        if hist:
            nav_history[h.fund_code] = hist
    return nav_data, nav_history


@router.get("/overview")
async def get_overview(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """持仓总览（含 Sharpe 比率、真实周收益）。"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"error": "暂无持仓数据，请先添加持仓"}
    nav_data, nav_history = await _load_data(holdings)
    overview = calculate_overview(holdings, nav_data, nav_history)
    overview["holdings_count"] = len(holdings)
    # 生成文字描述
    # 样本不足时 calculate_overview 会返回 None 而不是假装是 0，
    # 所以这里不能依赖 .get(k, 0) —— 键存在、值为 None 时默认值不生效。
    wr = overview.get("weekly_return") or 0
    wg = overview.get("weekly_growth_pct") or 0
    ex = overview.get("excess_return_pct")
    sharpe = overview.get("sharpe_ratio")

    parts = [f"本周组合收益 {'+' if wr >= 0 else ''}{wr:.0f} 元（{'+' if wg >= 0 else ''}{wg:.2f}%）。"]
    if ex is None:
        parts.append("基准对比数据不足，未计算超额收益。")
    else:
        parts.append(f"{'跑赢' if ex >= 0 else '跑输'}基准 {abs(ex):.2f} 个百分点。")
    if sharpe is not None:
        parts.append(f"年化 Sharpe 比率 {sharpe:.2f}。")
    overview["description"] = "".join(parts)
    return overview


@router.get("/attribution")
async def get_attribution(by: str = "fund", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """收益归因。by=fund|category|industry"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return []
    nav_data, _ = await _load_data(holdings)
    if by == "category":
        return calculate_attribution_by_category(holdings, nav_data)
    elif by == "industry":
        return calculate_attribution_by_industry(holdings, nav_data)
    return calculate_attribution_by_fund(holdings, nav_data)


@router.get("/drawdown")
async def get_drawdown(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """回撤分析（含最大回撤 + 恢复天数）。"""
    holdings = user_holdings(db, user_id)
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
async def get_health(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """组合健康度（5 维雷达 + 综合评分）。"""
    holdings = user_holdings(db, user_id)
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
async def get_correlation(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """持仓间相关性矩阵。"""
    holdings = user_holdings(db, user_id)
    if len(holdings) < 2:
        return {"message": "至少需要2只基金才能计算相关性", "matrix": {}}
    _, nav_history = await _load_data(holdings)
    matrix = calculate_correlation(nav_history)
    # 附加基金名称映射
    name_map = {h.fund_code: h.fund_name for h in holdings}
    return {"matrix": matrix, "names": name_map}


@router.get("/suggestions")
async def get_suggestions(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """AI 建议（规则引擎 + 数据驱动）。"""
    holdings = user_holdings(db, user_id)
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
