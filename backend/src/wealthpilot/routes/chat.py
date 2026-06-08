"""AI Chat 路由 (SSE Streaming)。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.schemas import ChatRequest
from wealthpilot.services.agent import chat_stream
from wealthpilot.services.market_data import fetch_fund_info
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(req: ChatRequest, db: Session = Depends(get_session)):
    """AI 对话（SSE streaming）。"""
    holdings = list(db.exec(select(PortfolioHolding)).all())

    # 获取最新净值
    nav_data: dict[str, float] = {}
    for h in holdings:
        info = await fetch_fund_info(h.fund_code)
        if info:
            nav_data[h.fund_code] = info["nav"]
        else:
            nav_data[h.fund_code] = h.cost_price

    return StreamingResponse(
        chat_stream(req.message, req.history, holdings, nav_data),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
