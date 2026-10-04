"""事后验证与复盘：验证点、成绩单、操作建议单。"""

import contextlib
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import checkpoints
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
    return {**checkpoints.scorecard(db, user_id), "advice_mode": get_settings().advice_mode}


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
    shares: int = Field(..., gt=0, description="实际成交数量（股）")
    price: float = Field(..., gt=0, description="实际成交价")


def _owned(db: Session, proposal_id: int, user_id: int) -> TradeProposal:
    p = db.get(TradeProposal, proposal_id)
    if p is None or p.user_id != user_id:
        raise HTTPException(404, "建议单不存在")
    if p.status != "proposed":
        raise HTTPException(409, "这条建议已经处理过了")
    return p


@router.get("/proposals")
def list_proposals(status: str = "", db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    stmt = select(TradeProposal).where(TradeProposal.user_id == user_id)
    if status:
        stmt = stmt.where(TradeProposal.status == status)
    return [checkpoints.serialize_proposal(p) for p in db.exec(stmt.order_by(TradeProposal.created_at.desc()).limit(100)).all()]


@router.post("/proposals/{proposal_id}/authorize")
def authorize_proposal(proposal_id: int, req: Authorize, db: Session = Depends(get_session),
                       user_id: int = Depends(current_user_id)):
    """用户授权后执行：把这笔操作记入持仓台账。

    这里不向券商下单 —— 用户在自己的券商成交后，把成交数量和价格填回来，持仓随之更新。
    """
    p = _owned(db, proposal_id, user_id)
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
    return checkpoints.serialize_proposal(p)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    p = _owned(db, proposal_id, user_id)
    p.status, p.decided_at = "rejected", datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    return checkpoints.serialize_proposal(p)
