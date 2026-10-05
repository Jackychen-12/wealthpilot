"""模拟盘、每日简报、公告正文、选股回测。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from wealthpilot.services import broker, filings, screener, watcher
from wealthpilot.services.deps import current_user_id
from wealthpilot.storage.db import get_session

router = APIRouter(tags=["broker"])


def _require_paper() -> None:
    if not broker.enabled():
        raise HTTPException(409, "模拟盘未开启：在 backend/.env 里设置 BROKER=paper 后重启")


class OrderRequest(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}$")
    side: str = Field(..., pattern="^(buy|sell)$")
    shares: int = Field(..., gt=0)
    name: str = ""
    asset_type: str = Field(default="stock", pattern="^(stock|etf)$")


@router.get("/broker")
async def broker_overview(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    if not broker.enabled():
        return {"mode": "none"}
    return await broker.overview(db, user_id)


@router.get("/broker/orders")
def broker_orders(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return [broker.serialize_order(o) for o in broker.list_orders(db, user_id)]


@router.post("/broker/orders")
async def place_order(req: OrderRequest, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """用户本人下一笔模拟盘委托。成交后持仓同步进组合。"""
    _require_paper()
    order = await broker.place_order(db, user_id, **req.model_dump())
    if order.status == "filled":
        await broker.sync_holdings(db, user_id)
    return broker.serialize_order(order)


@router.post("/broker/sync")
async def sync(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    _require_paper()
    return await broker.sync_holdings(db, user_id)


@router.post("/broker/reset")
async def reset(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    _require_paper()
    broker.reset(db, user_id)
    await broker.sync_holdings(db, user_id)
    return await broker.overview(db, user_id)


@router.get("/digest")
def digests(limit: int = 7, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return watcher.recent(db, user_id, max(1, min(limit, 30)))


@router.post("/digest/run")
async def run_digest(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """立即跑一次盯盘（也可以挂 cron 调这个接口）。"""
    return await watcher.run(db, user_id)


@router.get("/filings/{art_code}")
async def read_filing(art_code: str, keyword: str = "", page: int = 1):
    doc = await filings.read(art_code, keyword, page)
    if not doc:
        raise HTTPException(404, "未能读取这条公告的正文")
    return doc


@router.post("/screener/backtest")
async def backtest(body: dict):
    result = await screener.backtest_screen(dict(body.get("criteria") or {}), float(body.get("years") or 2), int(body.get("top_n") or 20))
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result
