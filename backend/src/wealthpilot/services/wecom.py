"""企业微信：在企业微信里和它对话。

企业微信的自建应用只支持"回调"收消息：成员给应用发消息，企业微信把它加密后 POST 到你填的地址。
所以这个渠道**需要一个公网能访问到的地址**（部署在服务器上，或自己做内网穿透）；只在自己电脑上跑、
没有公网地址的话用不了，这种情况用飞书或 Telegram。

这里实现的是官方文档里的加解密方案：签名 = sha1(把 token、时间戳、随机串、密文排序后拼起来)；
密文是 AES-256-CBC，密钥由 EncodingAESKey 解出，明文 = 16 字节随机数 + 4 字节消息长度 + 消息 + 企业 ID。

如实说明：加解密有自己加密再解密的往返测试，收发流程用模拟接口测过，没有连真实的企业微信跑过。
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import time

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from wealthpilot.services import channels

CHUNK = 600   # 企业微信单条文字上限 2048 字节，中文一个字 3 字节


def _key(aes_key: str) -> bytes:
    return base64.b64decode(aes_key + "=")


def sign(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce, encrypted])).encode()).hexdigest()


def decrypt(aes_key: str, encrypted: str) -> tuple[str, str]:
    """解出（消息, 接收方 ID）。格式不对会抛 ValueError。"""
    key = _key(aes_key)
    decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    plain = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    pad = plain[-1]
    if not 1 <= pad <= 32:
        raise ValueError("解密失败：填充不对")
    body = plain[16:-pad]
    length = int.from_bytes(body[:4], "big")
    if length > len(body) - 4:
        raise ValueError("解密失败：长度不对")
    return body[4:4 + length].decode("utf-8"), body[4 + length:].decode("utf-8")


def encrypt(aes_key: str, message: str, receive_id: str) -> str:
    key = _key(aes_key)
    raw = message.encode("utf-8")
    body = os.urandom(16) + len(raw).to_bytes(4, "big") + raw + receive_id.encode("utf-8")
    pad = 32 - len(body) % 32
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(encryptor.update(body + bytes([pad]) * pad) + encryptor.finalize()).decode()


def _field(xml: str, name: str) -> str:
    """从企业微信的 XML 里取一个字段。只取我们要的那几个，不上完整的 XML 解析器。"""
    match = re.search(rf"<{name}>(?:<!\[CDATA\[(.*?)\]\]>|([^<]*))</{name}>", xml, re.DOTALL)
    return (match.group(1) if match.group(1) is not None else match.group(2)).strip() if match else ""


def open_envelope(token: str, aes_key: str, corp_id: str, signature: str, timestamp: str, nonce: str, encrypted: str) -> str:
    """验签、解密、核对企业 ID。任何一步不对都抛 ValueError —— 回调地址是公开的，谁都能往上发东西。"""
    if not encrypted or sign(token, timestamp, nonce, encrypted) != signature:
        raise ValueError("签名不对")
    message, receiver = decrypt(aes_key, encrypted)
    if receiver != corp_id:
        raise ValueError("不是发给这个企业的")
    return message


def parse_message(xml: str) -> tuple[str, str, str] | None:
    """成员发来的文字消息 →（成员账号, 文字, 消息 ID）。其他类型返回 None。"""
    if _field(xml, "MsgType") != "text":
        return None
    user, text = _field(xml, "FromUserName"), _field(xml, "Content")
    return (user, text, _field(xml, "MsgId")) if user and text else None


def unsupported_from(xml: str) -> str:
    """成员发来的是图片或语音时，返回他的账号（好回一句"这里只收文字"）；否则空串。"""
    return _field(xml, "FromUserName") if _field(xml, "MsgType") in ("image", "voice", "video", "file") else ""


class WeCom:
    """只管发：换取 access_token，给一个成员发应用消息。"""

    _tokens: dict[str, tuple[str, float]] = {}

    def __init__(self, corp_id: str, agent_id: str, secret: str, base: str = "https://qyapi.weixin.qq.com", http: httpx.AsyncClient | None = None) -> None:
        self.corp_id, self.agent_id, self.secret = corp_id, agent_id, secret
        self._base = base.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=15.0)

    async def token(self) -> str:
        key = f"{self.corp_id}:{self.agent_id}"
        cached = self._tokens.get(key)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        data = (await self._http.get(f"{self._base}/cgi-bin/gettoken", params={"corpid": self.corp_id, "corpsecret": self.secret})).json()
        if data.get("errcode"):
            raise RuntimeError(f"企业微信拒绝了应用凭证：{data.get('errmsg') or data.get('errcode')}")
        self._tokens[key] = (data["access_token"], time.time() + int(data.get("expires_in") or 7200))
        return data["access_token"]

    async def send(self, user: str, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        token = await self.token()
        for chunk in channels.split_text(channels.with_hints(text, buttons), CHUNK) or ["（空）"]:
            data = (await self._http.post(f"{self._base}/cgi-bin/message/send", params={"access_token": token},
                                          json={"touser": user, "msgtype": "text", "agentid": int(self.agent_id) if str(self.agent_id).isdigit() else self.agent_id,
                                                "text": {"content": chunk}})).json()
            if data.get("errcode"):
                raise RuntimeError(f"企业微信没有接受这条消息：{data.get('errmsg') or data.get('errcode')}")


_bot: channels.Bot | None = None
_seen: list[str] = []


def bot() -> channels.Bot | None:
    """处理企业微信消息的机器人（保持同一个，这样会话上下文不丢）。没配置返回 None。"""
    global _bot
    api = channels._api_for("wecom")
    if api is None:
        _bot = None
        return None
    if _bot is None:
        _bot = channels.Bot(api, channel="wecom")
    else:
        _bot.api = api   # 设置里改了凭证，下一条消息就用新的
    return _bot


def fresh(message_id: str) -> bool:
    """企业微信 5 秒内没收到应答会重发同一条：见过的不再处理。"""
    global _seen
    if message_id and message_id in _seen:
        return False
    _seen = [*_seen[-200:], message_id]
    return True
