"""飞书：在飞书里和它对话。

收消息用飞书官方 SDK 的"长连接"：由本机主动连到飞书，不需要公网地址，适合跑在自己电脑上。
发消息直接调开放平台的接口。需要在飞书开放平台建一个"企业自建应用"，开通机器人能力和收发消息的权限，
并把事件订阅方式选成"使用长连接接收事件"。

如实说明：这部分是照飞书开放平台的文档和 SDK 写的，用模拟的接口和 SDK 自己的事件对象测过，
没有用真实的飞书应用跑过。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time

import httpx

from wealthpilot.services import channels
from wealthpilot.settings import get_settings

CHUNK = 3500


class Feishu:
    """只管发：换取 tenant_access_token，往一个会话里发文字。"""

    _tokens: dict[str, tuple[str, float]] = {}   # app_id -> (token, 到期时间)，进程内共用

    def __init__(self, app_id: str, app_secret: str, base: str = "https://open.feishu.cn", http: httpx.AsyncClient | None = None) -> None:
        self.app_id, self.app_secret = app_id, app_secret
        self._base = base.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=15.0)

    async def token(self) -> str:
        cached = self._tokens.get(self.app_id)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        resp = await self._http.post(f"{self._base}/open-apis/auth/v3/tenant_access_token/internal",
                                     json={"app_id": self.app_id, "app_secret": self.app_secret})
        data = resp.json()
        if data.get("code"):
            raise RuntimeError(f"飞书拒绝了应用凭证：{data.get('msg') or data.get('code')}")
        self._tokens[self.app_id] = (data["tenant_access_token"], time.time() + int(data.get("expire") or 7200))
        return data["tenant_access_token"]

    async def send(self, chat_id: str, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        """往一个会话里发文字。飞书的文字消息没有按钮，按钮写成可回复的命令；太长就分几条。"""
        token = await self.token()
        for chunk in channels.split_text(channels.with_hints(text, buttons), CHUNK) or ["（空）"]:
            resp = await self._http.post(f"{self._base}/open-apis/im/v1/messages", params={"receive_id_type": "chat_id"},
                                         headers={"Authorization": f"Bearer {token}"},
                                         json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": chunk}, ensure_ascii=False)})
            data = resp.json()
            if data.get("code"):
                raise RuntimeError(f"飞书没有接受这条消息：{data.get('msg') or data.get('code')}")


async def _download(self: Feishu, message_id: str, key: str, kind: str) -> bytes:
    """取回用户发来的图片或语音。"""
    token = await self.token()
    resp = await self._http.get(f"{self._base}/open-apis/im/v1/messages/{message_id}/resources/{key}",
                                params={"type": "image" if kind == "image" else "file"}, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        raise RuntimeError(f"飞书没有给出这个文件（{resp.status_code}）。应用需要「获取与上传图片或文件资源」权限。")
    return resp.content


Feishu.download = _download   # type: ignore[attr-defined]


def parse_media(data) -> tuple[str, str, str, str] | None:
    """图片或语音消息 →（会话 ID, image / voice, 消息 ID, 文件的 key）。其他类型返回 None。"""
    message = getattr(getattr(data, "event", None), "message", None)
    kind = {"image": "image", "audio": "voice"}.get(getattr(message, "message_type", ""))
    if message is None or kind is None:
        return None
    try:
        content = json.loads(message.content or "{}")
    except ValueError:
        return None
    key = str(content.get("image_key") or content.get("file_key") or "")
    return (str(message.chat_id), kind, str(message.message_id), key) if message.chat_id and key else None


def parse_event(data) -> tuple[str, str, str] | None:
    """从 SDK 的"收到消息"事件里取出（会话 ID, 文字, 消息 ID）。不是文字消息返回 None。"""
    message = getattr(getattr(data, "event", None), "message", None)
    if message is None or getattr(message, "message_type", "") != "text":
        return None
    try:
        text = str(json.loads(message.content or "{}").get("text") or "")
    except ValueError:
        return None
    text = re.sub(r"@_user_\d+\s*", "", text).strip()   # 群里 @ 机器人时带的占位符
    return (str(message.chat_id), text, str(message.message_id)) if message.chat_id and text else None


class Listener:
    """把飞书的长连接跑在一个单独的线程里，收到消息就交回主事件循环里的机器人处理。"""

    def __init__(self, app_id: str, app_secret: str, base: str, bot: channels.Bot, loop: asyncio.AbstractEventLoop) -> None:
        self.app_id, self.app_secret, self.base, self.bot, self.loop = app_id, app_secret, base, bot, loop
        self.seen: list[str] = []
        self.error = ""

    def on_message(self, data) -> None:
        media = parse_media(data)
        if media is not None:
            chat_id, kind, message_id, key = media
            if message_id not in self.seen:
                self.seen = [*self.seen[-200:], message_id]
                api = self.bot.api
                asyncio.run_coroutine_threadsafe(
                    self.bot.media(chat_id, kind, lambda: api.download(message_id, key, kind), filename="voice.opus"), self.loop)
            return
        parsed = parse_event(data)
        if parsed is None:
            return
        chat_id, text, message_id = parsed
        if message_id in self.seen:      # 飞书没及时收到确认会重发同一条
            return
        self.seen = [*self.seen[-200:], message_id]
        asyncio.run_coroutine_threadsafe(self.bot.message(chat_id, text), self.loop)

    def _run(self) -> None:
        try:
            import lark_oapi as lark
            import lark_oapi.ws.client as ws_client

            # SDK 在导入时就把"当前事件循环"存成了模块变量，start() 会在它上面 run_until_complete；
            # 主线程的循环正在跑，不能借用，所以给这个线程单独建一个
            ws_client.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_client.loop)
            handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(self.on_message).build()
            lark.ws.Client(self.app_id, self.app_secret, event_handler=handler, domain=self.base, log_level=lark.LogLevel.WARNING).start()
        except ImportError:
            self.error = "没有安装飞书的 SDK：在仓库的 backend 目录运行 uv sync --extra feishu（或重新 make setup）"
        except Exception as e:  # noqa: BLE001 — 连不上、凭证不对：记下来给自检和设置页看
            self.error = f"飞书长连接断开：{e}"
            logging.getLogger("wealthpilot.channel").warning("%s", self.error)

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run, daemon=True, name="wp-feishu")
        thread.start()
        return thread


_listener: Listener | None = None


def listener_error() -> str:
    return _listener.error if _listener is not None else ""


async def run() -> None:
    """跟着进程跑：等用户在设置里填好飞书应用的凭证，就把长连接接上。凭证改了要重启 WealthPilot 才换。"""
    global _listener
    while True:
        settings = get_settings()
        if _listener is None and settings.feishu_app_id and settings.feishu_app_secret:
            api = Feishu(settings.feishu_app_id, settings.feishu_app_secret, settings.feishu_api_base)
            _listener = Listener(settings.feishu_app_id, settings.feishu_app_secret, settings.feishu_api_base,
                                 channels.Bot(api, channel="feishu"), asyncio.get_running_loop())
            _listener.start()
        await asyncio.sleep(15)
