"""花了多少、还能不能花：模型用量的流水、汇总与每日上限。

用量按 token 记（这是服务商返回的事实）；折成钱只在用户自己填了单价时才算，
而且是个上限估计 —— 命中缓存的输入实际更便宜。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from wealthpilot.models.usage import UsageLog
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_engine


def record(user_id: int, usage, model: str, kind: str) -> None:
    """记一笔。没花 token（比如一上来就报余额不足）不记；记账失败不该影响业务。"""
    try:
        data = usage.as_dict()
        if not (data.get("input_tokens") or data.get("output_tokens")):
            return
        with Session(get_engine()) as db:
            db.add(UsageLog(user_id=user_id or 0, kind=kind, model=model, calls=data.get("calls", 0),
                            input_tokens=data.get("input_tokens", 0), cached_tokens=data.get("cached_tokens", 0),
                            output_tokens=data.get("output_tokens", 0)))
            db.commit()
    except Exception:  # noqa: BLE001
        pass


def _total(rows: list[UsageLog]) -> dict:
    tokens_in, cached, out = sum(r.input_tokens for r in rows), sum(r.cached_tokens for r in rows), sum(r.output_tokens for r in rows)
    return {"runs": len(rows), "input_tokens": tokens_in, "cached_tokens": cached, "output_tokens": out, "tokens": tokens_in + out,
            "cost": cost(tokens_in, out)}


def cost(input_tokens: int, output_tokens: int) -> float | None:
    """按用户填的单价（元 / 百万 token）折成钱。没填单价返回 None。"""
    s = get_settings()
    if not (s.token_price_input or s.token_price_output):
        return None
    return round(input_tokens / 1e6 * s.token_price_input + output_tokens / 1e6 * s.token_price_output, 4)


def spent_today(user_id: int, now: datetime | None = None) -> int:
    now = now or datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(get_engine()) as db:
        rows = db.exec(select(UsageLog).where(UsageLog.user_id == (user_id or 0), UsageLog.at >= start)).all()
    return sum(r.input_tokens + r.output_tokens for r in rows)


def blocked(user_id: int, now: datetime | None = None) -> str:
    """今天还能不能再调模型。到了上限返回一句说明（空串表示可以）。"""
    limit = get_settings().daily_token_budget
    if limit <= 0:
        return ""
    used = spent_today(user_id, now)
    if used < limit:
        return ""
    return (f"今天的模型用量已经到你设的上限了（已用 {used / 1e4:.1f} 万 token，上限 {limit / 1e4:.1f} 万）。"
            "明天会自动恢复；确实要继续，到「设置 → 用量与预算」把上限调高。行情、选股、持仓这些不用模型的功能不受影响。")


def summary(user_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(get_engine()) as db:
        rows = list(db.exec(select(UsageLog).where(UsageLog.user_id == (user_id or 0), UsageLog.at >= today - timedelta(days=29))).all())
    days = []
    for back in range(13, -1, -1):
        start = today - timedelta(days=back)
        day_rows = [r for r in rows if start <= r.at < start + timedelta(days=1)]
        days.append({"day": start.strftime("%m-%d"), **_total(day_rows)})
    kinds: dict[str, list[UsageLog]] = {}
    for r in rows:
        kinds.setdefault(r.kind, []).append(r)
    s = get_settings()
    return {
        "today": _total([r for r in rows if r.at >= today]),
        "last_7_days": _total([r for r in rows if r.at >= today - timedelta(days=6)]),
        "last_30_days": _total(rows),
        "by_day": days,
        "by_kind": sorted(({"kind": k, **_total(v), "avg_tokens": round(sum(r.input_tokens + r.output_tokens for r in v) / len(v))}
                           for k, v in kinds.items()), key=lambda i: -i["tokens"]),
        "daily_token_budget": s.daily_token_budget, "priced": bool(s.token_price_input or s.token_price_output),
    }


def typical_tokens(user_id: int, kind: str) -> int | None:
    """这类研究最近几次平均花多少 token，开跑前告诉用户个大概。没有记录返回 None。"""
    with Session(get_engine()) as db:
        rows = db.exec(select(UsageLog).where(UsageLog.user_id == (user_id or 0), UsageLog.kind == kind)
                       .order_by(UsageLog.id.desc()).limit(5)).all()
    return round(sum(r.input_tokens + r.output_tokens for r in rows) / len(rows)) if rows else None
