"""主动干活：到点自己跑的研究（任务），和越过条件就提醒的盯价（提醒）。

和每日盯盘一样跟着进程跑 —— 不装系统服务，不在后台常驻。电脑合着盖错过了时间，
下次打开时把最近错过的那一次补上。任务会调用模型，所以有每日次数上限；提醒只取行情，不花钱。
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from sqlmodel import Session, select

from wealthpilot.models.automation import Automation
from wealthpilot.models.broker import Digest
from wealthpilot.services import cache, channels, memory, stocks, summary
from wealthpilot.services.assets import fetch_sina_quotes
from wealthpilot.settings import get_settings

CATCH_UP = timedelta(hours=36)   # 错过多久以内还补跑；再久就等下一次
ALERT_EVERY = 300                # 盘中每隔多少秒看一次提醒
# metric -> (名称, 单位)
ALERT_METRICS: dict[str, tuple[str, str]] = {
    "price": ("最新价", "元"),
    "change_pct": ("当日涨跌幅", "%"),
    "pe_percentile": ("PE 历史分位", "%"),
    "pb_percentile": ("PB 历史分位", "%"),
}
DEPTHS = ("auto", "quick", "deep")

# ── 什么时候跑 ──────────────────────────────────────────

_DAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_DAY_NAMES = "一二三四五六日"
_TIME_RE = re.compile(r"(\d{1,2})\s*(?:[:：]\s*(\d{1,2})|点\s*(半|\d{1,2})?\s*分?)")


def parse_schedule(text: str) -> dict | None:
    """把“每天 8:30”“工作日 15:40”“每周一三五 9点半”读成 {days, hour, minute, text}。读不懂返回 None。"""
    raw = (text or "").strip()
    match = _TIME_RE.search(raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 30 if match.group(3) == "半" else int(match.group(3) or 0)
    if re.search(r"下午|晚上|傍晚", raw) and hour < 12:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    head = raw[:match.start()]
    if re.search(r"工作日|交易日", head):
        days = [0, 1, 2, 3, 4]
    elif (week := re.search(r"周([一二三四五六日天、,，和周\s]+)", head)):
        days = sorted({_DAY_INDEX[c] for c in week.group(1) if c in _DAY_INDEX})
    elif re.search(r"每天|每日|天天", head) or not head.strip():
        days = list(range(7))
    else:
        return None
    if not days:
        return None
    return {"days": days, "hour": hour, "minute": minute, "text": describe(days, hour, minute)}


def describe(days: list[int], hour: int, minute: int) -> str:
    when = "每天" if len(days) == 7 else "工作日" if days == [0, 1, 2, 3, 4] else "每周" + "".join(_DAY_NAMES[d] for d in days)
    return f"{when} {hour:02d}:{minute:02d}"


def last_slot(schedule: dict, now: datetime) -> datetime | None:
    """最近一个已经到点的时刻。"""
    for back in range(8):
        day = now.date() - timedelta(days=back)
        slot = datetime.combine(day, time(schedule["hour"], schedule["minute"]))
        if day.weekday() in schedule["days"] and slot <= now:
            return slot
    return None


def next_slot(schedule: dict, now: datetime) -> datetime | None:
    for ahead in range(8):
        day = now.date() + timedelta(days=ahead)
        slot = datetime.combine(day, time(schedule["hour"], schedule["minute"]))
        if day.weekday() in schedule["days"] and slot > now:
            return slot
    return None


def due(auto: Automation, now: datetime) -> bool:
    schedule = parse_schedule(auto.schedule)
    slot = last_slot(schedule, now) if schedule else None
    return bool(slot and slot > (auto.last_run_at or auto.created_at) and now - slot <= CATCH_UP)


# ── 增删改 ──────────────────────────────────────────────

class AutomationError(ValueError):
    pass


def owned(db: Session, user_id: int, automation_id: int) -> Automation:
    auto = db.get(Automation, automation_id)
    if auto is None or auto.user_id != user_id:
        raise AutomationError("没有这条自动任务")
    return auto


def _clean_task(data: dict, auto: Automation) -> None:
    prompt = str(data.get("prompt", auto.prompt) or "").strip()
    if len(prompt) < 4:
        raise AutomationError("写一句到点要问的话，比如“复盘一下我的持仓，有什么需要注意的”")
    schedule = parse_schedule(str(data.get("schedule", auto.schedule) or ""))
    if schedule is None:
        raise AutomationError("没看懂时间。可以写成：每天 08:30、工作日 15:40、每周一 09:00")
    depth = str(data.get("depth", auto.depth) or "auto")
    if depth not in DEPTHS:
        raise AutomationError("depth 只能是 auto / quick / deep")
    auto.prompt, auto.schedule, auto.depth = prompt[:500], schedule["text"], depth
    auto.title = str(data.get("title", auto.title) or "").strip()[:40] or prompt[:20]


def _clean_alert(data: dict, auto: Automation) -> None:
    code = str(data.get("code", auto.code) or "").strip()
    metric, op = str(data.get("metric", auto.metric) or ""), str(data.get("op", auto.op) or "")
    if not re.fullmatch(r"\d{6}", code):
        raise AutomationError("要盯的股票给 6 位代码")
    if metric not in ALERT_METRICS:
        raise AutomationError("metric 只能是：" + "、".join(ALERT_METRICS))
    if op not in (">=", "<="):
        raise AutomationError("op 只能是 >= 或 <=")
    try:
        threshold = float(data.get("threshold", auto.threshold))
    except (TypeError, ValueError):
        raise AutomationError("阈值要是一个数字") from None
    if metric == "price" and threshold <= 0:
        raise AutomationError("价格要大于 0")
    if metric.endswith("_percentile") and not 0 <= threshold <= 100:
        raise AutomationError("分位在 0 到 100 之间")
    auto.code, auto.metric, auto.op, auto.threshold = code, metric, op, threshold
    auto.name = str(data.get("name", auto.name) or "").strip()[:20]
    auto.repeat = bool(data.get("repeat", auto.repeat))
    auto.title = str(data.get("title", "") or "").strip()[:40] or condition_text(auto)


def condition_text(auto: Automation) -> str:
    label, unit = ALERT_METRICS.get(auto.metric, (auto.metric, ""))
    return f"{auto.name or auto.code} {label} {'≥' if auto.op == '>=' else '≤'} {auto.threshold:g}{unit}"


def save(db: Session, user_id: int, data: dict, automation_id: int | None = None) -> Automation:
    """新建或修改。字段都过校验；改了时间或条件就重新开始计（不会因为“早该跑了”立刻补跑）。"""
    if automation_id is None:
        kind = str(data.get("kind") or "")
        if kind not in ("task", "alert"):
            raise AutomationError("kind 只能是 task 或 alert")
        auto = Automation(user_id=user_id, kind=kind)
    else:
        auto = owned(db, user_id, automation_id)
    before = (auto.schedule, auto.metric, auto.op, auto.threshold, auto.code)
    (_clean_task if auto.kind == "task" else _clean_alert)(data, auto)
    if "enabled" in data:
        auto.enabled = bool(data["enabled"])
    if automation_id is not None and before != (auto.schedule, auto.metric, auto.op, auto.threshold, auto.code):
        auto.created_at, auto.last_run_at = datetime.now(), None
    db.add(auto)
    db.commit()
    db.refresh(auto)
    memory.record(db, user_id, "automation/saved", auto.title, {"id": auto.id, "kind": auto.kind}, actor="user")
    return auto


def delete(db: Session, user_id: int, automation_id: int) -> None:
    auto = owned(db, user_id, automation_id)
    memory.record(db, user_id, "automation/deleted", auto.title, {"id": auto.id, "kind": auto.kind}, actor="user")
    db.delete(auto)
    db.commit()


def list_all(db: Session, user_id: int) -> list[Automation]:
    return list(db.exec(select(Automation).where(Automation.user_id == user_id).order_by(Automation.id.desc())).all())


def serialize(auto: Automation, now: datetime | None = None) -> dict:
    out = {"id": auto.id, "kind": auto.kind, "title": auto.title, "enabled": auto.enabled,
           "last_run_at": auto.last_run_at.isoformat() if auto.last_run_at else None,
           "last_status": auto.last_status, "last_result": auto.last_result, "created_at": auto.created_at.isoformat()}
    if auto.kind == "task":
        schedule = parse_schedule(auto.schedule)
        upcoming = next_slot(schedule, now or datetime.now()) if schedule and auto.enabled else None
        out |= {"schedule": auto.schedule, "prompt": auto.prompt, "depth": auto.depth, "last_message_id": auto.last_message_id,
                "next_run_at": upcoming.isoformat() if upcoming else None}
    else:
        out |= {"code": auto.code, "name": auto.name, "metric": auto.metric, "op": auto.op, "threshold": auto.threshold,
                "repeat": auto.repeat, "condition": condition_text(auto), "unit": ALERT_METRICS.get(auto.metric, ("", ""))[1]}
    return out


# ── 记进当日简报 ────────────────────────────────────────

def _append_digest(db: Session, user_id: int, event: dict, today: date) -> None:
    digest = db.exec(select(Digest).where(Digest.user_id == user_id, Digest.day == str(today))).first()
    if digest is None:
        # 还没到盯盘的时间：先不建当天的简报（建了会让盯盘以为今天跑过了），记到一个待并入的位置
        pending = cache.read(f"autoevents:{user_id}:{today}", 2 * cache.DAY) or []
        cache.write(f"autoevents:{user_id}:{today}", pending + [event])
        return
    try:
        events = json.loads(digest.events_json)
    except ValueError:
        events = []
    digest.events_json = json.dumps(events + [event], ensure_ascii=False)
    db.add(digest)
    db.commit()


def pending_events(user_id: int, today: date) -> list[dict]:
    """当天在盯盘之前发生的任务与提醒，供盯盘写简报时并入。"""
    return cache.read(f"autoevents:{user_id}:{today}", 2 * cache.DAY) or []


# ── 任务：到点跑一次研究 ────────────────────────────────

def _runs_today(user_id: int, today: date) -> int:
    return int((cache.read(f"autoruns:{user_id}:{today}", 2 * cache.DAY) or {}).get("n", 0))


async def run_task(db: Session, auto: Automation, *, manual: bool = False, ask=None, now: datetime | None = None) -> dict:
    """跑一次任务。定时触发的受每日次数上限约束；用户手动点的不受限。"""
    now = now or datetime.now()
    today, settings, uid = now.date(), get_settings(), auto.user_id
    capped = not manual and _runs_today(uid, today) >= settings.auto_daily_runs_max
    # 先把“这个时点处理过了”落库：研究要跑一分钟，中途进程退出也不会在下次启动时反复重跑
    auto.last_run_at = now
    if capped:
        auto.last_status, auto.last_result = "skipped", f"今天自动跑的研究已到上限（{settings.auto_daily_runs_max} 次），这次没有跑"
    db.add(auto)
    db.commit()
    if capped:
        return serialize(auto, now)
    if not manual:
        cache.write(f"autoruns:{uid}:{today}", {"n": _runs_today(uid, today) + 1})

    if ask is None:
        from wealthpilot.services.local_run import stream_local as ask
    answer, meta, error = "", {}, ""
    try:
        async for event in ask(auto.prompt, [], f"auto-{auto.id}-{now:%Y%m%d%H%M}", depth=auto.depth, user_id=auto.user_id):
            if event.get("type") == "done":
                answer, meta = event.get("content") or "", event.get("meta") or {}
            elif event.get("type") == "error":
                error = str(event.get("content") or "")
    except Exception as e:  # noqa: BLE001 — 一条任务失败不能带倒调度循环
        error = f"{type(e).__name__}: {e}"

    card = meta.get("summary") or {}
    if answer and meta.get("status") in ("passed", "partial"):
        auto.last_status, auto.last_message_id = "ok", meta.get("message_id")
        auto.last_result = card.get("conclusion") or summary.conclusion(answer, 300)
    else:
        auto.last_status = "failed"
        auto.last_result = (error or f"这次研究没有产出可发布的结论（{meta.get('status') or '无结果'}）")[:300]
    db.add(auto)
    db.commit()
    db.refresh(auto)

    ok = auto.last_status == "ok"
    memory.record(db, auto.user_id, "automation/ran", auto.title,
                  {"id": auto.id, "status": auto.last_status, "manual": manual, "message_id": auto.last_message_id,
                   "usage": meta.get("usage") or {}}, actor="system")
    _append_digest(db, auto.user_id, {"kind": "task", "code": "", "name": auto.title, "held": True, "status": auto.last_status,
                                      "text": auto.last_result[:200], "message_id": auto.last_message_id}, today)
    lines = [f"⏰ {auto.title}" + ("" if ok else "（没跑成）"), auto.last_result]
    if ok and card.get("truncated"):
        lines.append("（完整内容在电脑上的研究记录里）")
    await channels.notify("\n".join(lines))
    return serialize(auto, now)


# ── 提醒：越过条件就说一声 ──────────────────────────────

async def _valuation(code: str) -> dict:
    async def load():
        history = await stocks.fetch_valuation_history(code)
        return stocks.summarize_valuation(history) if history else {}
    return await cache.cached(f"alertval:{code}", 6 * cache.HOUR, load) or {}


async def current_value(metric: str, code: str, quote: dict | None = None) -> float | None:
    """提醒用的当前值。取不到返回 None —— 取不到就不判，绝不拿默认值去触发。"""
    if metric in ("price", "change_pct"):
        if quote is None:
            quote = (await fetch_sina_quotes([code])).get(code)
        if not quote or not quote.get("price"):   # 停牌、取数失败：没有价格就不判
            return None
        value = quote.get(metric)
        return float(value) if value is not None else None
    summary = await _valuation(code)
    value = (summary.get("pe" if metric == "pe_percentile" else "pb") or {}).get("percentile")
    return float(value) if value is not None else None


def hit(auto: Automation, value: float) -> bool:
    return value >= auto.threshold if auto.op == ">=" else value <= auto.threshold


async def check_alerts(db: Session, user_id: int, now: datetime | None = None) -> list[dict]:
    """看一遍这个用户开着的提醒，返回这次触发的。"""
    now = now or datetime.now()
    alerts = [a for a in db.exec(select(Automation).where(
        Automation.user_id == user_id, Automation.kind == "alert", Automation.enabled == True)).all()  # noqa: E712
        if not (a.last_run_at and a.last_run_at.date() == now.date() and a.last_status == "fired")]
    if not alerts:
        return []
    quotes = await fetch_sina_quotes(sorted({a.code for a in alerts if a.metric in ("price", "change_pct")}))
    fired: list[dict] = []
    for auto in alerts:
        try:
            value = await current_value(auto.metric, auto.code, quotes.get(auto.code) or {})
        except Exception:  # noqa: BLE001
            value = None
        if value is None or not hit(auto, value):
            continue
        label, unit = ALERT_METRICS[auto.metric]
        auto.last_run_at, auto.last_status = now, "fired"
        auto.last_result = f"{label}现在是 {value:g}{unit}，已{'达到' if auto.op == '>=' else '低于'}你设的 {auto.threshold:g}{unit}"
        if not auto.repeat:
            auto.enabled = False   # 提醒一次就停，免得在阈值附近来回刷
        db.add(auto)
        db.commit()
        db.refresh(auto)
        memory.record(db, user_id, "automation/alert", auto.title, {"id": auto.id, "value": value, "threshold": auto.threshold})
        _append_digest(db, user_id, {"kind": "alert", "code": auto.code, "name": auto.name or auto.code, "held": True,
                                     "text": f"提醒：{auto.last_result}"}, now.date())
        await channels.notify(f"🔔 {auto.name or auto.code} {auto.code}\n{auto.last_result}"
                              + ("" if auto.repeat else "\n（这条提醒已停，要继续盯可以重新打开）"))
        fired.append(serialize(auto, now))
    return fired


# ── 调度：每分钟看一眼 ──────────────────────────────────

def market_hours(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 35)


_last_alert_check: dict[int, datetime] = {}


async def tick(db: Session, now: datetime | None = None, ask=None) -> dict:
    """调度循环每分钟调一次：到点的任务跑掉，盘中每五分钟看一次提醒（进程刚起来时先看一次）。"""
    now = now or datetime.now()
    ran, fired = [], []
    for auto in db.exec(select(Automation).where(Automation.kind == "task", Automation.enabled == True)).all():  # noqa: E712
        if due(auto, now):
            ran.append(await run_task(db, auto, ask=ask, now=now))
    for uid in sorted(set(db.exec(select(Automation.user_id).where(Automation.kind == "alert", Automation.enabled == True)).all())):  # noqa: E712
        last = _last_alert_check.get(uid)
        if last is None or (market_hours(now) and (now - last).total_seconds() >= ALERT_EVERY):
            _last_alert_check[uid] = now
            fired += await check_alerts(db, uid, now)
    return {"ran": ran, "fired": fired}
