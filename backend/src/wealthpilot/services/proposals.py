"""操作建议单的授权与拒绝。网页、终端、手机渠道都走这里，规则只有一份。"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.review import TradeProposal
from wealthpilot.services import broker, checkpoints, memory


class ProposalError(Exception):
    """带上 HTTP 状态码，路由可以原样转成响应；其它入口只用它的文字。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def owned(db: Session, user_id: int, proposal_id: int) -> TradeProposal:
    p = db.get(TradeProposal, proposal_id)
    if p is None or p.user_id != user_id:
        raise ProposalError(404, "建议单不存在")
    if p.status != "proposed":
        raise ProposalError(409, "这条建议已经处理过了")
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


async def authorize(db: Session, user_id: int, proposal_id: int, shares: int, price: float | None = None) -> TradeProposal:
    """用户授权后执行。

    开了模拟盘（BROKER=paper）：按最新价在模拟盘下单，成交后持仓同步进组合。
    没开：不下单，用户在自己的券商成交后把数量和价格填回来，记入持仓台账。
    """
    p = owned(db, user_id, proposal_id)
    if shares <= 0:
        raise ProposalError(422, "数量必须大于 0")
    if broker.enabled():
        order = await broker.place_order(db, user_id, code=p.code, name=p.name, asset_type=p.asset_type,
                                         side="buy" if p.action in ("buy", "add") else "sell", shares=shares, proposal_id=p.id)
        if order.status != "filled":
            raise ProposalError(422, f"模拟盘拒单：{order.reason}")
        await broker.sync_holdings(db, user_id)
        p.exec_shares, p.exec_price = order.shares, order.price
    else:
        if price is None or price <= 0:
            raise ProposalError(422, "请填写实际成交价")
        holding = db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id,
                                                         PortfolioHolding.fund_code == p.code)).first()
        if p.action in ("buy", "add"):
            if holding:
                total = holding.shares + shares
                holding.cost_price = round((holding.shares * holding.cost_price + shares * price) / total, 4)
                holding.shares, holding.updated_at = total, datetime.now()
            else:
                holding = PortfolioHolding(user_id=user_id, asset_type=p.asset_type, fund_code=p.code, fund_name=p.name,
                                           shares=shares, cost_price=price, buy_date=date.today())
            db.add(holding)
        else:
            if holding is None or holding.shares < shares:
                raise ProposalError(422, f"持仓不足：当前持有 {int(holding.shares) if holding else 0} 股")
            holding.shares -= shares
            holding.updated_at = datetime.now()
            if holding.shares <= 0:
                db.delete(holding)
            else:
                db.add(holding)
        p.exec_shares, p.exec_price = shares, price
    p.status, p.decided_at = "executed", datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    _decided(db, user_id, p, "allowed-once")
    return p


def reject(db: Session, user_id: int, proposal_id: int, reason: str = "") -> TradeProposal:
    """不采纳。原因会记进投资者记忆，下次研究这只股票时 Agent 会看到。"""
    p = owned(db, user_id, proposal_id)
    p.status, p.decided_at = "rejected", datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    _decided(db, user_id, p, "rejected", reason.strip())
    return p


def open_proposals(db: Session, user_id: int) -> list[TradeProposal]:
    return list(db.exec(select(TradeProposal).where(TradeProposal.user_id == user_id, TradeProposal.status == "proposed")
                        .order_by(TradeProposal.created_at.desc())).all())
