"""研究相关路由：证券搜索、自选股、选股、研究记录。"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.research import WatchItem
from wealthpilot.models.review import TradeProposal
from wealthpilot.services import cache, checkpoints, screener, summary, watcher
from wealthpilot.services.assets import fetch_sina_quotes
from wealthpilot.services.deps import current_user_id
from wealthpilot.services.securities import search
from wealthpilot.storage.db import get_session

router = APIRouter(tags=["research"])


# ── 证券搜索 ────────────────────────────────────────────

@router.get("/securities/search")
async def search_securities(q: str, limit: int = 8):
    """按名称、简称或代码搜索 A 股、ETF、基金。"""
    return await search(q, max(1, min(limit, 20)))


# ── 自选股 ──────────────────────────────────────────────

class WatchCreate(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}$")
    name: str = ""
    asset_type: str = Field(default="stock", pattern="^(stock|etf|fund)$")
    note: str = Field(default="", max_length=200)


class WatchUpdate(BaseModel):
    note: str = Field(default="", max_length=200)


@router.get("/watchlist")
async def list_watchlist(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """自选列表，股票 / ETF 带上最新行情。"""
    items = list(db.exec(select(WatchItem).where(WatchItem.user_id == user_id).order_by(WatchItem.created_at.desc())).all())
    quotes = await fetch_sina_quotes([i.code for i in items if i.asset_type in ("stock", "etf")])
    return [{
        "id": i.id, "code": i.code, "name": i.name, "asset_type": i.asset_type, "note": i.note,
        "created_at": i.created_at.isoformat(),
        "price": quotes.get(i.code, {}).get("price"), "change_pct": quotes.get(i.code, {}).get("change_pct"),
    } for i in items]


@router.post("/watchlist", status_code=201)
def add_watch(req: WatchCreate, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    existing = db.exec(select(WatchItem).where(WatchItem.user_id == user_id, WatchItem.code == req.code)).first()
    if existing:
        return {"id": existing.id, "already": True}
    item = WatchItem(user_id=user_id, **req.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "already": False}


def _owned(db: Session, item_id: int, user_id: int) -> WatchItem:
    item = db.get(WatchItem, item_id)
    # 不区分"不存在"与"不是你的"，免得被用来枚举别人的自选
    if item is None or item.user_id != user_id:
        raise HTTPException(404, "自选项不存在")
    return item


@router.put("/watchlist/{item_id}")
def update_watch(item_id: int, req: WatchUpdate, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    item = _owned(db, item_id, user_id)
    item.note = req.note
    db.add(item)
    db.commit()
    return {"ok": True}


@router.delete("/watchlist/{item_id}")
def remove_watch(item_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    db.delete(_owned(db, item_id, user_id))
    db.commit()
    return {"ok": True}


# ── 选股与市场 ──────────────────────────────────────────

@router.post("/screener")
async def run_screener(criteria: dict):
    """按条件筛选全部 A 股。与 Agent 的 screen_stocks 工具是同一份实现。"""
    snap = await screener.snapshot()
    if not snap:
        raise HTTPException(503, "暂时取不到全市场快照，请稍后再试")
    return screener.screen(snap, criteria)


@router.get("/screener/industries")
async def list_industries():
    """行业列表（按成分股数量降序），给筛选表单用。"""
    snap = await screener.snapshot()
    counts: dict[str, int] = {}
    for s in snap.get("stocks", []):
        if s["industry"]:
            counts[s["industry"]] = counts.get(s["industry"], 0) + 1
    return [{"industry": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


# ── 研究记录 ────────────────────────────────────────────

@router.get("/research/history")
def research_history(limit: int = 30, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """本人做过的研究，最新在前。每条是一问一答。"""
    answers = db.exec(
        select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant",
                                  ChatMessage.conversation_id != "")
        .order_by(ChatMessage.created_at.desc()).limit(max(1, min(limit, 100)))
    ).all()
    out = []
    for a in answers:
        question = db.exec(
            select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "user",
                                      ChatMessage.conversation_id == a.conversation_id, ChatMessage.id < a.id)
            .order_by(ChatMessage.id.desc()).limit(1)
        ).first()
        try:
            meta = json.loads(a.metadata_json) if a.metadata_json else {}
        except ValueError:
            meta = {}
        out.append({
            "id": a.id, "conversation_id": a.conversation_id, "created_at": a.created_at.isoformat(),
            "question": question.content if question else "", "status": meta.get("status", ""),
            "playbook": meta.get("playbook", ""), "intent": meta.get("intent", ""),
            "securities": meta.get("securities", []), "evidence_count": len(meta.get("evidence", [])),
        })
    return out


@router.get("/research/history/{message_id}")
def research_detail(message_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    answer = db.get(ChatMessage, message_id)
    if answer is None or answer.user_id != user_id or answer.role != "assistant":
        raise HTTPException(404, "研究记录不存在")
    question = db.exec(
        select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "user",
                                  ChatMessage.conversation_id == answer.conversation_id, ChatMessage.id < answer.id)
        .order_by(ChatMessage.id.desc()).limit(1)
    ).first()
    try:
        meta = json.loads(answer.metadata_json) if answer.metadata_json else {}
    except ValueError:
        meta = {}
    return {"id": answer.id, "created_at": answer.created_at.isoformat(), "question": question.content if question else "",
            "answer": answer.content, "meta": meta,
            "checkpoints": [checkpoints.serialize(c) for c in checkpoints.list_checkpoints(db, user_id, message_id=answer.id)],
            "proposals": [checkpoints.serialize_proposal(p) for p in db.exec(
                select(TradeProposal).where(TradeProposal.user_id == user_id, TradeProposal.message_id == answer.id)).all()]}


def _meta(row: ChatMessage) -> dict:
    try:
        return json.loads(row.metadata_json) if row.metadata_json else {}
    except ValueError:
        return {}


_SOURCE = (("auto-", "定时任务"), ("tg-", "Telegram"), ("fs-", "飞书"), ("dd-", "钉钉"), ("wx-", "企业微信"))


@router.get("/conversations")
def conversations(limit: int = 30, q: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """会话列表，最近用过的在前。一个会话是连着问的几个问题；标题取第一个问题。

    给了 q 就只要提到过它的会话（问题、回答、研究过的证券里出现过），并带上命中的那一小段，方便认出是哪一次。
    """
    needle = q.strip().lower() if isinstance(q, str) else ""
    rows = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.conversation_id != "")
                   .order_by(ChatMessage.id.desc()).limit(6000 if needle else 800)).all()
    found: dict[str, dict] = {}
    hits: dict[str, str] = {}
    for row in rows:   # 新的在前：先见到的是最后一条，越往后越早
        if needle and row.conversation_id not in hits:
            at = row.content.lower().find(needle)
            if at >= 0:
                hits[row.conversation_id] = re.sub(r"\s+", " ", row.content[max(0, at - 24):at + len(needle) + 40]).strip()
        item = found.setdefault(row.conversation_id, {
            "id": row.conversation_id, "title": "", "turns": 0, "last_at": row.created_at.isoformat(), "securities": {},
            "source": next((label for prefix, label in _SOURCE if row.conversation_id.startswith(prefix)), ""), "last_status": ""})
        item["last_at"] = max(item["last_at"], row.created_at.isoformat())
        if row.role == "user":
            item["title"] = row.content[:60]          # 不断被更早的问题覆盖，最后留下的就是第一个问题
        else:
            item["turns"] += 1
            meta = _meta(row)
            item["last_status"] = item["last_status"] or meta.get("status", "")
            for s in meta.get("securities") or []:
                item["securities"].setdefault(s.get("code"), s)
    if needle:
        for cid, c in found.items():       # 问「宁德」也该找到只写了代码的那次：证券的名字和代码也算
            named = next((sec for sec in c["securities"].values() if needle in f"{sec.get('name', '')} {sec.get('code', '')}".lower()), None)
            if named and cid not in hits:
                hits[cid] = f"研究过 {named.get('name', '')} {named.get('code', '')}"
        found = {cid: {**c, "match": hits[cid]} for cid, c in found.items() if cid in hits}
    out = [{**c, "securities": list(c["securities"].values())[:4]} for c in found.values() if c["turns"]]
    return sorted(out, key=lambda c: c["last_at"], reverse=True)[:max(1, min(limit, 100))]


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """一个会话里的每一轮：问题、回答、当时的证据和校验结果。页面据此把会话整个恢复出来，接着问。"""
    rows = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
                   .order_by(ChatMessage.id)).all()
    if not rows:
        raise HTTPException(404, "没有这个会话")
    turns, question = [], ""
    for row in rows:
        if row.role == "user":
            question = row.content
            continue
        turns.append({
            "message_id": row.id, "created_at": row.created_at.isoformat(), "question": question, "answer": row.content, "meta": _meta(row),
            "checkpoints": [checkpoints.serialize(c) for c in checkpoints.list_checkpoints(db, user_id, message_id=row.id)],
            "proposals": [checkpoints.serialize_proposal(p) for p in db.exec(
                select(TradeProposal).where(TradeProposal.user_id == user_id, TradeProposal.message_id == row.id)).all()]})
        question = ""
    return {"id": conversation_id, "turns": turns}


@router.get("/research/stats")
def research_stats(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    count = db.exec(select(func.count()).select_from(ChatMessage)
                    .where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant")).one()
    return {"research_count": count}


# ── 工作台：围绕"我的股票"的汇总 ─────────────────────────

_THESIS_PLAYBOOKS = ("stock_deep", "stock_compare", "holding_review")
_conclusion, _stance = summary.conclusion, summary.stance


def _research_by_code(db: Session, user_id: int, limit: int = 150) -> dict[str, list[dict]]:
    """每只证券对应的研究记录（新的在前）。只算发布了的。"""
    rows = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant",
                                             ChatMessage.conversation_id != "")
                   .order_by(ChatMessage.created_at.desc()).limit(limit)).all()
    out: dict[str, list[dict]] = {}
    for m in rows:
        try:
            meta = json.loads(m.metadata_json) if m.metadata_json else {}
        except ValueError:
            continue
        # 只算完整的研究：问个价格这种窄问题不构成"对这只股票的判断"
        if meta.get("status") not in ("passed", "partial") or meta.get("playbook") not in _THESIS_PLAYBOOKS:
            continue
        codes = {s.get("code") for s in meta.get("securities") or []}
        codes |= set(re.findall(r"（(\d{6})）", " ".join(t.get("goal", "") for t in meta.get("tasks") or [])))
        for code in codes - {None}:
            out.setdefault(code, []).append({"id": m.id, "date": m.created_at.isoformat(), "status": meta.get("status"),
                                             "playbook": meta.get("playbook", ""), "answer": m.content})
    return out


@router.get("/research/latest")
def latest_research(code: str, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """这只股票最近一次研究的结论、立场和验证点状态；以及历次研究的日期（画在 K 线上）。"""
    records = _research_by_code(db, user_id).get(code, [])
    points = checkpoints.list_checkpoints(db, user_id, code=code)
    count = lambda s: sum(1 for c in points if c.status == s)  # noqa: E731
    # 判断卡要的是"对这只股票的结论"：持仓诊断讲的是整个组合，只用来标研究日期，不当作个股结论
    latest = next((r for r in records if r["playbook"] in ("stock_deep", "stock_compare")), None)
    name = points[0].name if points else ""
    return {
        "code": code,
        "latest": {"id": latest["id"], "date": latest["date"], "status": latest["status"], "playbook": latest["playbook"],
                   "conclusion": _conclusion(latest["answer"]), "stance": _stance(latest["answer"], name)} if latest else None,
        "research_dates": [r["date"][:10] for r in records],
        "checkpoints": {"total": len(points), "pending": count("pending"), "held": count("held"), "broken": count("broken")},
        "broken": [checkpoints.serialize(c) for c in points if c.status == "broken"][:3],
    }


@router.get("/desk")
async def desk(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """首页的工作台：我的每只股票现在怎么样、当初的判断还成立几条、有什么等我处理。"""
    targets = watcher.targets(db, user_id)
    quotes = await fetch_sina_quotes([t["code"] for t in targets])
    states = cache.read(f"watchstate:{user_id}", 3650 * cache.DAY) or {}
    points = checkpoints.list_checkpoints(db, user_id, limit=2000)
    research = _research_by_code(db, user_id)
    proposals = db.exec(select(TradeProposal).where(TradeProposal.user_id == user_id, TradeProposal.status == "proposed")).all()
    holdings = {h.fund_code: h for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()}

    from wealthpilot.services import fx
    stocks = []
    for t in targets:
        code, quote, mine = t["code"], quotes.get(t["code"]) or {}, [c for c in points if c.code == t["code"]]
        last = (research.get(code) or [None])[0]
        h = holdings.get(code)
        price = quote.get("price")
        # 现价照行情的原币种给人看；市值和持有收益是账上的事，账是人民币的，港股美股要先折算（取不到汇率就不算）
        in_cny = price * factor if h and price and (factor := await fx.factor(code)) else None
        stocks.append({
            "code": code, "name": t["name"], "asset_type": t["asset_type"], "held": t["held"],
            "price": price, "change_pct": quote.get("change_pct"), "currency": fx.currency_of(code),
            "market_value": round(h.shares * in_cny, 2) if in_cny else None,
            "return_pct": round((in_cny / h.cost_price - 1) * 100, 2) if in_cny and h.cost_price else None,
            "pe_percentile": (states.get(code) or {}).get("pe_percentile"),
            "checkpoints": {s: sum(1 for c in mine if c.status == s) for s in ("pending", "held", "broken")},
            "last_research": {"id": last["id"], "date": last["date"][:10], "status": last["status"]} if last else None,
            "open_proposals": sum(1 for p in proposals if p.code == code),
        })
    # 需要处理的排前面：有建议单的、有被证伪的、持有的、当日波动大的
    stocks.sort(key=lambda s: (-s["open_proposals"], -s["checkpoints"]["broken"], not s["held"], -abs(s["change_pct"] or 0)))
    verified = sorted((c for c in points if c.status in ("held", "broken") and c.checked_at), key=lambda c: c.checked_at, reverse=True)
    digest = watcher.recent(db, user_id, 1)
    return {
        "stocks": stocks,
        "todo": {"proposals": len(proposals), "broken": sum(1 for c in points if c.status == "broken"),
                 "pending": sum(1 for c in points if c.status == "pending"),
                 "unresearched": sum(1 for s in stocks if s["last_research"] is None)},
        "verified_recent": [checkpoints.serialize(c) for c in verified[:5]],
        "digest": digest[0] if digest else None,
        "sample": _has_sample(db, user_id),
    }


@router.get("/market/movers")
async def movers(limit: int = 8, min_mv_yi: float = 100):
    """当日涨幅榜与跌幅榜（默认只看市值 100 亿以上的，免得全是小票）。"""
    snap = await screener.snapshot()
    rows = [s for s in snap.get("stocks", []) if s["change_pct"] is not None and (s["total_mv_yi"] or 0) >= min_mv_yi
            and "ST" not in s["name"].upper()]
    pick = lambda r: {k: r[k] for k in ("code", "name", "industry", "price", "change_pct", "total_mv_yi")}  # noqa: E731
    ranked = sorted(rows, key=lambda r: r["change_pct"])
    limit = max(1, min(limit, 20))
    return {"trade_date": snap.get("trade_date"), "min_mv_yi": min_mv_yi,
            "gainers": [pick(r) for r in reversed(ranked[-limit:])], "losers": [pick(r) for r in ranked[:limit]]}


# ── 示例数据：第一次打开不至于一片空白 ──────────────────

_SAMPLE_HOLDINGS = [
    ("stock", "300750", "宁德时代", 100, 262.0, "电池"), ("stock", "600036", "招商银行", 600, 36.5, "银行"),
    ("stock", "000858", "五粮液", 200, 78.4, "白酒"), ("etf", "510300", "沪深300ETF华泰柏瑞", 5000, 3.95, "宽基"),
    ("fund", "110011", "易方达优质精选混合", 2500, 4.35, "消费"),
]
_SAMPLE_WATCH = [("600519", "贵州茅台"), ("601899", "紫金矿业")]
_SAMPLE_NOTE = "示例"


def _has_sample(db: Session, user_id: int) -> bool:
    return db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id, PortfolioHolding.source == "sample")).first() is not None


@router.post("/sample")
def load_sample(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """放一份示例持仓和自选进来。都打了"示例"标记，随时可以一键清掉，不会和你自己录的混在一起。"""
    from datetime import date

    held = {h.fund_code for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()}
    watched = {w.code for w in db.exec(select(WatchItem).where(WatchItem.user_id == user_id)).all()}
    for asset_type, code, name, shares, cost, industry in _SAMPLE_HOLDINGS:
        if code not in held:
            db.add(PortfolioHolding(user_id=user_id, asset_type=asset_type, fund_code=code, fund_name=name, shares=shares,
                                    cost_price=cost, buy_date=date(2025, 3, 3), industry=industry, source="sample"))
    for code, name in _SAMPLE_WATCH:
        if code not in watched:
            db.add(WatchItem(user_id=user_id, code=code, name=name, asset_type="stock", note=_SAMPLE_NOTE))
    db.commit()
    return {"ok": True}


@router.delete("/sample")
def clear_sample(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    removed = 0
    for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id, PortfolioHolding.source == "sample")).all():
        db.delete(h)
        removed += 1
    for w in db.exec(select(WatchItem).where(WatchItem.user_id == user_id, WatchItem.note == _SAMPLE_NOTE)).all():
        db.delete(w)
        removed += 1
    db.commit()
    return {"ok": True, "removed": removed}
