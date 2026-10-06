"""AI Chat 路由 (SSE Streaming) — Multi-Agent 架构。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.schemas import ChatRequest
from wealthpilot.routes.profile import load_profile
from wealthpilot.services.agents import chat_stream
from wealthpilot.services.context import load_market_context
from wealthpilot.services.deps import current_user_id, user_holdings
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(
    req: ChatRequest,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """AI 对话（SSE streaming + Multi-Agent）。"""
    holdings = user_holdings(db, user_id)

    nav_data, nav_history = await load_market_context(holdings)

    return StreamingResponse(
        chat_stream(
            req.message,
            req.history,
            holdings,
            nav_data,
            nav_history,
            conversation_id=req.conversation_id,
            db_session=db,
            profile=load_profile(db, user_id),
            user_id=user_id,
            depth=req.depth,
            rewrite_of=req.rewrite_of,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{conversation_id}")
def get_history(
    conversation_id: str,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """获取指定会话的历史消息（仅限本人的会话）。"""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at)
    )
    rows = db.exec(stmt).all()
    return [
        {
            "role": r.role,
            "content": r.content,
            "metadata": r.metadata_json,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
