"""周报路由。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav
from wealthpilot.services.report import generate_weekly_report
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/weekly")
async def get_weekly_report(db: Session = Depends(get_session)):
    """获取/生成最新周报。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据，请先添加持仓"}

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}

    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price

        hist = await fetch_fund_nav(h.fund_code, 30)
        if hist:
            nav_history[h.fund_code] = hist

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return report


@router.post("/generate")
async def force_generate_report(db: Session = Depends(get_session)):
    """手动触发重新生成周报。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"error": "暂无持仓数据"}

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}

    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price

        hist = await fetch_fund_nav(h.fund_code, 30)
        if hist:
            nav_history[h.fund_code] = hist

    report = generate_weekly_report(holdings, nav_data, nav_history)
    return {"status": "generated", "report": report}
