"""持仓 CRUD 路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.schemas import PortfolioCreate, PortfolioResponse, PortfolioUpdate
from wealthpilot.services.assets import fetch_prices_by_type
from wealthpilot.services.deps import current_user_id, owned_holding, user_holdings
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioResponse])
async def list_holdings(
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    holdings = user_holdings(db, user_id)
    prices = await fetch_prices_by_type(
        [(h.fund_code, h.asset_type) for h in holdings]
    )
    from wealthpilot.services import fx
    results = []
    for h in holdings:
        latest_nav = prices.get(h.fund_code)
        fx_rate = await fx.factor(h.fund_code) if h.currency != "CNY" else None
        market_value = h.shares * latest_nav if latest_nav else None
        total_return = (latest_nav - h.cost_price) * h.shares if latest_nav else None
        return_pct = ((latest_nav - h.cost_price) / h.cost_price * 100) if latest_nav else None
        results.append(PortfolioResponse(
            id=h.id,
            asset_type=h.asset_type,
            fund_code=h.fund_code,
            fund_name=h.fund_name,
            shares=h.shares,
            cost_price=h.cost_price,
            buy_date=h.buy_date,
            category=h.category,
            industry=h.industry,
            latest_nav=latest_nav,
            market_value=round(market_value, 2) if market_value else None,
            total_return=round(total_return, 2) if total_return else None,
            return_pct=round(return_pct, 2) if return_pct else None,
            currency=h.currency, cost_native=h.cost_native, cost_fx=h.cost_fx, fx_rate=fx_rate,
            native_price=round(latest_nav / fx_rate, 3) if latest_nav and fx_rate else None,
        ))
    return results


@router.post("", response_model=PortfolioResponse, status_code=201)
async def add_holding(
    req: PortfolioCreate,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    from wealthpilot.services import fx
    from wealthpilot.services.sources import SourceError
    try:
        # 港股美股：填的是原币种的成本，按买入日的人民币中间价折成人民币入账。只看股票和 ETF —— BTC 这种代码长得像美股，但它是加密货币
        is_security = (req.asset_type or "fund").lower() in ("stock", "etf")
        booked = await fx.book(req.fund_code, req.cost_price, req.buy_date) if is_security else \
            {"code": req.fund_code, "currency": "CNY", "cost_price": req.cost_price, "cost_native": None, "cost_fx": None}
    except SourceError as e:
        raise HTTPException(503, str(e)) from e
    holding = PortfolioHolding(
        user_id=user_id,
        asset_type=(req.asset_type or "fund").lower(),
        fund_code=booked["code"],
        fund_name=req.fund_name,
        shares=req.shares,
        cost_price=booked["cost_price"],
        currency=booked["currency"], cost_native=booked["cost_native"], cost_fx=booked["cost_fx"],
        buy_date=req.buy_date,
        category=req.category,
        industry=req.industry,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return PortfolioResponse(
        id=holding.id,
        asset_type=holding.asset_type,
        fund_code=holding.fund_code,
        fund_name=holding.fund_name,
        shares=holding.shares,
        cost_price=holding.cost_price,
        buy_date=holding.buy_date,
        category=holding.category,
        industry=holding.industry,
        currency=holding.currency, cost_native=holding.cost_native, cost_fx=holding.cost_fx,
    )


@router.put("/{holding_id}", response_model=PortfolioResponse)
async def update_holding(
    holding_id: int,
    req: PortfolioUpdate,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    holding = owned_holding(db, holding_id, user_id)
    if not holding:
        raise HTTPException(status_code=404, detail="持仓不存在")
    changes = req.model_dump(exclude_unset=True)
    if holding.currency != "CNY" and changes.get("cost_price") is not None and changes["cost_price"] != holding.cost_native:
        # 港股美股改成本价：填的仍然是原币种的数，重新按买入日的汇率折一次
        from wealthpilot.services import fx
        from wealthpilot.services.sources import SourceError
        try:
            booked = await fx.book(holding.fund_code, changes["cost_price"], holding.buy_date)
        except SourceError as e:
            raise HTTPException(503, str(e)) from e
        changes |= {"cost_price": booked["cost_price"], "cost_native": booked["cost_native"], "cost_fx": booked["cost_fx"]}
    elif holding.currency != "CNY":
        changes.pop("cost_price", None)                  # 没改：账上的人民币成本不动
    for key, value in changes.items():
        setattr(holding, key, value)
    holding.updated_at = datetime.now()
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return PortfolioResponse(
        id=holding.id,
        asset_type=holding.asset_type,
        fund_code=holding.fund_code,
        fund_name=holding.fund_name,
        shares=holding.shares,
        cost_price=holding.cost_price,
        buy_date=holding.buy_date,
        category=holding.category,
        industry=holding.industry,
        currency=holding.currency, cost_native=holding.cost_native, cost_fx=holding.cost_fx,
    )


@router.delete("/{holding_id}")
def delete_holding(
    holding_id: int,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    holding = owned_holding(db, holding_id, user_id)
    if not holding:
        raise HTTPException(status_code=404, detail="持仓不存在")
    db.delete(holding)
    db.commit()
    return {"status": "deleted", "id": holding_id}
