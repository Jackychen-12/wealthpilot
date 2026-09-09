"""同步 SDK → 异步事件流的桥接。

Anthropic / OpenAI 的 Python SDK 在本项目里用的是同步客户端，而多 Agent 并行
要求整条链路是 async 的。直接在事件循环里迭代同步流会阻塞整个循环，导致
"并行" 退化成串行。

这里把同步流式调用搬到工作线程里，通过 queue.Queue 把 token 递回事件循环，
调用方用 `async for` 消费。这样既保留了现成的 Provider 抽象层（不必重写成
AsyncAnthropic / AsyncOpenAI），又让多个 Agent 能真正并发。
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any

_SENTINEL = object()


async def stream_sync_in_thread(
    make_stream: Callable[[], Any],
) -> AsyncIterator[tuple[str, Any]]:
    """在线程中执行同步流式调用，异步产出事件。

    Args:
        make_stream: 无参可调用对象，返回一个支持 `with` 的流上下文，
            该上下文需提供 `.text_stream` 迭代器与 `.get_final_result()`。

    Yields:
        ("delta", str)  — 增量文本
        ("final", CompletionResult) — 本轮最终结果
        ("error", Exception) — 线程内异常，调用方负责处理
    """
    loop = asyncio.get_running_loop()
    q: queue.Queue = queue.Queue(maxsize=256)

    def worker() -> None:
        try:
            with make_stream() as stream:
                for text in stream.text_stream:
                    q.put(("delta", text))
                q.put(("final", stream.get_final_result()))
        except Exception as exc:  # noqa: BLE001 — 交给调用方决定如何呈现
            q.put(("error", exc))
        finally:
            q.put(_SENTINEL)

    thread = threading.Thread(target=worker, daemon=True, name="wp-llm-stream")
    thread.start()

    try:
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is _SENTINEL:
                break
            yield item
    finally:
        # 消费方提前退出（客户端断连）时，让工作线程自然结束而不是卡在 put 上
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
