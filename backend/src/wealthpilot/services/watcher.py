"""每日盯盘 —— 让工具自己干活，而不是等人想起来才打开。

每个交易日收盘后跑一次：核对到期的验证点，同步模拟盘持仓，检查自选和持仓里每只股票
有没有值得知道的变化（大涨大跌、新财报、估值分位跨档、重要公告），写成一份当日简报。
有事才推送；什么都没发生就只留一条"今日无事"的记录。全程不调用模型。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import date, datetime

import httpx
from sqlmodel import Session, select

from wealthpilot.models.broker import Digest
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.research import WatchItem
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import broker, cache, checkpoints, filings, stocks
from wealthpilot.services.assets import fetch_sina_quotes
from wealthpilot.settings import get_settings

_FOREVER = 3650 * cache.DAY


def _band(percentile: float | None) -> str:
    if percentile is None:
        return ""
    return "low" if percentile <= 20 else "high" if percentile >= 80 else "mid"


_BAND_TEXT = {"low": "低位（≤20%）", "mid": "中间区域", "high": "高位（≥80%）"}


def targets(db: Session, user_id: int) -> list[dict]:
    """要盯的股票和 ETF：持仓在前，自选在后，去重。"""
    seen: dict[str, dict] = {}
    for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all():
        if h.asset_type in ("stock", "etf"):
            seen.setdefault(h.fund_code, {"code": h.fund_code, "name": h.fund_name, "asset_type": h.asset_type, "held": True})
    for w in db.exec(select(WatchItem).where(WatchItem.user_id == user_id)).all():
        if w.asset_type in ("stock", "etf"):
            seen.setdefault(w.code, {"code": w.code, "name": w.name, "asset_type": w.asset_type, "held": False})
    return list(seen.values())


async def _inspect(target: dict, state: dict, quote: dict | None, move_pct: float) -> tuple[list[dict], dict]:
    """检查一只股票，返回（事件, 新状态）。state 为空表示第一次见到它：只记基线，不报"新"财报和公告。"""
    code, first_time = target["code"], not state
    events: list[dict] = []
    new_state = dict(state)

    def event(kind: str, text: str, **extra) -> None:
        events.append({"kind": kind, "code": code, "name": target["name"], "held": target["held"], "text": text, **extra})

    change = (quote or {}).get("change_pct")
    if change is not None and abs(change) >= move_pct:
        event("move", f"当日{'上涨' if change > 0 else '下跌'} {abs(change):.2f}%，收于 {quote.get('price')}", change_pct=change)

    is_stock = target["asset_type"] == "stock"
    reports, history, listing = await asyncio.gather(
        stocks.fetch_financial_indicators(code, 1) if is_stock else asyncio.sleep(0, []),
        stocks.fetch_valuation_history(code) if is_stock else asyncio.sleep(0, []),
        filings.list_filings(code, 15), return_exceptions=True)

    if isinstance(reports, list) and reports:
        r = reports[0]
        if not first_time and r["report_date"] > state.get("report_date", ""):
            event("report", f"披露 {r['report_name']}：营收同比 {r.get('revenue_yoy_pct')}%，归母净利润同比 {r.get('net_profit_yoy_pct')}%",
                  report_date=r["report_date"])
        new_state["report_date"] = max(r["report_date"], state.get("report_date", ""))
    if isinstance(history, list) and history:
        pe = (stocks.summarize_valuation(history).get("pe") or {}).get("percentile")
        band = _band(pe)
        if band and not first_time and state.get("pe_band") and band != state["pe_band"]:
            event("valuation", f"PE 历史分位 {pe}%，由{_BAND_TEXT[state['pe_band']]}进入{_BAND_TEXT[band]}", percentile=pe)
        if band:
            new_state["pe_band"] = band
    if isinstance(listing, list) and listing:
        last = state.get("last_filing", "")
        if not first_time:
            for f in [f for f in listing if f["art_code"] > last and filings.is_important(f)][:3]:
                event("filing", f"公告（{f['date']}）：{f['title']}", art_code=f["art_code"], url=f["url"])
        new_state["last_filing"] = max([f["art_code"] for f in listing] + [last])
    return events, new_state


async def run(db: Session, user_id: int, *, today: date | None = None, push: bool = True) -> dict:
    """跑一次盯盘，写入（或覆盖）当天的简报。"""
    settings = get_settings()
    today = today or date.today()
    started = datetime.now()
    events: list[dict] = []

    # 1) 核对到期的验证点
    with contextlib.suppress(Exception):  # 核对失败不该拦住后面的检查
        await checkpoints.verify_pending(db, user_id, force=True, today=today)
    for cp in db.exec(select(Checkpoint).where(Checkpoint.user_id == user_id, Checkpoint.checked_at >= started)).all():
        if cp.status in ("held", "broken"):
            label = checkpoints.METRICS.get(cp.metric, (cp.metric,))[0]
            events.append({"kind": "checkpoint", "code": cp.code, "name": cp.name, "held": True, "status": cp.status,
                           "text": f"验证点{'成立' if cp.status == 'held' else '被证伪'}：{label} {cp.op} {cp.threshold:g}，"
                                   f"实际 {cp.actual_value:g}（{cp.actual_as_of}）"})

    # 2) 模拟盘持仓同步进组合
    if broker.enabled():
        try:
            synced = await broker.sync_holdings(db, user_id)
            if synced["added"] or synced["updated"] or synced["removed"]:
                events.append({"kind": "sync", "code": "", "name": "模拟盘", "held": True,
                               "text": f"持仓已同步：新增 {synced['added']}，更新 {synced['updated']}，移除 {synced['removed']}"})
        except Exception:  # noqa: BLE001
            pass

    # 3) 逐只检查持仓与自选
    watch = targets(db, user_id)
    key = f"watchstate:{user_id}"
    states: dict = cache.read(key, _FOREVER) or {}
    quotes = await fetch_sina_quotes([t["code"] for t in watch])
    gate = asyncio.Semaphore(5)

    async def one(target: dict):
        async with gate:
            try:
                return await _inspect(target, states.get(target["code"], {}), quotes.get(target["code"]), settings.watch_move_pct)
            except Exception:  # noqa: BLE001 — 一只取数失败不影响其余
                return [], states.get(target["code"], {})

    for target, (found, new_state) in zip(watch, await asyncio.gather(*[one(t) for t in watch]), strict=True):
        events += found
        if new_state:
            states[target["code"]] = new_state
    if states:
        cache.write(key, states)

    # 4) 还没处理的建议单
    open_count = len(db.exec(select(TradeProposal).where(TradeProposal.user_id == user_id, TradeProposal.status == "proposed")).all())
    if open_count:
        events.append({"kind": "proposal", "code": "", "name": "", "held": True, "text": f"有 {open_count} 条操作建议单等你决定"})

    order = {"checkpoint": 0, "report": 1, "filing": 2, "valuation": 3, "move": 4, "proposal": 5, "sync": 6}
    events.sort(key=lambda e: (order.get(e["kind"], 9), not e["held"]))
    notable = [e for e in events if e["kind"] not in ("sync", "proposal")]
    summary = (f"盯了 {len(watch)} 只，{len(notable)} 件事值得看" if notable else f"盯了 {len(watch)} 只，今日无事") if watch \
        else "还没有持仓和自选，没有可盯的对象"

    digest = db.exec(select(Digest).where(Digest.user_id == user_id, Digest.day == str(today))).first() \
        or Digest(user_id=user_id, day=str(today))
    digest.events_json, digest.summary, digest.created_at = json.dumps(events, ensure_ascii=False), summary, datetime.now()
    db.add(digest)
    db.commit()
    db.refresh(digest)
    result = serialize(digest)
    if push and notable and settings.alert_webhook_url:
        result["pushed"] = await _push(settings.alert_webhook_url, result)
    return result


async def _push(url: str, digest: dict) -> bool:
    lines = [f"WealthPilot {digest['day']} · {digest['summary']}"] + [
        f"- {e['name']} {e['code']}：{e['text']}".replace("  ", " ") for e in digest["events"]]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # 同时带 text 与 content 两种常见字段，企业微信 / 飞书 / Slack 兼容的机器人都能收
            resp = await client.post(url, json={"msgtype": "text", "text": {"content": "\n".join(lines)},
                                                "content": "\n".join(lines), "digest": digest})
        return resp.status_code < 300
    except httpx.HTTPError:
        return False


def serialize(d: Digest) -> dict:
    try:
        events = json.loads(d.events_json)
    except ValueError:
        events = []
    return {"id": d.id, "day": d.day, "summary": d.summary, "events": events, "created_at": d.created_at.isoformat()}


def recent(db: Session, user_id: int, limit: int = 7) -> list[dict]:
    rows = db.exec(select(Digest).where(Digest.user_id == user_id).order_by(Digest.day.desc()).limit(limit)).all()
    return [serialize(d) for d in rows]


def _users(db: Session) -> list[int]:
    ids = set(db.exec(select(PortfolioHolding.user_id)).all()) | set(db.exec(select(WatchItem.user_id)).all())
    return sorted(ids)


async def scheduler() -> None:
    """后台循环：交易日到了设定时间、当天还没跑过，就给每个有持仓或自选的用户跑一次。"""
    from wealthpilot.storage.db import get_engine

    while True:
        try:
            settings = get_settings()   # 每轮重读：在网页上改了时间或关掉盯盘，不用重启
            hour, minute = (int(x) for x in settings.watch_time.split(":"))
            now = datetime.now()
            if settings.watch_enabled and now.weekday() < 5 and (now.hour, now.minute) >= (hour, minute):
                with Session(get_engine()) as db:
                    for uid in _users(db):
                        done = db.exec(select(Digest).where(Digest.user_id == uid, Digest.day == str(now.date()))).first()
                        if done is None:
                            await run(db, uid)
        except Exception:  # noqa: BLE001 — 调度循环不能因为一次失败就停
            pass
        await asyncio.sleep(600)
