"""跟着进程跑的后台活：每日盯盘与自动任务、手机渠道的消息轮询。"""

from __future__ import annotations

import asyncio

from wealthpilot.services import channels, watcher


async def run_all() -> None:
    await asyncio.gather(watcher.scheduler(), channels.run_bot(), return_exceptions=True)
