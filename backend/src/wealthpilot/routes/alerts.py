"""预警路由 — 评估、落库、未读、已读、webhook 推送。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from wealthpilot.routes.profile import load_profile
from wealthpilot.services import alerting
from wealthpilot.services.assets import fetch_prices_by_type
from wealthpilot.services.deps import current_user_id, user_holdings
from wealthpilot.services.market_data import fetch_fund_nav
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _load_market(holdings) -> tuple[dict, dict]:
    prices = await fetch_prices_by_type(
        [(h.fund_code, getattr(h, "asset_type", "fund")) for h in holdings]
    )
    nav_data = {h.fund_code: prices.get(h.fund_code, h.cost_price) for h in holdings}
    nav_history = {}
    for h in holdings:
        if (getattr(h, "asset_type", "fund") or "fund") != "fund":
            continue
        hist = await fetch_fund_nav(h.fund_code, 60)
        if hist:
            nav_history[h.fund_code] = hist
    return nav_data, nav_history


@router.get("")
async def check_alerts(
    threshold: float = -3.0,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """评估预警并落库。返回本次新增与当前未读数。

    threshold: 单标的亏损预警线（默认 -3%）
    """
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"alerts": [], "new_count": 0, "unread_count": 0, "message": "暂无持仓"}

    nav_data, nav_history = await _load_market(holdings)
    candidates = alerting.evaluate_alerts(
        holdings, nav_data, nav_history, load_profile(db, user_id), user_id, threshold
    )
    created = alerting.persist_alerts(db, candidates)

    return {
        "alerts": [
            {"kind": a.kind, "severity": a.severity, "message": a.message,
             "fund_code": a.fund_code, "fund_name": a.fund_name, "value": a.value}
            for a in candidates
        ],
        "new_count": len(created),
        "unread_count": alerting.unread_count(db, user_id),
        "threshold": threshold,
    }


@router.get("/inbox")
def inbox(
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """已落库的预警列表（收件箱）。"""
    rows = alerting.list_alerts(db, user_id, unread_only, limit)
    return {
        "unread_count": alerting.unread_count(db, user_id),
        "alerts": [
            {"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message,
             "fund_code": a.fund_code, "fund_name": a.fund_name, "value": a.value,
             "read": a.read_at is not None, "created_at": a.created_at.isoformat()}
            for a in rows
        ],
    }


@router.post("/read")
def mark_read(
    alert_ids: list[int] | None = None,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """标记已读。不传 alert_ids 则全部标记。"""
    return {"marked": alerting.mark_read(db, user_id, alert_ids)}


@router.post("/push")
async def push_alerts(
    threshold: float = -3.0,
    webhook_url: str = "",
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """评估后把新增预警推到 webhook。

    webhook_url 留空则用 ALERT_WEBHOOK_URL 配置。适合挂 cron 定时调用。
    """
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"new_count": 0, "delivery": {"delivered": False, "reason": "暂无持仓"}}

    nav_data, nav_history = await _load_market(holdings)
    created = alerting.persist_alerts(
        db,
        alerting.evaluate_alerts(
            holdings, nav_data, nav_history, load_profile(db, user_id), user_id, threshold
        ),
    )

    url = webhook_url or get_settings().alert_webhook_url
    delivery = await alerting.deliver_webhook(url, created)
    return {"new_count": len(created), "delivery": delivery}
