"""持仓 CRUD 路由。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.schemas import PortfolioCreate, PortfolioResponse, PortfolioUpdate
from wealthpilot.services.market_data import fetch_fund_info
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioResponse])
async def list_holdings(db: Session = Depends(get_session)):
    holdings = list(db.exec(select(PortfolioHolding).order_by(PortfolioHolding.created_at)).all())
    results = []
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        latest_nav = info["nav"] if info else None
        market_value = h.shares * latest_nav if latest_nav else None
        total_return = (latest_nav - h.cost_price) * h.shares if latest_nav else None
        return_pct = ((latest_nav - h.cost_price) / h.cost_price * 100) if latest_nav else None
        results.append(PortfolioResponse(
            id=h.id,
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
        ))
    return results


@router.post("", response_model=PortfolioResponse, status_code=201)
def add_holding(req: PortfolioCreate, db: Session = Depends(get_session)):
    holding = PortfolioHolding(
        fund_code=req.fund_code,
        fund_name=req.fund_name,
        shares=req.shares,
        cost_price=req.cost_price,
        buy_date=req.buy_date,
        category=req.category,
        industry=req.industry,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return PortfolioResponse(
        id=holding.id,
        fund_code=holding.fund_code,
        fund_name=holding.fund_name,
        shares=holding.shares,
        cost_price=holding.cost_price,
        buy_date=holding.buy_date,
        category=holding.category,
        industry=holding.industry,
    )


@router.put("/{holding_id}", response_model=PortfolioResponse)
def update_holding(holding_id: int, req: PortfolioUpdate, db: Session = Depends(get_session)):
    holding = db.get(PortfolioHolding, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="持仓不存在")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(holding, key, value)
    holding.updated_at = datetime.now()
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return PortfolioResponse(
        id=holding.id,
        fund_code=holding.fund_code,
        fund_name=holding.fund_name,
        shares=holding.shares,
        cost_price=holding.cost_price,
        buy_date=holding.buy_date,
        category=holding.category,
        industry=holding.industry,
    )


@router.delete("/{holding_id}")
def delete_holding(holding_id: int, db: Session = Depends(get_session)):
    holding = db.get(PortfolioHolding, holding_id)
    if not holding:
        raise HTTPException(status_code=404, detail="持仓不存在")
    db.delete(holding)
    db.commit()
    return {"status": "deleted", "id": holding_id}
