"""AI Chat 路由 (SSE Streaming) — Multi-Agent 架构。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.schemas import ChatRequest
from wealthpilot.services.agents import chat_stream
from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(req: ChatRequest, db: Session = Depends(get_session)):
    """AI 对话（SSE streaming + Multi-Agent）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())

    nav_data: dict[str, float] = {}
    nav_history: dict[str, list[dict]] = {}
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price
        hist = await fetch_fund_nav(h.fund_code, 60)
        if hist:
            nav_history[h.fund_code] = hist

    return StreamingResponse(
        chat_stream(req.message, req.history, holdings, nav_data, nav_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
