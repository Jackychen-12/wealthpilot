"""外部数据缓存（SQLite）。

用法：
    rows = await cached("valuation:600519", DAY, lambda: fetch_valuation_history("600519"))

只缓存"取到了"的结果 —— 空结果（None / [] / {}）不落库，下次照常重试，
否则一次网络抖动会被放大成长时间的"没有数据"。
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlmodel import Session

from wealthpilot.models.research import DataCache
from wealthpilot.storage.db import get_engine

MINUTE, HOUR, DAY = 60.0, 3600.0, 86400.0


def read(key: str, ttl: float) -> Any | None:
    with Session(get_engine()) as session:
        row = session.get(DataCache, key)
        if row is None or time.time() - row.fetched_at > ttl:
            return None
        try:
            return json.loads(row.payload)
        except ValueError:
            return None


def write(key: str, value: Any) -> None:
    with Session(get_engine()) as session:
        session.merge(DataCache(key=key, payload=json.dumps(value, ensure_ascii=False), fetched_at=time.time()))
        session.commit()


async def cached(key: str, ttl: float, loader: Callable[[], Awaitable[Any]]) -> Any:
    hit = read(key, ttl)
    if hit is not None:
        return hit
    value = await loader()
    if value:
        write(key, value)
    return value
