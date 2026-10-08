"""飞书、企业微信：和 Telegram 共用同一个机器人逻辑，区别只在收发。全部用模拟接口，不连真实服务。"""

import asyncio
import base64
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from wealthpilot.main import app
from wealthpilot.models.research import DataCache
from wealthpilot.routes.config import ENV_FILE
from wealthpilot.services import channels, feishu, wecom
from wealthpilot.settings import reload_settings
from wealthpilot.storage.db import get_engine


@pytest.fixture(autouse=True)
def _clean():
    def wipe():
        with Session(get_engine()) as db:
            for key in [f"channel:{c}:{k}" for c in channels.CHANNELS for k in ("owner", "pair")]:
                row = db.get(DataCache, key)
                if row:
                    db.delete(row)
            db.commit()
    wipe()
    yield
    wipe()


class Sink:
    """一个只会"发"的假渠道：记下发出去的话。"""

    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text, buttons=None):
        self.sent.append((chat_id, channels.with_hints(text, buttons)))

    def last(self):
        return self.sent[-1][1]


async def test_pairing_and_ownership_are_per_channel():
    sink = Sink()
    bot = channels.Bot(sink, channel="feishu")
    await bot.message("oc_stranger", "你好")
    assert "还没有绑定" in sink.last() and channels.owner("feishu") is None
    code = channels.new_pair_code("feishu")
    assert not channels._pair_matches(code, "telegram")                       # 飞书的码不能拿去绑 Telegram
    await bot.message("oc_me", f"/pair {code}")
    assert channels.owner("feishu") == "oc_me" and channels.owner("telegram") is None and "已绑定" in sink.last()
    count = len(sink.sent)
    await bot.message("oc_stranger", "/proposals")
    assert len(sink.sent) == count                                            # 不是主人：不回应
    assert bot.conversation.startswith("fs-")


async def test_buttons_become_commands_on_channels_without_buttons(monkeypatch):
    text = channels.with_hints("建议 #3：加仓 贵州茅台", [[("授权", "ap:3"), ("不采纳", "rj:3")]])
    assert "回复 /ap 3 授权" in text and "/rj 3 不采纳" in text
    sink = Sink()
    bot = channels.Bot(sink, channel="wecom")
    channels.set_owner("zhangsan", "wecom")
    pressed = []

    async def button(chat_id, data):
        pressed.append(data)
    monkeypatch.setattr(bot, "_button", button)
    for line in ("/ap 3", "/ok #3", "/no 3", "/rj 3"):
        await bot.message("zhangsan", line)
    assert pressed == ["ap:3", "ok:3", "no:3", "rj:3"]
    await bot.message("zhangsan", "/ok abc")                                  # 编号不对：当成不认识的命令
    assert "没有这个命令" in sink.last()


async def test_a_question_in_feishu_runs_research_and_replies_with_the_conclusion():
    async def ask(message, history, conversation_id, *, depth="auto"):
        yield {"type": "plan", "intent": "个股深度研究", "eta_seconds": 40}
        yield {"type": "done", "content": "## 结论\n稳。" + "正文。" * 300,
               "meta": {"status": "passed", "seconds": 38, "summary": {"conclusion": "基本面稳。", "stance": "中性", "truncated": False}}}
    sink = Sink()
    bot = channels.Bot(sink, ask=ask, channel="feishu")
    channels.set_owner("oc_me", "feishu")
    await bot.message("oc_me", "帮我分析一下贵州茅台")
    texts = [t for _, t in sink.sent]
    assert "预计约 40 秒" in texts[0] and "【结论】基本面稳。" in texts[1] and "立场：中性" in texts[1]


# ── 飞书 ────────────────────────────────────────────────

def _feishu_api(log):
    def handler(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            log.append(("token", json.loads(request.content)))
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        log.append(("message", dict(request.url.params), request.headers.get("authorization"), json.loads(request.content)))
        return httpx.Response(200, json={"code": 0})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_feishu_sends_text_with_a_cached_token():
    feishu.Feishu._tokens.clear()
    log = []
    api = feishu.Feishu("cli_x", "secret", http=_feishu_api(log))
    await api.send("oc_me", "第一条")
    await api.send("oc_me", "第二条", [[("确认", "ok:7")]])
    assert [entry[0] for entry in log] == ["token", "message", "message"]      # 第二次不再换 token
    assert log[0][1] == {"app_id": "cli_x", "app_secret": "secret"}
    _, params, auth, body = log[1]
    assert params == {"receive_id_type": "chat_id"} and auth == "Bearer t-abc"
    assert body["receive_id"] == "oc_me" and body["msg_type"] == "text" and json.loads(body["content"]) == {"text": "第一条"}
    assert "回复 /ok 7 确认" in json.loads(log[2][3]["content"])["text"]


async def test_feishu_reports_a_rejected_credential():
    feishu.Feishu._tokens.clear()
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"code": 10003, "msg": "invalid app_secret"})))
    with pytest.raises(RuntimeError, match="invalid app_secret"):
        await feishu.Feishu("cli_x", "bad", http=http).send("oc_me", "hi")


def _feishu_event(text, message_id="om_1", message_type="text", chat_id="oc_me"):
    """用飞书 SDK 自己的事件对象来造一条"收到消息"，这样字段名对不对由 SDK 说了算。"""
    lark = pytest.importorskip("lark_oapi")
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
    raw = {"schema": "2.0", "header": {"event_type": "im.message.receive_v1"},
           "event": {"sender": {"sender_id": {"open_id": "ou_1"}},
                     "message": {"message_id": message_id, "chat_id": chat_id, "chat_type": "p2p", "message_type": message_type,
                                 "content": json.dumps({"text": text}, ensure_ascii=False)}}}
    return lark.JSON.unmarshal(json.dumps(raw), P2ImMessageReceiveV1)


def test_feishu_events_are_read_with_the_sdks_own_model():
    assert feishu.parse_event(_feishu_event("@_user_1 茅台贵不贵")) == ("oc_me", "茅台贵不贵", "om_1")
    assert feishu.parse_event(_feishu_event("x", message_type="image")) is None
    assert feishu.parse_event(_feishu_event("   ")) is None


async def test_feishu_listener_hands_messages_to_the_bot_once():
    got = []

    class Bot:
        async def message(self, chat_id, text):
            got.append((chat_id, text))
    listener = feishu.Listener("cli_x", "secret", "https://open.feishu.cn", Bot(), asyncio.get_running_loop())
    event = _feishu_event("帮我分析一下茅台", message_id="om_9")
    await asyncio.to_thread(listener.on_message, event)                        # 像 SDK 那样从别的线程调进来
    await asyncio.to_thread(listener.on_message, event)                        # 飞书重发同一条
    await asyncio.sleep(0.05)
    assert got == [("oc_me", "帮我分析一下茅台")]


# ── 企业微信 ────────────────────────────────────────────

AES_KEY = base64.b64encode(os.urandom(32)).decode().rstrip("=")               # 43 位，和企业微信给的一样
TOKEN, CORP = "tok123", "ww1234567890"


def test_wecom_crypto_round_trip_and_rejects_tampering():
    assert len(AES_KEY) == 43
    sealed = wecom.encrypt(AES_KEY, "你好，企业微信", CORP)
    assert wecom.decrypt(AES_KEY, sealed) == ("你好，企业微信", CORP)
    signature = wecom.sign(TOKEN, "1700000000", "nonce", sealed)
    assert wecom.open_envelope(TOKEN, AES_KEY, CORP, signature, "1700000000", "nonce", sealed) == "你好，企业微信"
    with pytest.raises(ValueError, match="签名"):
        wecom.open_envelope(TOKEN, AES_KEY, CORP, "0" * 40, "1700000000", "nonce", sealed)
    with pytest.raises(ValueError, match="企业"):
        wecom.open_envelope(TOKEN, AES_KEY, "other-corp", signature, "1700000000", "nonce", sealed)
    # 官方文档里的签名示例：sha1(排序后拼接)
    assert wecom.sign("b", "c", "a", "d") == __import__("hashlib").sha1(b"abcd").hexdigest()


def test_wecom_message_fields_are_extracted_without_an_xml_parser():
    xml = ("<xml><ToUserName><![CDATA[ww1]]></ToUserName><FromUserName><![CDATA[zhangsan]]></FromUserName><CreateTime>1700000000</CreateTime>"
           "<MsgType><![CDATA[text]]></MsgType><Content><![CDATA[茅台 <贵> 不贵]]></Content><MsgId>123456</MsgId><AgentID>1000002</AgentID></xml>")
    assert wecom.parse_message(xml) == ("zhangsan", "茅台 <贵> 不贵", "123456")
    assert wecom.parse_message(xml.replace("[text]", "[image]")) is None
    assert wecom.fresh("m-1") and not wecom.fresh("m-1")                       # 重发的同一条不再处理


async def test_wecom_sends_an_app_message():
    wecom.WeCom._tokens.clear()
    log = []

    def handler(request):
        if request.url.path.endswith("/gettoken"):
            log.append(("token", dict(request.url.params)))
            return httpx.Response(200, json={"errcode": 0, "access_token": "at-1", "expires_in": 7200})
        log.append(("send", dict(request.url.params), json.loads(request.content)))
        return httpx.Response(200, json={"errcode": 0})
    api = wecom.WeCom(CORP, "1000002", "secret", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await api.send("zhangsan", "结论在这")
    assert log[0] == ("token", {"corpid": CORP, "corpsecret": "secret"})
    assert log[1][1] == {"access_token": "at-1"}
    assert log[1][2] == {"touser": "zhangsan", "msgtype": "text", "agentid": 1000002, "text": {"content": "结论在这"}}
    long_text = "\n".join(["一二三四五六七八九十" * 5] * 30)
    await api.send("zhangsan", long_text)
    assert all(len(entry[2]["text"]["content"].encode()) <= 2048 for entry in log if entry[0] == "send")    # 每条都在 2048 字节以内


def _configure_wecom():
    ENV_FILE.write_text(f"WECOM_CORP_ID={CORP}\nWECOM_AGENT_ID=1000002\nWECOM_SECRET=s\nWECOM_TOKEN={TOKEN}\nWECOM_AES_KEY={AES_KEY}\n")
    reload_settings()


def test_wecom_callback_verifies_then_answers_at_once(monkeypatch):
    original = ENV_FILE.read_text() if ENV_FILE.exists() else None
    try:
        _configure_wecom()
        got = []

        class Bot:
            async def message(self, user, text):
                got.append((user, text))
        monkeypatch.setattr(wecom, "bot", lambda: Bot())
        client = TestClient(app)
        # 1) 保存回调地址时的验证：把 echostr 解密后原样返回
        echo = wecom.encrypt(AES_KEY, "echo-123", CORP)
        r = client.get("/api/channel/wecom/callback", params={"msg_signature": wecom.sign(TOKEN, "1", "n", echo), "timestamp": "1", "nonce": "n", "echostr": echo})
        assert r.status_code == 200 and r.text == "echo-123"
        # 2) 成员发来消息
        inner = "<xml><FromUserName><![CDATA[zhangsan]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[茅台贵不贵]]></Content><MsgId>m-77</MsgId></xml>"
        sealed = wecom.encrypt(AES_KEY, inner, CORP)
        body = f"<xml><ToUserName><![CDATA[{CORP}]]></ToUserName><Encrypt><![CDATA[{sealed}]]></Encrypt><AgentID><![CDATA[1000002]]></AgentID></xml>"
        params = {"msg_signature": wecom.sign(TOKEN, "2", "n2", sealed), "timestamp": "2", "nonce": "n2"}
        with TestClient(app) as live:
            assert live.post("/api/channel/wecom/callback", params=params, content=body).text == ""
            live.post("/api/channel/wecom/callback", params=params, content=body)                 # 企业微信重发
        assert got == [("zhangsan", "茅台贵不贵")]
        # 3) 签名不对：拒绝，而且不说原因
        bad = client.post("/api/channel/wecom/callback", params={**params, "msg_signature": "0" * 40}, content=body)
        assert bad.status_code == 403 and bad.json()["detail"] == "验证失败"
    finally:
        if original is None:
            ENV_FILE.unlink(missing_ok=True)
        else:
            ENV_FILE.write_text(original)
        reload_settings()


def test_channel_routes_cover_all_three():
    client = TestClient(app)
    data = client.get("/api/channel").json()
    assert [c["channel"] for c in data["channels"]] == ["telegram", "feishu", "wecom"] and data["channels"][1]["label"] == "飞书"
    assert "paired" in data                                                    # 老字段还在
    assert client.post("/api/channel/pair?channel=feishu").status_code == 409  # 还没配置：不给配对码
    assert client.post("/api/channel/pair?channel=line").status_code == 404
    assert client.post("/api/channel/test?channel=wecom").json()["ok"] is False
    assert client.get("/api/channel/wecom/callback").status_code == 404        # 没配置时回调地址不存在
