"""回撤预警路由。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.market_data import fetch_fund_info
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def check_alerts(
    threshold: float = -3.0,
    db: Session = Depends(get_session),
):
    """检查回撤预警。返回超过阈值的持仓列表。

    threshold: 触发预警的收益率阈值（默认 -3%）
    """
    holdings = list(db.exec(select(PortfolioHolding)).all())
    if not holdings:
        return {"alerts": [], "message": "暂无持仓"}

    alerts = []
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if not info:
            continue
        nav = info["nav"]
        ret_pct = (nav - h.cost_price) / h.cost_price * 100

        if ret_pct <= threshold:
            severity = "critical" if ret_pct <= -10 else "warning" if ret_pct <= -5 else "notice"
            alerts.append({
                "fund_code": h.fund_code,
                "fund_name": h.fund_name,
                "current_nav": nav,
                "cost_price": h.cost_price,
                "return_pct": round(ret_pct, 2),
                "severity": severity,
                "message": f"{h.fund_name} 当前亏损 {ret_pct:.1f}%，已触发预警线（{threshold}%）",
            })

    return {
        "alerts": alerts,
        "total": len(alerts),
        "threshold": threshold,
        "checked_at": str(__import__("datetime").datetime.now()),
    }


@router.get("/summary")
async def alert_summary(db: Session = Depends(get_session)):
    """预警摘要（首页使用）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())
    critical = 0
    warning = 0

    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if not info:
            continue
        ret = (info["nav"] - h.cost_price) / h.cost_price * 100
        if ret <= -10:
            critical += 1
        elif ret <= -5:
            warning += 1

    return {
        "critical": critical,
        "warning": warning,
        "status": "danger" if critical > 0 else "warning" if warning > 0 else "safe",
    }
