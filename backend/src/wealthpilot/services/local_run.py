"""在本机进程里跑一次研究：终端、手机渠道、定时任务共用这一个入口。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from sqlmodel import Session

from wealthpilot.settings import get_settings


async def stream_local(message: str, history: list[dict] | None = None, conversation_id: str = "", *,
                       depth: str = "auto", rewrite_of: int | None = None, user_id: int | None = None) -> AsyncIterator[dict]:
    from wealthpilot.services.agents.orchestrator import chat_stream
    from wealthpilot.services.context import load_local_user, load_market_context
    from wealthpilot.storage.db import get_engine

    uid = get_settings().local_user_id if user_id is None else user_id
    holdings, profile = load_local_user(uid)
    nav_data, nav_history = await load_market_context(holdings)
    with Session(get_engine()) as db:
        async for line in chat_stream(message, history or [], holdings, nav_data, nav_history,
                                      conversation_id=conversation_id or None, db_session=db, profile=profile, user_id=uid,
                                      depth=depth, rewrite_of=rewrite_of):
            if line.startswith("data: "):
                yield json.loads(line[6:])
