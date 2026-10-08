"""事后验证与复盘：验证点、成绩单、操作建议单。"""

import contextlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import checkpoints, memory, proposals
from wealthpilot.services.deps import current_user_id
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_session

router = APIRouter(tags=["review"])


@router.get("/checkpoints")
async def list_checkpoints(code: str = "", status: str = "", message_id: int | None = None,
                           db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """验证点列表。读取前顺带核对到期的（6 小时内只核对一次）。"""
    with contextlib.suppress(Exception):  # 核对要联网，失败了照样返回已有的记录
        await checkpoints.verify_pending(db, user_id)
    return [checkpoints.serialize(c) for c in
            checkpoints.list_checkpoints(db, user_id, code=code, status=status, message_id=message_id)]


@router.post("/checkpoints/verify")
async def verify_now(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """立即核对全部未决的验证点。"""
    return await checkpoints.verify_pending(db, user_id, force=True)


@router.get("/checkpoints/scorecard")
def get_scorecard(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return {**checkpoints.scorecard(db, user_id), "advice_mode": get_settings().advice_mode, "broker": get_settings().broker}


@router.delete("/checkpoints/{checkpoint_id}")
def delete_checkpoint(checkpoint_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    cp = db.get(Checkpoint, checkpoint_id)
    if cp is None or cp.user_id != user_id:
        raise HTTPException(404, "验证点不存在")
    if cp.status in ("held", "broken"):
        # 已经核对出结果的不许删，否则成绩单可以靠删掉证伪的条目来美化
        raise HTTPException(409, "已核对出结果的验证点不能删除")
    db.delete(cp)
    db.commit()
    return {"ok": True}


# ── 操作建议单 ──────────────────────────────────────────

class Authorize(BaseModel):
    shares: int = Field(..., gt=0, description="数量（股）")
    price: float | None = Field(default=None, gt=0, description="实际成交价；模拟盘按最新价成交，不需要填")


def _guard(work):
    """把服务层的错误原样转成 HTTP 响应。"""
    try:
        return work()
    except proposals.ProposalError as e:
        raise HTTPException(e.status, str(e)) from e


@router.get("/proposals")
def list_proposals(status: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    stmt = select(TradeProposal).where(TradeProposal.user_id == user_id)
    if status:
        stmt = stmt.where(TradeProposal.status == status)
    return [checkpoints.serialize_proposal(p) for p in db.exec(stmt.order_by(TradeProposal.created_at.desc()).limit(100)).all()]


@router.post("/proposals/{proposal_id}/authorize")
async def authorize_proposal(proposal_id: int, req: Authorize, db: Session = Depends(get_session),
                             user_id: int = Depends(current_user_id)):
    """用户授权后执行：开了模拟盘就按最新价下单，没开就把填回来的成交记入持仓台账。"""
    try:
        return checkpoints.serialize_proposal(await proposals.authorize(db, user_id, proposal_id, req.shares, req.price))
    except proposals.ProposalError as e:
        raise HTTPException(e.status, str(e)) from e


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, body: dict | None = None, db: Session = Depends(get_session),
                    user_id: int = Depends(current_user_id)):
    """不采纳。可以带上原因 —— 原因会记进投资者记忆，下次研究这只股票时 Agent 会看到。"""
    reason = str((body or {}).get("reason") or "")
    return checkpoints.serialize_proposal(_guard(lambda: proposals.reject(db, user_id, proposal_id, reason)))


# ── 投资者记忆与审计日志 ────────────────────────────────

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=2, max_length=300)
    code: str = Field(default="", pattern=r"^(\d{6})?$")


@router.get("/memory")
def list_memory(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return [memory.serialize(m) for m in memory.list_memories(db, user_id)]


@router.post("/memory", status_code=201)
def add_memory(req: MemoryCreate, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return memory.serialize(memory.add(db, user_id, req.content, kind="note", code=req.code, source="manual"))


@router.delete("/memory/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    if not memory.remove(db, user_id, memory_id):
        raise HTTPException(404, "这条记忆不存在")
    return {"ok": True}


@router.get("/stances")
async def stance_scorecard(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """立场成绩单：给过立场的个股研究，之后相对沪深 300 的表现。"""
    from wealthpilot.services import stance
    return await stance.scorecard(db, user_id)


@router.post("/trades/check")
async def trades_check(body: dict):
    """交易记录体检：贴成交记录进来，找反复出现的行为毛病。记录只在这次计算里用，不保存。"""
    from wealthpilot.services import trades
    text = str(body.get("text") or "")
    if len(text) > 2_000_000:
        raise HTTPException(413, "内容太大了。导出最近一两年的成交记录就够。")
    return await trades.check(text)


@router.get("/lessons")
def list_lessons(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """它自己记下的经验：判断落空时自动记的，和它归纳出来的规律。"""
    from wealthpilot.services import lessons
    return [memory.serialize(m) for m in lessons.list_lessons(db, user_id)]


@router.post("/lessons/reflect")
async def reflect(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """让模型把已核对的判断归纳一次（会调用一次模型，所以只在用户点的时候跑）。"""
    import asyncio

    from wealthpilot.services import lessons
    from wealthpilot.services.ai_client import create_ai_client, diagnose

    settings = get_settings()
    try:
        client = create_ai_client(settings)
        saved = await asyncio.to_thread(lessons.reflect, db, user_id, client, settings.light_model or settings.active_model)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:  # noqa: BLE001
        known = diagnose(e)
        raise HTTPException(502, known.message if known else f"模型没有返回可用的结果：{str(e)[:200]}") from e
    return {"added": [memory.serialize(m) for m in saved]}


@router.get("/audit")
def audit_log(limit: int = 100, kind: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """审计日志，新的在前。只读：没有修改和删除的接口。"""
    return {"events": memory.events(db, user_id, limit, kind), "integrity": memory.verify(db, user_id)}
