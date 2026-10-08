"""研究在服务端跑，不绑在某一次网页连接上。

之前研究和发起它的那次 HTTP 请求绑在一起：标签页一关、页面一刷新，跑到一半的研究就被取消，
token 花了，结果没存。现在每次研究是一个独立的任务，事件记在内存里；页面只是"订阅"它 ——
断开不影响它跑完和落库，回来可以从头或从断点接着看。只有用户明确点了停止才会取消。

任务只存在于这个进程的内存里：进程退出就没了（不做后台常驻）。跑完的任务留半小时供回看，之后清掉；
研究结果本身在数据库的研究记录里。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

KEEP_SECONDS = 1800


class Run:
    def __init__(self, user_id: int, question: str, conversation_id: str, depth: str = "auto", rewrite_of: int | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.user_id, self.question, self.conversation_id = user_id, question, conversation_id
        self.depth, self.rewrite_of = depth, rewrite_of
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.events: list[dict] = [{"type": "run", "run_id": self.id}]
        self.task: asyncio.Task | None = None
        self._changed = asyncio.Event()

    @property
    def done(self) -> bool:
        return self.finished_at is not None

    def push(self, event: dict) -> None:
        self.events.append(event)
        self._changed.set()

    def finish(self) -> None:
        if self.finished_at is None:
            self.finished_at = time.time()
        self._changed.set()

    def describe(self) -> dict:
        return {"run_id": self.id, "question": self.question, "conversation_id": self.conversation_id, "depth": self.depth,
                "rewrite_of": self.rewrite_of, "started_at": self.started_at, "done": self.done, "events": len(self.events)}


_RUNS: dict[str, Run] = {}


def _sweep() -> None:
    cutoff = time.time() - KEEP_SECONDS
    for run_id in [k for k, r in _RUNS.items() if r.finished_at is not None and r.finished_at < cutoff]:
        del _RUNS[run_id]


async def _drive(run: Run, source: AsyncIterator[dict]) -> None:
    try:
        async for event in source:
            run.push(event)
        if not any(e.get("type") == "done" for e in run.events):
            run.push({"type": "done", "content": "这次研究没有产出结果。", "meta": {"status": "failed"}})
    except asyncio.CancelledError:
        run.push({"type": "done", "content": "已停止。", "meta": {"status": "stopped"}})
    except Exception as e:  # noqa: BLE001 — 任务自己兜住：没人在等它的时候也不能留下未处理的异常
        run.push({"type": "error", "content": f"研究执行异常：{e}"})
        run.push({"type": "done", "content": "研究执行异常，没有完成。", "meta": {"status": "failed"}})
    finally:
        run.finish()


def start(user_id: int, message: str, history: list[dict] | None = None, conversation_id: str = "", *,
          depth: str = "auto", rewrite_of: int | None = None, source: AsyncIterator[dict] | None = None) -> Run:
    """发起一次研究，立刻返回。source 是产出事件的异步迭代器，默认就是本机的研究流程。"""
    if source is None:
        from wealthpilot.services.local_run import stream_local
        source = stream_local(message, history, conversation_id, depth=depth, rewrite_of=rewrite_of, user_id=user_id)
    _sweep()
    run = Run(user_id, message, conversation_id, depth, rewrite_of)
    run.task = asyncio.create_task(_drive(run, source))
    _RUNS[run.id] = run
    return run


def get(run_id: str, user_id: int) -> Run | None:
    run = _RUNS.get(run_id)
    return run if run is not None and run.user_id == user_id else None


def active(user_id: int) -> list[dict]:
    """这个用户还在跑的研究（新的在前）。页面刷新后靠它找回正在跑的那一次。"""
    return [r.describe() for r in sorted(_RUNS.values(), key=lambda r: -r.started_at) if r.user_id == user_id and not r.done]


def stop(run: Run) -> None:
    if run.task is not None and not run.done:
        run.task.cancel()


async def subscribe(run: Run, start: int = 0) -> AsyncIterator[dict]:
    """从第 start 个事件开始往后看，直到这次研究结束。订阅方中途离开不影响研究本身。"""
    index = max(0, start)
    while True:
        while index < len(run.events):
            yield run.events[index]
            index += 1
        if run.done:
            return
        run._changed.clear()
        if index < len(run.events) or run.done:   # 清标志和检查之间可能刚好来了新事件
            continue
        try:
            await asyncio.wait_for(run._changed.wait(), 15)
        except TimeoutError:
            yield {"type": "ping"}   # 长时间没有新事件时发个心跳，免得中间的代理把连接掐了
