"""模拟盘 —— 把"建议 → 授权 → 下单 → 成交 → 持仓"这条链路先在不动真钱的地方跑通。

模拟盘按最新价即时成交，规则尽量贴近 A 股：买入整手、T+1、佣金与印花税、资金不足拒单。
下单只有两个入口：用户授权一条建议单，或用户自己在页面 / 终端下单。Agent 的工具集里没有下单。

接真实券商时实现同样的 account / place_order / positions 即可；那一步需要选定券商后再做。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, select

from wealthpilot.models.broker import Order, PaperAccount, PaperPosition
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.assets import fetch_sina_quotes
from wealthpilot.services.stocks import fetch_stock_profile, fetch_stock_quote
from wealthpilot.settings import get_settings

COMMISSION_RATE, COMMISSION_MIN, STAMP_RATE = 0.00025, 5.0, 0.0005


def enabled() -> bool:
    return get_settings().broker == "paper"


def fees(side: str, amount: float) -> float:
    fee = max(COMMISSION_MIN, amount * COMMISSION_RATE)
    return round(fee + (amount * STAMP_RATE if side == "sell" else 0), 2)


def get_account(db: Session, user_id: int) -> PaperAccount:
    account = db.get(PaperAccount, user_id)
    if account is None:
        cash = float(get_settings().paper_initial_cash)
        account = PaperAccount(user_id=user_id, cash=cash, initial_cash=cash)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def _positions(db: Session, user_id: int) -> list[PaperPosition]:
    return list(db.exec(select(PaperPosition).where(PaperPosition.user_id == user_id)).all())


def _bought_today(db: Session, user_id: int, code: str, today: date) -> int:
    rows = db.exec(select(Order).where(Order.user_id == user_id, Order.code == code, Order.side == "buy",
                                       Order.status == "filled")).all()
    return sum(o.shares for o in rows if o.created_at.date() == today)


async def place_order(db: Session, user_id: int, *, code: str, side: str, shares: int, name: str = "",
                      asset_type: str = "stock", proposal_id: int | None = None, today: date | None = None) -> Order:
    """下一笔模拟盘委托，按最新价即时成交。不满足规则的记为 rejected 并写明原因，不抛异常。"""
    today = today or date.today()
    order = Order(user_id=user_id, code=code, name=name, side=side, shares=int(shares), proposal_id=proposal_id)

    def reject(reason: str) -> Order:
        order.status, order.reason = "rejected", reason
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    if side not in ("buy", "sell") or order.shares <= 0:
        return reject("方向或数量不合法")
    quote = await fetch_stock_quote(code)
    if not quote or not quote.get("price"):
        return reject("取不到最新价，无法成交")
    order.name = order.name or quote.get("name", "")
    order.price = float(quote["price"])
    order.amount = round(order.price * order.shares, 2)
    order.fee = fees(side, order.amount)
    account = get_account(db, user_id)
    position = next((p for p in _positions(db, user_id) if p.code == code), None)

    if side == "buy":
        if order.shares % 100:
            return reject("买入数量必须是 100 股的整数倍")
        if account.cash < order.amount + order.fee:
            return reject(f"资金不足：可用 {account.cash:,.2f}，需要 {order.amount + order.fee:,.2f}")
        account.cash = round(account.cash - order.amount - order.fee, 2)
        if position:
            total = position.shares + order.shares
            position.cost_price = round((position.shares * position.cost_price + order.amount) / total, 4)
            position.shares, position.updated_at = total, datetime.now()
        else:
            position = PaperPosition(user_id=user_id, code=code, name=order.name, asset_type=asset_type,
                                     shares=order.shares, cost_price=order.price)
        db.add(position)
    else:
        held = position.shares if position else 0
        sellable = held - _bought_today(db, user_id, code, today)   # T+1：当天买的当天不能卖
        if order.shares > sellable:
            return reject(f"可卖数量不足：持有 {held} 股，其中今日买入的不可卖，可卖 {max(sellable, 0)} 股")
        if order.shares % 100 and order.shares != held:
            return reject("卖出零股只能一次性全部卖出")
        account.cash = round(account.cash + order.amount - order.fee, 2)
        position.shares -= order.shares
        position.updated_at = datetime.now()
        if position.shares == 0:
            db.delete(position)
        else:
            db.add(position)
    db.add(account)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


async def overview(db: Session, user_id: int) -> dict:
    account = get_account(db, user_id)
    positions = _positions(db, user_id)
    quotes = await fetch_sina_quotes([p.code for p in positions])
    rows, market_value = [], 0.0
    for p in sorted(positions, key=lambda p: p.code):
        price = (quotes.get(p.code) or {}).get("price")
        value = (price or p.cost_price) * p.shares
        market_value += value
        rows.append({"code": p.code, "name": p.name, "asset_type": p.asset_type, "shares": p.shares, "cost_price": p.cost_price,
                     "price": price, "market_value": round(value, 2),
                     "pnl": round((price - p.cost_price) * p.shares, 2) if price else None,
                     "pnl_pct": round((price / p.cost_price - 1) * 100, 2) if price else None})
    total = account.cash + market_value
    return {"mode": get_settings().broker, "cash": round(account.cash, 2), "initial_cash": account.initial_cash,
            "market_value": round(market_value, 2), "total_assets": round(total, 2),
            "total_pnl": round(total - account.initial_cash, 2),
            "total_pnl_pct": round((total / account.initial_cash - 1) * 100, 2), "positions": rows,
            "rules": "按最新价即时成交（非交易时段为最近收盘价）；买入整手、T+1；佣金万 2.5（最低 5 元），卖出另收印花税万 5"}


def list_orders(db: Session, user_id: int, limit: int = 50) -> list[Order]:
    return list(db.exec(select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(limit)).all())


def serialize_order(o: Order) -> dict:
    return {"id": o.id, "code": o.code, "name": o.name, "side": o.side, "shares": o.shares, "price": o.price, "amount": o.amount,
            "fee": o.fee, "status": o.status, "reason": o.reason, "proposal_id": o.proposal_id, "created_at": o.created_at.isoformat()}


async def sync_holdings(db: Session, user_id: int) -> dict:
    """把模拟盘持仓同步进组合：只动来源是 broker 的行，手工录入的（比如场外基金）不碰。"""
    positions = {p.code: p for p in _positions(db, user_id)}
    holdings = db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()
    manual = {h.fund_code for h in holdings if h.source != "broker"}
    result = {"added": 0, "updated": 0, "removed": 0, "skipped": []}
    for h in holdings:
        if h.source != "broker":
            continue
        p = positions.pop(h.fund_code, None)
        if p is None:
            db.delete(h)
            result["removed"] += 1
        elif (h.shares, h.cost_price) != (p.shares, p.cost_price):
            h.shares, h.cost_price, h.updated_at = p.shares, p.cost_price, datetime.now()
            db.add(h)
            result["updated"] += 1
    for code, p in positions.items():
        if code in manual:
            # 同一只票已经有手工录入的记录：不覆盖，交给用户自己处理
            result["skipped"].append(f"{p.name}（{code}）已有手工录入的持仓，未覆盖")
            continue
        profile = await fetch_stock_profile(code) if p.asset_type == "stock" else None
        db.add(PortfolioHolding(user_id=user_id, asset_type=p.asset_type, fund_code=code, fund_name=p.name, shares=p.shares,
                                cost_price=p.cost_price, buy_date=date.today(), industry=(profile or {}).get("industry", ""),
                                source="broker"))
        result["added"] += 1
    db.commit()
    return result


def reset(db: Session, user_id: int, cash: float | None = None) -> None:
    """清空模拟盘重新开始（委托记录保留）。"""
    for p in _positions(db, user_id):
        db.delete(p)
    account = get_account(db, user_id)
    account.cash = account.initial_cash = float(cash or get_settings().paper_initial_cash)
    db.add(account)
    db.commit()
