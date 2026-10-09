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
    assert [c["channel"] for c in data["channels"]] == ["telegram", "feishu", "dingtalk", "wecom"] and data["channels"][1]["label"] == "飞书"
    assert data["channels"][2]["label"] == "钉钉" and data["channels"][2]["error"] == ""
    assert "paired" in data                                                    # 老字段还在
    assert client.post("/api/channel/pair?channel=feishu").status_code == 409  # 还没配置：不给配对码
    assert client.post("/api/channel/pair?channel=line").status_code == 404
    assert client.post("/api/channel/test?channel=wecom").json()["ok"] is False
    assert client.get("/api/channel/wecom/callback").status_code == 404        # 没配置时回调地址不存在


# ── 手机里的命令和终端对齐：能停、能改写、能看状态，而且一次只查一个 ──────────────

def _paired(ask):
    sink = Sink()
    channels.set_owner("me", "feishu")
    return channels.Bot(sink, ask=ask, channel="feishu"), sink


async def test_stop_cancels_the_running_research_and_only_one_runs_at_a_time():
    started, cleaned = asyncio.Event(), []

    async def slow(question, history, conversation, depth="auto", **kw):
        try:
            yield {"type": "plan", "intent": "个股深度研究", "eta_seconds": 40}
            started.set()
            await asyncio.sleep(60)
            yield {"type": "done", "content": "不该走到这里", "meta": {"status": "passed"}}
        finally:
            cleaned.append(question)          # 真实的研究在这里把已经花掉的 token 记账
    bot, sink = _paired(slow)
    await bot.message("me", "/stop")
    assert "没有在查" in sink.last()
    first = asyncio.create_task(bot.message("me", "帮我分析一下宁德时代"))
    await started.wait()
    assert "/stop" in sink.last()                                             # 告诉用户不想等可以停
    await bot.message("me", "再分析一下茅台")                                  # 手一快连发了第二条
    assert "还在查" in sink.last() and "宁德时代" in sink.last() and cleaned == []      # 没有同时跑第二个
    await bot.message("me", "/status")
    assert "正在查：帮我分析一下宁德时代" in sink.last()
    await bot.message("me", "/stop")
    await asyncio.wait_for(first, 2)
    assert sink.last().startswith("已停止") and cleaned == ["帮我分析一下宁德时代"] and bot._running is None
    assert bot.history == []                                                  # 停掉的那次不算进对话
    await bot.message("me", "/status")
    assert "现在没有在查的问题" in sink.last() and "今天用量" in sink.last() and "模型：" in sink.last()


async def test_deep_and_rewrite_reach_the_research_with_the_right_arguments():
    seen = []

    async def ask(question, history, conversation, depth="auto", **kw):
        seen.append((question, depth, kw))
        yield {"type": "done", "content": "结论：估值在历史中位附近。", "meta": {"status": "passed", "seconds": 3, "message_id": 77,
                                                                      "fallback": {"model": "DeepSeek · deepseek-chat", "reason": "balance", "message": ""}}}
    bot, sink = _paired(ask)
    await bot.message("me", "/rewrite 更短一点")
    assert "还没有可以改写的回答" in sink.last() and seen == []
    await bot.message("me", "/deep 茅台估值贵不贵")
    assert seen[-1] == ("茅台估值贵不贵", "deep", {}) and bot.last_message_id == 77
    assert "主模型余额不足，这一轮是备用模型 DeepSeek · deepseek-chat 答的" in sink.last()      # 换过模型要说
    await bot.message("me", "/rewrite 更短一点")
    assert seen[-1] == ("更短一点", "auto", {"rewrite_of": 77}) and len(bot.history) == 2     # 改写不算新的一轮
    await bot.message("me", "/rewrite")
    assert "想怎么改" in sink.last()
    await bot.message("me", "/new")
    assert bot.last_message_id is None and bot.history == []
    for command in ("/deep", "/rewrite", "/stop", "/status", "/usage", "/holdings", "/watch", "/tasks"):
        assert command in channels.HELP_ALL                                  # 全表里都有
    assert len(channels.HELP.splitlines()) <= 10 and "帮助 全部" in channels.HELP   # 默认的帮助一屏看完
    for section in ("今日", "市场", "持仓", "回顾"):
        assert section in channels.HELP
    await bot.message("me", "帮助 全部")
    assert "/rewrite" in sink.last()
    await bot.message("me", "大盘")                                          # 手机上“大盘”“市场”给当天的复盘
    assert "/rewrite" not in sink.last()


async def test_read_only_commands_answer_from_local_data(monkeypatch):
    from datetime import date

    from sqlmodel import select

    from wealthpilot.models.portfolio import PortfolioHolding
    from wealthpilot.services import assets, automations

    async def quotes(codes):
        return {"600519": {"price": 1650.0, "change_pct": 1.2}}
    monkeypatch.setattr(assets, "fetch_sina_quotes", quotes)
    bot, sink = _paired(None)
    with Session(get_engine()) as db:
        for row in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == 0)).all():
            db.delete(row)
        db.add(PortfolioHolding(user_id=0, fund_code="600519", fund_name="贵州茅台", shares=100, cost_price=1500, asset_type="stock", buy_date=date(2026, 1, 5)))
        db.commit()
        task_id = automations.save(db, 0, {"kind": "task", "schedule": "工作日 08:30", "prompt": "诊断一下我的持仓"}).id
    try:
        await bot.message("me", "/holdings")
        assert "贵州茅台 600519  100 股  现价 1650  +10.0%" in sink.last() and "浮动盈亏 +1.50 万（+10.0%）" in sink.last()
        await bot.message("me", "/tasks")
        assert "工作日 08:30：诊断一下我的持仓" in sink.last() and "下次" in sink.last()
        await bot.message("me", "/usage")
        assert sink.last().startswith("今天：") and "近 30 天" in sink.last()
        await bot.message("me", "/watch")
        assert sink.last()                                                    # 有没有自选都要有句话
    finally:
        with Session(get_engine()) as db:
            automations.delete(db, 0, task_id)
            for row in db.exec(select(PortfolioHolding).where(PortfolioHolding.fund_code == "600519", PortfolioHolding.user_id == 0)).all():
                db.delete(row)
            db.commit()


# ── 钉钉：长连接收、接口发，只认单聊 ─────────────────────────────────────────

DING_EVENT = {"conversationId": "cidAbc==", "chatbotCorpId": "dingcorp", "chatbotUserId": "$:LWCP_v1:$bot", "msgId": "msgAbc==", "senderNick": "张三",
              "isAdmin": True, "senderStaffId": "manager8031", "sessionWebhookExpiredTime": 1791449999000, "createAt": 1791446000000,
              "senderCorpId": "dingcorp", "conversationType": "1", "senderId": "$:LWCP_v1:$abc",
              "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=x", "text": {"content": " 帮我分析一下宁德时代 "},
              "robotCode": "dingrobot123", "msgtype": "text"}


def _ding_clean():
    with Session(get_engine()) as db:
        row = db.get(DataCache, "channel:dingtalk:robot")
        if row:
            db.delete(row)
            db.commit()


def test_dingtalk_events_are_read_the_way_the_official_sdk_reads_them():
    import warnings
    with warnings.catch_warnings():        # 钉钉的 SDK 是可选依赖：没装就跳过，装了才对字段名
        warnings.simplefilter("ignore")
        dingtalk_stream = pytest.importorskip("dingtalk_stream")
    from wealthpilot.services import dingtalk
    _ding_clean()
    official = dingtalk_stream.ChatbotMessage.from_dict(DING_EVENT)                 # 用 SDK 自己的解析对一遍字段名
    assert dingtalk.parse_event(DING_EVENT) == (official.sender_staff_id, official.text.content.strip()) == ("manager8031", "帮我分析一下宁德时代")
    assert dingtalk.robot_code() == official.robot_code == "dingrobot123"           # 发消息要用的机器人编码，从收到的消息里记下来
    assert dingtalk.parse_event({**DING_EVENT, "conversationType": "2"}) is None    # 群聊：不理
    assert dingtalk.parse_event({**DING_EVENT, "msgtype": "picture", "content": {"downloadCode": "x"}}) is None
    assert dingtalk.parse_event({**DING_EVENT, "senderStaffId": ""}) is None and dingtalk.parse_event({**DING_EVENT, "text": {"content": "  "}}) is None
    assert dingtalk_stream.ChatbotMessage.TOPIC == "/v1.0/im/bot/messages/get"
    _ding_clean()


async def test_dingtalk_sends_through_the_robot_api_and_reports_refusals():
    from wealthpilot.services import dingtalk
    _ding_clean()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers.get("x-acs-dingtalk-access-token"), json.loads(request.content)))
        if request.url.path.endswith("/oauth2/accessToken"):
            return httpx.Response(200, json={"accessToken": "tok-1", "expireIn": 7200})
        return httpx.Response(200, json={"processQueryKey": "k"})
    dingtalk.DingTalk._tokens.clear()
    api = dingtalk.DingTalk("dingapp1", "secret", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await api.send("manager8031", "建议单 #3", [[("授权", "ap:3"), ("不采纳", "rj:3")]])
    await api.send("manager8031", "第二条")
    assert [s[0] for s in seen] == ["/v1.0/oauth2/accessToken", "/v1.0/robot/oToMessages/batchSend", "/v1.0/robot/oToMessages/batchSend"]     # 令牌只换一次
    assert seen[0][2] == {"appKey": "dingapp1", "appSecret": "secret"} and seen[1][1] == "tok-1"
    body = seen[1][2]
    assert body["robotCode"] == "dingapp1" and body["userIds"] == ["manager8031"] and body["msgKey"] == "sampleText"       # 没收到过消息时，编码用应用的 Client ID
    assert "回复 /ap 3 授权" in json.loads(body["msgParam"])["content"]                                                      # 文字消息没有按钮：写成可回复的命令
    dingtalk.DingTalk._tokens.clear()
    refused = dingtalk.DingTalk("dingapp1", "wrong", http=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"code": "invalidClientIdOrSecret", "message": "无效的clientId或clientSecret"}))))
    with pytest.raises(RuntimeError, match="钉钉拒绝了应用凭证：无效的clientId"):
        await refused.send("manager8031", "x")
    dingtalk.DingTalk._tokens.clear()


async def test_a_dingtalk_message_reaches_the_same_bot_and_is_acknowledged_at_once():
    import warnings
    with warnings.catch_warnings():        # 钉钉的 SDK 是可选依赖：没装就跳过，装了才对字段名
        warnings.simplefilter("ignore")
        dingtalk_stream = pytest.importorskip("dingtalk_stream")
    from wealthpilot.services import dingtalk
    _ding_clean()
    sink = Sink()
    bot = channels.Bot(sink, channel="dingtalk")
    handler = dingtalk.handler_for(bot, dingtalk_stream)
    code = channels.new_pair_code("dingtalk")
    callback = dingtalk_stream.CallbackMessage()
    callback.data = {**DING_EVENT, "text": {"content": f"/pair {code}"}}
    assert await handler.process(callback) == (dingtalk_stream.AckMessage.STATUS_OK, "OK")        # 立刻应答，不等研究跑完
    await asyncio.gather(*dingtalk._tasks)
    assert channels.owner("dingtalk") == "manager8031" and "已绑定" in sink.last() and bot.conversation.startswith("dd-")
    callback.data = {**DING_EVENT, "conversationType": "2", "text": {"content": "/status"}}       # 有人在群里 @ 它
    count = len(sink.sent)
    await handler.process(callback)
    await asyncio.gather(*dingtalk._tasks)
    assert len(sink.sent) == count
    assert channels.status("dingtalk") == {"channel": "dingtalk", "label": "钉钉", "configured": False, "paired": True}
    _ding_clean()


def test_a_dingtalk_connection_problem_is_surfaced_instead_of_retrying_in_silence():
    import logging

    from wealthpilot.services import dingtalk
    sdk_log = dingtalk._sdk_logger()
    sdk_log.error("open connection failed, error=401 Client Error: Unauthorized")
    assert "应用凭证不对" in dingtalk.listener_error() and "401" in dingtalk.listener_error()
    data = TestClient(app).get("/api/channel").json()
    assert "应用凭证不对" in next(c for c in data["channels"] if c["channel"] == "dingtalk")["error"]      # 设置页看得到
    sdk_log.info("endpoint is %s", {"endpoint": "wss://x", "ticket": "t"})                                   # 之后连上了：错误消掉
    assert dingtalk.listener_error() == "" and sdk_log.propagate is False and not any(isinstance(h, logging.StreamHandler) for h in sdk_log.handlers)
