"""跟着进程跑的后台活：每日盯盘与自动任务、手机渠道的消息轮询。"""

from __future__ import annotations

import asyncio

from wealthpilot.services import channels, dingtalk, feishu, upgrade, watcher
from wealthpilot.settings import get_settings


async def check_updates() -> None:
    """启动后看一眼有没有新版本，之后半天一次。结果只进缓存，由界面决定怎么提示。"""
    await asyncio.sleep(20)   # 别和启动抢资源
    while True:
        if get_settings().update_check:
            await asyncio.to_thread(upgrade.check)
        await asyncio.sleep(12 * 3600)


async def run_all() -> None:
    await asyncio.gather(watcher.scheduler(), channels.run_bot(), feishu.run(), dingtalk.run(), check_updates(), return_exceptions=True)
