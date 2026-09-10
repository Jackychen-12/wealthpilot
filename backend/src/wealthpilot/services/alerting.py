"""预警评估与推送。

原来的 /api/alerts 是纯即时计算 —— 每次请求重算一遍、不留痕，所以谈不上"通知"：
用户不看就不知道，看了也不知道哪条是新的。

这里补三件事：
1. 评估结果落库，带去重键与冷却期（否则同一条预警每次评估都新增一条）
2. 未读计数与标记已读
3. webhook 推送 —— 自部署场景下唯一不需要额外凭证的送达方式；
   邮件/短信需要 SMTP 或服务商密钥，不在代码里假装支持
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlmodel import Session, select

from wealthpilot.models.alert import Alert
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.simulation import check_constraints, portfolio_weights

DEFAULT_COOLDOWN_HOURS = 12
CONCENTRATION_LIMIT = 0.40


def _severity(value: float, threshold: float) -> str:
    """跌得越深越严重。以阈值的倍数分档。"""
    if threshold == 0:
        return "medium"
    ratio = abs(value) / abs(threshold)
    if ratio >= 2:
        return "high"
    if ratio >= 1.4:
        return "medium"
    return "low"


def evaluate_alerts(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None,
    profile: InvestorProfile | None,
    user_id: int,
    drawdown_threshold: float = -3.0,
) -> list[Alert]:
    """算出当前应该存在的预警。纯函数，不落库。"""
    alerts: list[Alert] = []
    if not holdings:
        return alerts

    # 1. 单标的亏损
    for h in holdings:
        price = nav_data.get(h.fund_code, h.cost_price)
        if h.cost_price <= 0:
            continue
        return_pct = (price - h.cost_price) / h.cost_price * 100
        if return_pct <= drawdown_threshold:
            alerts.append(Alert(
                user_id=user_id, kind="drawdown",
                fund_code=h.fund_code, fund_name=h.fund_name,
                severity=_severity(return_pct, drawdown_threshold),
                message=f"{h.fund_name} 当前收益率 {return_pct:.2f}%，已跌破 {drawdown_threshold:.1f}% 预警线",
                value=round(return_pct, 2), threshold=drawdown_threshold,
                dedup_key=f"{user_id}:drawdown:{h.fund_code}",
            ))

    # 2. 集中度
    weights = portfolio_weights(holdings, nav_data)
    for code, weight in weights.items():
        if weight <= CONCENTRATION_LIMIT:
            continue
        name = next((h.fund_name for h in holdings if h.fund_code == code), code)
        alerts.append(Alert(
            user_id=user_id, kind="concentration",
            fund_code=code, fund_name=name,
            severity="high" if weight > 0.6 else "medium",
            message=f"{name} 占比 {weight:.1%}，超过 {CONCENTRATION_LIMIT:.0%} 集中度警戒线",
            value=round(weight * 100, 2), threshold=CONCENTRATION_LIMIT * 100,
            dedup_key=f"{user_id}:concentration:{code}",
        ))

    # 3. 画像硬约束（没有画像时不产生噪音，测评本身有单独引导）
    if profile is not None:
        result = check_constraints(profile, holdings, nav_data, nav_history)
        for violation in result.get("violations", []):
            alerts.append(Alert(
                user_id=user_id, kind="constraint",
                severity="high",
                message=f"风险画像约束被突破：{violation}",
                dedup_key=f"{user_id}:constraint:{violation[:40]}",
            ))

    return alerts


def persist_alerts(
    db: Session,
    candidates: list[Alert],
    cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
) -> list[Alert]:
    """落库，冷却期内同 dedup_key 不重复写入。返回本次真正新增的。"""
    if not candidates:
        return []

    cutoff = datetime.now() - timedelta(hours=cooldown_hours)
    keys = [c.dedup_key for c in candidates]
    recent = db.exec(
        select(Alert).where(Alert.dedup_key.in_(keys)).where(Alert.created_at >= cutoff)
    ).all()
    seen = {a.dedup_key for a in recent}

    created: list[Alert] = []
    for candidate in candidates:
        if candidate.dedup_key in seen:
            continue
        db.add(candidate)
        created.append(candidate)
        seen.add(candidate.dedup_key)

    if created:
        db.commit()
        for a in created:
            db.refresh(a)
    return created


def list_alerts(
    db: Session, user_id: int, unread_only: bool = False, limit: int = 50
) -> list[Alert]:
    stmt = select(Alert).where(Alert.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Alert.read_at.is_(None))
    stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
    return list(db.exec(stmt).all())


def unread_count(db: Session, user_id: int) -> int:
    return len(
        db.exec(
            select(Alert).where(Alert.user_id == user_id).where(Alert.read_at.is_(None))
        ).all()
    )


def mark_read(db: Session, user_id: int, alert_ids: list[int] | None = None) -> int:
    """标记已读。不传 id 则全部标记。返回受影响条数。"""
    stmt = select(Alert).where(Alert.user_id == user_id).where(Alert.read_at.is_(None))
    if alert_ids:
        stmt = stmt.where(Alert.id.in_(alert_ids))
    rows = list(db.exec(stmt).all())
    now = datetime.now()
    for row in rows:
        row.read_at = now
        db.add(row)
    if rows:
        db.commit()
    return len(rows)


async def deliver_webhook(url: str, alerts: list[Alert], timeout: float = 8.0) -> dict:
    """把预警 POST 到用户配置的 webhook。

    失败不抛错 —— 推送失败不应该让评估请求整体失败，如实返回结果即可。
    """
    if not url:
        return {"delivered": False, "reason": "未配置 webhook URL"}
    if not alerts:
        return {"delivered": False, "reason": "无新增预警，未发送"}

    payload = {
        "source": "wealthpilot",
        "generated_at": datetime.now().isoformat(),
        "count": len(alerts),
        "alerts": [
            {
                "kind": a.kind, "severity": a.severity, "message": a.message,
                "fund_code": a.fund_code, "fund_name": a.fund_name,
                "value": a.value, "threshold": a.threshold,
            }
            for a in alerts
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
        ok = resp.status_code < 400
        return {
            "delivered": ok,
            "status_code": resp.status_code,
            "reason": "" if ok else f"webhook 返回 {resp.status_code}",
        }
    except Exception as e:  # noqa: BLE001
        return {"delivered": False, "reason": f"{type(e).__name__}: {e}"}
