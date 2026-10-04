"""研究相关路由：证券搜索、自选股、选股、研究记录。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.research import WatchItem
from wealthpilot.models.review import TradeProposal
from wealthpilot.services import checkpoints, screener
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


@router.get("/research/stats")
def research_stats(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    count = db.exec(select(func.count()).select_from(ChatMessage)
                    .where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant")).one()
    return {"research_count": count}
