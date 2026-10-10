"""外部数据缓存（SQLite）。

用法：
    rows = await cached("valuation:600519", DAY, lambda: fetch_valuation_history("600519"))

只缓存"取到了"的结果 —— 空结果（None / [] / {}）不落库，下次照常重试，
否则一次网络抖动会被放大成长时间的"没有数据"。

resilient 多做一件事：这次没取到时，拿上一次取到的那份顶上（哪怕已经过了有效期），并记下它是什么时候的。
数据源没有服务保障，“取不到”是常态；一份写明日期的旧数据，比一句“未获取到”有用。
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
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


# ── 取不到时用旧的顶上 ────────────────────────────────────

# 这一次调用里，哪些数据其实是旧的。工具执行器在开头清空、结尾读出来写进给模型的结果里
_stale_notes: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar("stale_notes", default=None)
_inflight: dict[tuple[int, str], asyncio.Future] = {}


def collect_stale() -> list[str]:
    """开始记“这次用了哪些旧数据”，返回那张清单（之后 resilient 会往里加）。"""
    notes: list[str] = []
    _stale_notes.set(notes)
    return notes


def _age(key: str) -> tuple[Any | None, float]:
    with Session(get_engine()) as session:
        row = session.get(DataCache, key)
        if row is None:
            return None, 0.0
        try:
            return json.loads(row.payload), row.fetched_at
        except ValueError:
            return None, 0.0


def _when(stamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))


async def resilient(key: str, ttl: float, loader: Callable[[], Awaitable[Any]], *, keep: float = 7 * DAY, what: str = "") -> Any:
    """有效期内直接给；过期了去取；取不到（出错或空的）而 keep 之内还留着旧的，就给旧的并记一笔。

    同一个 key 同时来了好几个请求（一次研究里几个 Agent 常常要同一份数据）只取一次。
    """
    if os.environ.get("WEALTHPILOT_NO_FETCH_CACHE"):      # 测试里各自造数据，不能互相读到对方缓存的
        return await loader()
    old, fetched_at = _age(key)
    if old is not None and time.time() - fetched_at <= ttl:
        return old
    loop = asyncio.get_running_loop()
    slot = (id(loop), key)
    running = _inflight.get(slot)
    if running is None:
        running = loop.create_future()
        _inflight[slot] = running
        try:
            try:
                value = await loader()
            except Exception:  # noqa: BLE001 — 取数失败在这里就是“没取到”
                value = None
            if value:
                write(key, value)
            running.set_result(value)
        finally:
            _inflight.pop(slot, None)
            if not running.done():
                running.set_result(None)
    value = await running
    if value:
        return value
    if old is not None and time.time() - fetched_at <= keep:
        notes = _stale_notes.get()
        if notes is not None:
            notes.append(f"{what or key}：数据源这次取不到，用的是 {_when(fetched_at)} 取到的那一份")
        return {**old, "stale_as_of": _when(fetched_at)} if isinstance(old, dict) else old
    return value
