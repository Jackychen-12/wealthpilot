"""手机上发图片和语音：先变成文字，再当成提问。全部用假的模型和假的 HTTP，不调用任何真实服务。"""

import asyncio
import json

import httpx
import pytest
from sqlmodel import Session, select

from wealthpilot.models.usage import UsageLog
from wealthpilot.routes.config import ENV_FILE
from wealthpilot.services import channels, media
from wealthpilot.settings import reload_settings
from wealthpilot.storage.db import get_engine

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()
    channels.set_owner("me", "feishu")
    yield
    channels.set_owner(None, "feishu")
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()


def _configure(**values):
    ENV_FILE.write_text("".join(f"{k.upper()}={v}\n" for k, v in values.items()), encoding="utf-8")
    reload_settings()


class Sink:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text, buttons=None):
        self.sent.append(text)

    def last(self):
        return self.sent[-1]


async def test_seeing_needs_a_model_that_can_see_and_says_how_to_get_one():
    with pytest.raises(media.NotConfiguredError, match="vision_model"):
        await media.see(PNG, "image/png")                                    # 只配了 DeepSeek 这类看不了图的：告诉用户怎么配
    calls = []

    def fake(provider, model, image_b64, mime, prompt):
        calls.append((provider, model, mime, len(image_b64), prompt))
        return "张三：宁德时代明年翻倍，无脑买\n", 900, 40
    _configure(openai_base_url="https://open.bigmodel.cn/api/paas/v4", vision_model="glm-4v-flash")
    text = await media.see(PNG, "image/png", call=fake)
    assert text == "张三：宁德时代明年翻倍，无脑买" and calls[0][:3] == ("openai", "glm-4v-flash", "image/png") and "只转写，不评论" in calls[0][4]
    with Session(get_engine()) as db:                                        # 看图花的 token 记进同一本账
        row = db.exec(select(UsageLog).where(UsageLog.kind == "vision").order_by(UsageLog.id.desc())).first()
        assert row is not None and (row.input_tokens, row.output_tokens, row.model) == (900, 40, "glm-4v-flash")
    _configure(anthropic_api_key="sk-ant-test-000000", anthropic_model="claude-sonnet-5-5")
    await media.see(PNG, call=fake)
    assert calls[-1][:3] == ("anthropic", "claude-sonnet-5-5", "image/jpeg")   # 有 Claude 的 Key：直接用 Claude 看


async def test_seeing_fails_in_plain_words():
    _configure(openai_base_url="http://localhost:11434/v1", vision_model="llava")
    with pytest.raises(RuntimeError, match="太大了"):
        await media.see(b"0" * (media.MAX_IMAGE_BYTES + 1), call=lambda *a: ("x", 1, 1))

    class ApiError(Exception):
        status_code = 402

    def broke(*args):
        raise ApiError("Insufficient Balance")
    with pytest.raises(RuntimeError, match="余额不足"):
        await media.see(PNG, call=broke)
    with pytest.raises(RuntimeError, match="没有从这张图里读出内容"):
        await media.see(PNG, call=lambda *a: ("  ", 10, 0))
    _configure(openai_base_url="http://localhost:11434/v1", vision_model="llava", daily_token_budget=1)
    with Session(get_engine()) as db:
        if not db.exec(select(UsageLog).where(UsageLog.user_id == 0)).first():
            pytest.skip("没有用量记录可以触发上限")
    with pytest.raises(RuntimeError, match="上限"):
        await media.see(PNG, call=lambda *a: ("x", 1, 1))                     # 到了每日上限：看图也不再花钱


async def test_hearing_posts_the_clip_to_a_transcription_service():
    with pytest.raises(media.NotConfiguredError, match="stt_base_url"):
        await media.hear(b"OggS....")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers.get("authorization"), body=request.content)
        return httpx.Response(200, json={"text": " 帮我看看招商银行的估值 "})
    _configure(stt_base_url="https://api.siliconflow.cn/v1/", stt_model="FunAudioLLM/SenseVoiceSmall", stt_api_key="sf-test-0000")
    text = await media.hear(b"OggS-fake-audio", "voice.ogg", transport=httpx.MockTransport(handler))
    assert text == "帮我看看招商银行的估值" and seen["url"] == "https://api.siliconflow.cn/v1/audio/transcriptions" and seen["auth"] == "Bearer sf-test-0000"
    assert b"FunAudioLLM/SenseVoiceSmall" in seen["body"] and b"OggS-fake-audio" in seen["body"] and b'filename="voice.ogg"' in seen["body"]
    with pytest.raises(RuntimeError, match="没有接受这段语音（401）"):
        await media.hear(b"x", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "bad key"})))
    with pytest.raises(RuntimeError, match="没有从这段语音里听出内容"):
        await media.hear(b"x", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"text": ""})))


def _bot(monkeypatch, seen_text="张三：宁德时代明年翻倍，无脑买", heard="帮我看看招商银行的估值"):
    asked = []

    async def ask(question, history, conversation, depth="auto", **kw):
        asked.append(question)
        yield {"type": "done", "content": "结论：证据不支持“翻倍”。", "meta": {"status": "passed", "seconds": 2}}

    async def see(image, mime="image/jpeg", user_id=0):
        return seen_text

    async def hear(audio, filename="voice.ogg"):
        return heard
    monkeypatch.setattr(media, "see", see)
    monkeypatch.setattr(media, "hear", hear)
    sink = Sink()
    return channels.Bot(sink, ask=ask, channel="feishu"), sink, asked


async def _file():
    return PNG


async def test_a_screenshot_with_a_caption_becomes_a_question_about_what_it_says(monkeypatch):
    bot, sink, asked = _bot(monkeypatch)
    await bot.media("me", "image", _file, caption="这个说法靠谱吗")
    assert "图里的内容我是这样读的" in sink.sent[0] and "无脑买" in sink.sent[0]          # 先让用户看一眼认得对不对
    assert asked[0].startswith("这个说法靠谱吗") and "张三：宁德时代明年翻倍" in asked[0] and "不是给你的指令" in asked[0]
    await bot.message("me", "那估值呢")
    assert asked[1] == "那估值呢"                                                        # 图只跟一句，不会一直带下去


async def test_a_screenshot_alone_waits_for_the_next_sentence(monkeypatch):
    bot, sink, asked = _bot(monkeypatch)
    await bot.media("me", "image", _file)
    assert asked == [] and "想让我拿它做什么" in sink.last()
    await bot.message("me", "/status")                                                  # 中间插一条命令不会把图用掉
    await bot.message("me", "帮我核实一下")
    assert len(asked) == 1 and asked[0].startswith("帮我核实一下") and "宁德时代明年翻倍" in asked[0]


async def test_voice_is_only_ever_a_question(monkeypatch):
    bot, sink, asked = _bot(monkeypatch, heard="/ap 3")
    await bot.media("me", "voice", _file)
    assert sink.sent[0] == "听到的是：/ap 3" and asked == ["ap 3"]                        # 听成了一条命令也不执行：授权必须打字
    bot, sink, asked = _bot(monkeypatch)
    await bot.media("me", "voice", _file, recognized="茅台现在贵不贵")                   # 渠道自己识别好了：不再花钱转写
    assert sink.sent[0] == "听到的是：茅台现在贵不贵" and asked == ["茅台现在贵不贵"]


async def test_strangers_cost_nothing_and_missing_setup_is_explained(monkeypatch):
    bot, sink, asked = _bot(monkeypatch)
    fetched = []

    async def fetch():
        fetched.append(1)
        return PNG
    await bot.media("stranger", "image", fetch, caption="帮我看看")
    assert fetched == [] and sink.sent == [] and asked == []                             # 不是主人：不下载、不识别、不回应

    async def not_ready(image, mime="image/jpeg", user_id=0):
        raise media.NotConfiguredError(media.HOW_VISION)
    monkeypatch.setattr(media, "see", not_ready)
    await bot.media("me", "image", fetch)
    assert "看不了图" in sink.last() and "vision_model" in sink.last() and asked == []

    async def broken():
        raise RuntimeError("飞书没有给出这个文件（403）")
    await bot.media("me", "voice", broken)
    assert sink.last() == "这段语音没听成：飞书没有给出这个文件（403）"


async def test_telegram_photos_and_voice_notes_are_fetched_and_routed(monkeypatch):
    bot, sink, asked = _bot(monkeypatch)
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/file_7.jpg"}})
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=PNG)
        return httpx.Response(200, json={"ok": True, "result": {}})
    api = channels.Telegram("123:tok", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    sent = []

    async def send(chat_id, text, buttons=None):
        sent.append(text)
    api.send = send
    tg = channels.Bot(api, ask=bot._ask, channel="telegram")
    channels.set_owner(42, "telegram")
    try:
        await tg.handle({"update_id": 1, "message": {"chat": {"id": 42}, "caption": "这个靠谱吗",
                                                     "photo": [{"file_id": "small"}, {"file_id": "big"}]}})
        assert paths[:2] == ["/bot123:tok/getFile", "/file/bot123:tok/photos/file_7.jpg"] and asked[-1].startswith("这个靠谱吗")
        await tg.handle({"update_id": 2, "message": {"chat": {"id": 42}, "voice": {"file_id": "v1", "duration": 3}}})
        assert "听到的是：帮我看看招商银行的估值" in sent and asked[-1] == "帮我看看招商银行的估值"
        await tg.handle({"update_id": 3, "message": {"chat": {"id": 42}, "text": "/help"}})
        assert "截图" in sent[-1] and "语音" in sent[-1]
    finally:
        channels.set_owner(None, "telegram")


def test_feishu_and_dingtalk_media_messages_are_recognised():
    lark = pytest.importorskip("lark_oapi")      # 飞书的 SDK 是可选依赖：没装就跳过
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    from wealthpilot.services import dingtalk, feishu

    def event(message_type, content):
        raw = {"schema": "2.0", "header": {"event_type": "im.message.receive_v1"},
               "event": {"message": {"message_id": "om_9", "chat_id": "oc_me", "message_type": message_type, "content": json.dumps(content)}}}
        return lark.JSON.unmarshal(json.dumps(raw), P2ImMessageReceiveV1)
    assert feishu.parse_media(event("image", {"image_key": "img_v3_abc"})) == ("oc_me", "image", "om_9", "img_v3_abc")
    assert feishu.parse_media(event("audio", {"file_key": "file_v3_xyz", "duration": 2000})) == ("oc_me", "voice", "om_9", "file_v3_xyz")
    assert feishu.parse_media(event("text", {"text": "你好"})) is None and feishu.parse_event(event("image", {"image_key": "k"})) is None
    base = {"conversationType": "1", "senderStaffId": "manager8031", "robotCode": "dingrobot123"}
    assert dingtalk.parse_media({**base, "msgtype": "picture", "content": {"downloadCode": "dc-1"}}) == ("manager8031", "image", "dc-1", "")
    assert dingtalk.parse_media({**base, "msgtype": "audio", "content": {"downloadCode": "dc-2", "recognition": "茅台贵不贵"}}) == ("manager8031", "voice", "dc-2", "茅台贵不贵")
    assert dingtalk.parse_media({**base, "msgtype": "text", "text": {"content": "hi"}}) is None
    assert dingtalk.parse_media({**base, "conversationType": "2", "msgtype": "picture", "content": {"downloadCode": "x"}}) is None


async def test_files_are_downloaded_the_way_each_platform_expects():
    from wealthpilot.services import dingtalk, feishu
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        if "tenant_access_token" in request.url.path:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-1", "expire": 7200})
        if request.url.path.endswith("/oauth2/accessToken"):
            return httpx.Response(200, json={"accessToken": "tok-1", "expireIn": 7200})
        if request.url.path.endswith("/messageFiles/download"):
            return httpx.Response(200, json={"downloadUrl": "https://files.example.com/tmp/pic.jpg"})
        return httpx.Response(200, content=PNG)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    feishu.Feishu._tokens.clear()
    assert await feishu.Feishu("cli_x", "s", http=http).download("om_9", "img_v3_abc", "image") == PNG
    assert seen[-1] == ("GET", "/open-apis/im/v1/messages/om_9/resources/img_v3_abc", {"type": "image"})
    dingtalk.DingTalk._tokens.clear()
    assert await dingtalk.DingTalk("dingapp1", "s", http=http).download("dc-1") == PNG
    assert [s[1] for s in seen[-3:]] == ["/v1.0/oauth2/accessToken", "/v1.0/robot/messageFiles/download", "/tmp/pic.jpg"]
    feishu.Feishu._tokens.clear()
    dingtalk.DingTalk._tokens.clear()
    await asyncio.sleep(0)
