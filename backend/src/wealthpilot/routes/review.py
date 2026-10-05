"""事后验证与复盘：验证点、成绩单、操作建议单。"""

import contextlib
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import broker, checkpoints, memory
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


def _owned(db: Session, proposal_id: int, user_id: int) -> TradeProposal:
    p = db.get(TradeProposal, proposal_id)
    if p is None or p.user_id != user_id:
        raise HTTPException(404, "建议单不存在")
    if p.status != "proposed":
        raise HTTPException(409, "这条建议已经处理过了")
    return p


def _decided(db: Session, user_id: int, p: TradeProposal, outcome: str, reason: str = "") -> None:
    """审批结果进审计日志，同时记成一条"决定"：Agent 下次研究这只股票时知道用户上次怎么选的。
    outcome 沿用 DeepSeek Harness 审批子系统的取值：allowed-once 只授权这一次，rejected 为拒绝。"""
    label = checkpoints.ACTIONS.get(p.action, p.action)
    memory.record(db, user_id, "approval/decided", f"{label} {p.name}：{'授权' if outcome == 'allowed-once' else '不采纳'}",
                  {"proposal_id": p.id, "code": p.code, "action": p.action, "outcome": outcome, "shares": p.exec_shares,
                   "price": p.exec_price, "reason": reason}, actor="user")
    day = datetime.now().strftime("%Y-%m-%d")
    if outcome == "allowed-once":
        text = f"{day} 采纳了对{p.name}的{label}建议（{p.exec_shares} 股 @ {p.exec_price}）"
    else:
        text = f"{day} 没有采纳对{p.name}的{label}建议" + (f"，原因：{reason}" if reason else "")
    memory.add(db, user_id, text, kind="decision", code=p.code, source=f"proposal:{p.id}")


@router.get("/proposals")
def list_proposals(status: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    stmt = select(TradeProposal).where(TradeProposal.user_id == user_id)
    if status:
        stmt = stmt.where(TradeProposal.status == status)
    return [checkpoints.serialize_proposal(p) for p in db.exec(stmt.order_by(TradeProposal.created_at.desc()).limit(100)).all()]


@router.post("/proposals/{proposal_id}/authorize")
async def authorize_proposal(proposal_id: int, req: Authorize, db: Session = Depends(get_session),
                             user_id: int = Depends(current_user_id)):
    """用户授权后执行。

    开了模拟盘（BROKER=paper）：按最新价在模拟盘下单，成交后持仓同步进组合。
    没开：不下单，用户在自己的券商成交后把数量和价格填回来，记入持仓台账。
    """
    p = _owned(db, proposal_id, user_id)
    if broker.enabled():
        order = await broker.place_order(db, user_id, code=p.code, name=p.name, asset_type=p.asset_type,
                                         side="buy" if p.action in ("buy", "add") else "sell", shares=req.shares, proposal_id=p.id)
        if order.status != "filled":
            raise HTTPException(422, f"模拟盘拒单：{order.reason}")
        await broker.sync_holdings(db, user_id)
        p.status, p.exec_shares, p.exec_price, p.decided_at = "executed", order.shares, order.price, datetime.now()
        db.add(p)
        db.commit()
        db.refresh(p)
        _decided(db, user_id, p, "allowed-once")
        return checkpoints.serialize_proposal(p)
    if req.price is None:
        raise HTTPException(422, "请填写实际成交价")
    holding = db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id,
                                                     PortfolioHolding.fund_code == p.code)).first()
    if p.action in ("buy", "add"):
        if holding:
            total = holding.shares + req.shares
            holding.cost_price = round((holding.shares * holding.cost_price + req.shares * req.price) / total, 4)
            holding.shares = total
            holding.updated_at = datetime.now()
        else:
            holding = PortfolioHolding(user_id=user_id, asset_type=p.asset_type, fund_code=p.code, fund_name=p.name,
                                       shares=req.shares, cost_price=req.price, buy_date=date.today())
        db.add(holding)
    else:
        if holding is None or holding.shares < req.shares:
            raise HTTPException(422, f"持仓不足：当前持有 {int(holding.shares) if holding else 0} 股")
        holding.shares -= req.shares
        holding.updated_at = datetime.now()
        if holding.shares <= 0:
            db.delete(holding)
        else:
            db.add(holding)
    p.status, p.exec_shares, p.exec_price, p.decided_at = "executed", req.shares, req.price, datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    _decided(db, user_id, p, "allowed-once")
    return checkpoints.serialize_proposal(p)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, body: dict | None = None, db: Session = Depends(get_session),
                    user_id: int = Depends(current_user_id)):
    """不采纳。可以带上原因 —— 原因会记进投资者记忆，下次研究这只股票时 Agent 会看到。"""
    p = _owned(db, proposal_id, user_id)
    p.status, p.decided_at = "rejected", datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    _decided(db, user_id, p, "rejected", str((body or {}).get("reason") or "").strip())
    return checkpoints.serialize_proposal(p)


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


@router.get("/audit")
def audit_log(limit: int = 100, kind: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """审计日志，新的在前。只读：没有修改和删除的接口。"""
    return {"events": memory.events(db, user_id, limit, kind), "integrity": memory.verify(db, user_id)}
