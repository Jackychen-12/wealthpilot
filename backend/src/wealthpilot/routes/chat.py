"""AI Chat 路由 (SSE Streaming) — Multi-Agent 架构。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.schemas import ChatRequest
from wealthpilot.services import runs
from wealthpilot.services.deps import current_user_id
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


_SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


async def _sse(run: runs.Run, start: int = 0):
    async for event in runs.subscribe(run, start):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(req: ChatRequest, user_id: int = Depends(current_user_id)):
    """发起一次研究并订阅它的过程（SSE）。

    研究在服务端独立运行：这个连接断了（关标签页、刷新、网络抖动）它照样跑完、照样存进研究记录。
    第一条事件带 run_id，页面可以凭它重新接上（GET /chat/runs/{id}/events）或明确叫停（POST /chat/runs/{id}/stop）。
    """
    run = runs.start(user_id, req.message, req.history, req.conversation_id or "", depth=req.depth, rewrite_of=req.rewrite_of)
    return StreamingResponse(_sse(run), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/runs/active")
def active_runs(user_id: int = Depends(current_user_id)):
    """还在跑的研究。页面刷新后用它找回正在进行的那一次。"""
    return runs.active(user_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, start: int = 0, user_id: int = Depends(current_user_id)):
    """重新接上一次研究：从第 start 个事件开始（0 = 从头重放）。"""
    run = runs.get(run_id, user_id)
    if run is None:
        raise HTTPException(404, "找不到这次研究：可能已经结束很久，结果在研究记录里")
    return StreamingResponse(_sse(run, start), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, user_id: int = Depends(current_user_id)):
    """明确叫停。只有这里会取消研究；断开连接不会。"""
    run = runs.get(run_id, user_id)
    if run is None:
        raise HTTPException(404, "找不到这次研究")
    runs.stop(run)
    return {"ok": True}


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
