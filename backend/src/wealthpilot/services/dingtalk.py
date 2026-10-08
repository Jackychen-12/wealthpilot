"""钉钉：在钉钉里和机器人单聊 —— 提问、收简报、处理建议单。

和飞书一样走长连接（钉钉叫 Stream 模式）：本机主动连出去，不需要公网地址。
收消息用官方的 dingtalk-stream SDK；发消息直接调开放平台的接口（机器人给个人发消息），
所以简报、提醒这类不是"回复"的消息也发得出去。

只认单聊：群里谁都能 @ 机器人，而这个机器人背后是一个人的持仓和建议单。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import warnings

import httpx

from wealthpilot.services import cache, channels
from wealthpilot.settings import get_settings

CHUNK = 3500
log = logging.getLogger("wealthpilot.channel")


def robot_code(fallback: str = "") -> str:
    """发消息要带机器人的编码。企业内部应用的机器人，编码就是应用的 Client ID；收到过消息的话以消息里带的为准。"""
    seen = (cache.read("channel:dingtalk:robot", 3650 * cache.DAY) or {}).get("code")
    return seen or fallback or get_settings().dingtalk_client_id


class DingTalk:
    """只管发：换取 accessToken，用机器人给一个人发文字。"""

    _tokens: dict[str, tuple[str, float]] = {}   # client_id -> (token, 到期时间)，进程内共用

    def __init__(self, client_id: str, client_secret: str, base: str = "https://api.dingtalk.com", http: httpx.AsyncClient | None = None) -> None:
        self.client_id, self.client_secret = client_id, client_secret
        self._base = base.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=15.0)

    async def token(self) -> str:
        cached = self._tokens.get(self.client_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        resp = await self._http.post(f"{self._base}/v1.0/oauth2/accessToken", json={"appKey": self.client_id, "appSecret": self.client_secret})
        data = resp.json()
        if resp.status_code >= 400 or not data.get("accessToken"):
            raise RuntimeError(f"钉钉拒绝了应用凭证：{data.get('message') or data.get('code') or resp.status_code}")
        self._tokens[self.client_id] = (data["accessToken"], time.time() + int(data.get("expireIn") or 7200))
        return data["accessToken"]

    async def send(self, chat_id: str, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        """给一个人发文字（chat_id 是他的 staffId）。文字消息没有按钮，按钮写成可回复的命令；太长就分几条。"""
        token = await self.token()
        for chunk in channels.split_text(channels.with_hints(text, buttons), CHUNK) or ["（空）"]:
            resp = await self._http.post(f"{self._base}/v1.0/robot/oToMessages/batchSend", headers={"x-acs-dingtalk-access-token": token},
                                         json={"robotCode": robot_code(self.client_id), "userIds": [str(chat_id)], "msgKey": "sampleText",
                                               "msgParam": json.dumps({"content": chunk}, ensure_ascii=False)})
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400 or data.get("code"):
                raise RuntimeError(f"钉钉没有接受这条消息：{data.get('message') or data.get('code') or resp.status_code}")


def parse_event(data: dict) -> tuple[str, str] | None:
    """从"机器人收到消息"的回调里取出（发消息的人, 文字）。群聊、非文字消息返回 None。"""
    if not isinstance(data, dict) or str(data.get("conversationType")) != "1":
        return None
    sender = str(data.get("senderStaffId") or "").strip()
    if data.get("msgtype") != "text" or not sender:
        return None
    text = str((data.get("text") or {}).get("content") or "").strip()
    if not text:
        return None
    if data.get("robotCode"):
        cache.write("channel:dingtalk:robot", {"code": data["robotCode"]})
    return sender, text


def handler_for(bot, sdk):
    """把"收到消息"的回调接到机器人上。研究要几十秒：放到后台跑，先把这条回调应答掉，不然钉钉会重发。"""
    class Handler(sdk.ChatbotHandler):
        async def process(self, callback):
            parsed = parse_event(getattr(callback, "data", None) or {})
            if parsed:
                task = asyncio.create_task(bot.message(*parsed))
                _tasks.add(task)
                task.add_done_callback(_tasks.discard)
            return sdk.AckMessage.STATUS_OK, "OK"
    return Handler()


_error = ""
_connected_as = ""
_tasks: set[asyncio.Task] = set()


def listener_error() -> str:
    return _error


async def run(sleep: float = 15.0) -> None:
    """跟着进程跑：等用户填好钉钉应用的 Client ID 和 Client Secret，就把长连接接上。凭证改了要重启 WealthPilot 才换。"""
    global _error, _connected_as
    while True:
        settings = get_settings()
        if not _connected_as and settings.dingtalk_client_id and settings.dingtalk_client_secret:
            try:
                with warnings.catch_warnings():          # SDK 在新版 Python 上导入时会打一条语法警告，和用户无关
                    warnings.simplefilter("ignore")
                    import dingtalk_stream
            except ImportError:
                _error = "没有安装钉钉的 SDK：在仓库的 backend 目录运行 uv sync --extra dingtalk（或重新运行安装脚本）"
                await asyncio.sleep(max(sleep, 60))
                continue
            bot = channels.Bot(DingTalk(settings.dingtalk_client_id, settings.dingtalk_client_secret), channel="dingtalk")
            client = dingtalk_stream.DingTalkStreamClient(dingtalk_stream.Credential(settings.dingtalk_client_id, settings.dingtalk_client_secret))
            client.register_callback_handler(dingtalk_stream.ChatbotMessage.TOPIC, handler_for(bot, dingtalk_stream))
            _connected_as, _error = settings.dingtalk_client_id, ""
            try:
                await client.start()                     # 一直挂着收消息，断了 SDK 自己会重连
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — 凭证不对、网络不通：记下来给自检和设置页看，过一会儿再试
                _error = f"钉钉长连接断开：{e}"
                log.warning("%s", _error)
            _connected_as = ""
        await asyncio.sleep(sleep)
