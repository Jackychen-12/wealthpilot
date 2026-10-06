"""手机触达、首次引导、粘贴导入、快速回答与基于已有证据的追问。不联网、不调模型。"""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wealthpilot.main import app
from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.research import DataCache, WatchItem
from wealthpilot.models.review import TradeProposal
from wealthpilot.routes import onboarding
from wealthpilot.services import channels, summary
from wealthpilot.services.agents import orchestrator
from wealthpilot.services.agents.planner_agent import PlannerAgent
from wealthpilot.storage.db import get_engine

MAOTAI = {"code": "600519", "name": "贵州茅台", "asset_type": "stock"}


@pytest.fixture
def db():
    with TestClient(app):
        pass
    with Session(get_engine()) as session:
        for model in (DataCache, TradeProposal, ChatMessage, PortfolioHolding, WatchItem):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        yield session


class FakeTelegram:
    """记下机器人发出去的每一条消息。"""

    def __init__(self):
        self.sent: list[dict] = []

    def client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            self.sent.append({"method": request.url.path.rsplit("/", 1)[-1], **json.loads(request.content or b"{}")})
            return httpx.Response(200, json={"ok": True, "result": []})
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent if m["method"] == "sendMessage"]


def message(chat_id: int, text: str) -> dict:
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def press(chat_id: int, data: str) -> dict:
    return {"update_id": 2, "callback_query": {"id": "cb", "data": data, "message": {"chat": {"id": chat_id}}}}


async def test_only_the_paired_chat_is_served(db):
    tg = FakeTelegram()
    bot = channels.Bot(channels.Telegram("T", http=tg.client()))
    await bot.handle(message(111, "帮我看看持仓"))
    assert "还没有绑定" in tg.texts()[-1] and channels.owner() is None

    code = channels.new_pair_code()
    await bot.handle(message(111, "/pair 000000" if code != "000000" else "/pair 111111"))
    assert channels.owner() is None                                   # 码不对：不绑定
    await bot.handle(message(111, f"/pair {code}"))
    assert channels.owner() == 111 and "已绑定" in tg.texts()[-1]

    before = len(tg.sent)
    await bot.handle(message(999, "/proposals"))                       # 别人发来的：完全不回应
    assert len(tg.sent) == before
    await bot.handle(message(111, "/proposals"))
    assert "没有等你决定的建议" in tg.texts()[-1]


async def test_research_from_the_phone_gives_conclusion_first_then_offers_proposals(db):
    channels.set_owner(111)
    tg = FakeTelegram()
    proposal = {"id": 7, "action_label": "减仓", "name": "五粮液", "code": "000858", "shares": 100, "price_ref": 70.06,
                "reason": "白酒暴露过于集中", "invalidation": "三季报现金流转正"}
    answer = "## 结论\n盈利质量仍高，但增长失速 [E-abcdef123456]。\n## 建议\n**立场：中性。**\n" + "正文" * 300
    calls = []

    async def ask(question, history, conversation_id, depth="auto"):
        calls.append((question, depth, len(history)))
        yield {"type": "plan", "intent": "个股深度研究", "eta_seconds": 52}
        yield {"type": "checkpoints", "items": [], "proposals": [proposal]}
        yield {"type": "done", "content": answer, "meta": {"status": "passed", "seconds": 48.2, "summary": summary.card(answer)}}

    bot = channels.Bot(channels.Telegram("T", http=tg.client()), ask=ask)
    await bot.handle(message(111, "帮我分析一下五粮液"))
    texts = tg.texts()
    assert "预计约 52 秒" in texts[0]
    assert texts[1].startswith("【结论】盈利质量仍高，但增长失速。") and "立场：中性" in texts[1] and "已通过校验 · 48.2 秒" in texts[1]
    assert "[E-" not in texts[2] and "【建议】" in texts[2]                # 正文去掉了证据标记和 Markdown 符号
    offer = [m for m in tg.sent if m.get("reply_markup")][-1]
    assert "建议 #7：减仓 五粮液" in offer["text"]
    assert [b["callback_data"] for b in offer["reply_markup"]["inline_keyboard"][0]] == ["ap:7", "rj:7"]

    await bot.handle(message(111, "/quick 现在贵吗"))
    assert calls[1] == ("现在贵吗", "quick", 2)                         # 快速回答，带着上一轮的上下文


async def test_approving_from_the_phone_takes_two_taps_and_rejecting_is_recorded(db, monkeypatch):
    from wealthpilot.services import broker

    channels.set_owner(111)
    monkeypatch.setattr(broker, "enabled", lambda: True)
    filled = SimpleNamespace(status="filled", shares=100, price=70.06, reason="")
    orders = []

    async def place_order(db_, user_id, **kw):
        orders.append(kw)
        return filled

    async def sync(db_, user_id):
        return {"added": 0, "updated": 0, "removed": 0, "skipped": []}

    monkeypatch.setattr(broker, "place_order", place_order)
    monkeypatch.setattr(broker, "sync_holdings", sync)
    db.add(TradeProposal(user_id=0, code="000858", name="五粮液", action="reduce", shares=100))
    db.add(TradeProposal(user_id=0, code="600519", name="贵州茅台", action="reduce"))
    db.commit()
    first, second = [p.id for p in db.exec(select(TradeProposal).order_by(TradeProposal.id)).all()]

    tg = FakeTelegram()
    bot = channels.Bot(channels.Telegram("T", http=tg.client()))
    await bot.handle(press(111, f"ap:{first}"))
    assert "确认吗" in tg.texts()[-1] and orders == []                  # 点"授权"只是问清楚，还没有下单
    await bot.handle(press(111, f"ok:{first}"))
    assert "已执行：减仓 五粮液 100 股 @ 70.06" in tg.texts()[-1] and orders[0]["side"] == "sell"
    await bot.handle(press(111, f"ok:{first}"))
    assert "已经处理过了" in tg.texts()[-1] and len(orders) == 1         # 同一条不会执行两次

    await bot.handle(press(111, f"ap:{second}"))
    assert f"/approve {second} 数量" in tg.texts()[-1]                  # 没给数量的建议：让用户自己说
    await bot.handle(message(111, f"/reject {second} 仓位本来就小"))
    db.expire_all()
    assert db.get(TradeProposal, second).status == "rejected"


def test_long_text_is_split_and_markdown_is_flattened():
    parts = channels.split_text("\n".join(["一行" * 50] * 100), 1000)
    assert len(parts) > 1 and all(len(p) <= 1000 for p in parts)
    assert channels.plain("## 估值\n**PE 19.32** [E-abc123def456]\n| a | b |\n|---|---|\n| 1 | 2 |") == "【估值】\nPE 19.32\n| a | b |\n| 1 | 2 |"


def test_onboarding_tracks_real_progress_and_can_be_dismissed(db, monkeypatch):
    monkeypatch.setattr(onboarding, "model_ready", lambda: False)
    with TestClient(app) as client:
        first = client.get("/api/onboarding").json()
        assert [(s["key"], s["done"]) for s in first["steps"]] == [("model", False), ("data", False), ("research", False), ("reach", False)]
        assert first["complete"] is False and first["dismissed"] is False
        client.post("/api/sample")
        monkeypatch.setattr(onboarding, "model_ready", lambda: True)
        db.add(ChatMessage(user_id=0, conversation_id="c", role="assistant", content="答"))
        db.commit()
        second = client.get("/api/onboarding").json()
        assert second["complete"] is True                               # 连手机是可选的，不算进"完成"
        client.post("/api/onboarding/dismiss")
        assert client.get("/api/onboarding").json()["dismissed"] is True
        client.delete("/api/sample")


def test_pasted_holdings_are_previewed_then_saved_once(db, monkeypatch):
    known = {"贵州茅台": ("600519", "贵州茅台", "stock"), "600036": ("600036", "招商银行", "stock"), "110011": ("110011", "易方达优质精选混合", "fund")}

    async def search(query, limit=8):
        hit = known.get(query)
        return [{"code": hit[0], "name": hit[1], "asset_type": hit[2]}] if hit else []

    async def profile(code):
        return {"industry": "白酒Ⅱ"}

    monkeypatch.setattr(onboarding.securities, "search", search)
    monkeypatch.setattr(onboarding, "fetch_stock_profile", profile)
    with TestClient(app) as client:
        rows = client.post("/api/portfolio/parse", json={"text": "贵州茅台 100 1500\n600036,600,36.5\n110011 2500份 4.35\n不存在的票 100 10\n招商银行 600\n"}).json()["rows"]
        assert [(r["code"], r["shares"], r["cost"], r["ok"]) for r in rows[:3]] == [("600519", 100, 1500, True), ("600036", 600, 36.5, True), ("110011", 2500, 4.35, True)]
        assert "没找到" in rows[3]["problem"] and rows[4]["problem"] == "没看到成本价"
        assert client.get("/api/portfolio").json() == []                # 预览不落库
        good = [r for r in rows if r["ok"]]
        assert client.post("/api/portfolio/batch", json={"rows": good}).json() == {"added": 3, "skipped": []}
        again = client.post("/api/portfolio/batch", json={"rows": good[:1]}).json()
        assert again["added"] == 0 and "已经在持仓里" in again["skipped"][0]
        held = {h["fund_code"]: h for h in client.get("/api/portfolio").json()}
        assert held["600519"]["industry"] == "白酒Ⅱ" and held["110011"]["asset_type"] == "fund"


def test_quick_plan_sends_at_most_two_agents_and_deep_forces_the_full_template():
    silent = SimpleNamespace(create=lambda **kw: SimpleNamespace(text="不是 JSON"))
    quick = PlannerAgent(silent, "m").plan("帮我分析一下贵州茅台", securities=[MAOTAI], depth="quick")
    assert (quick.intent, quick.playbook, [t.agent for t in quick.tasks], quick.sections) == ("快速回答", "", ["fundamental", "valuation"], [])
    free = SimpleNamespace(create=lambda **kw: SimpleNamespace(text=json.dumps(
        {"intent": "free", "tasks": [{"id": "t1", "agent": "price", "goal": "查走势"}, {"id": "t2", "agent": "industry", "goal": "查行业"}]})))
    assert [t.agent for t in PlannerAgent(free, "m").plan("茅台最近怎么走", securities=[MAOTAI], depth="quick").tasks] == ["price"]
    assert PlannerAgent(free, "m").plan("茅台最近怎么走", securities=[MAOTAI], depth="deep").playbook == "stock_deep"
    assert PlannerAgent(free, "m").plan("茅台最近怎么走", securities=[MAOTAI]).playbook == ""


def test_conclusion_card_only_for_long_answers():
    long = "## 结论\n茅台 > 五粮液，差距在质量 [E-abc123def456]。\n## 建议\n**立场：贵州茅台——看多；五粮液——中性。**\n" + "x" * 600
    card = summary.card(long)
    assert card["conclusion"].startswith("茅台 > 五粮液，差距在质量。") and card["stance"] == "看多"
    assert summary.card("现价 1258.62 元。") is None
    assert summary.conclusion("# 标题\n\n| a | b |\n第一段正文。\n第二段。") == "第一段正文。 第二段。"


async def test_follow_up_reuses_stored_evidence_without_new_tool_calls(db, monkeypatch):
    from wealthpilot.services.agents.critic_agent import CriticAgent
    from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent

    evidence = [{"id": "E-aaaaaaaaaaaa", "tool": "get_financial_indicators", "input": {"code": "600519"},
                 "output": json.dumps({"gross_margin_pct": 89.56, "debt_ratio_pct": 15.19}), "status": "ok"}]
    db.add(ChatMessage(user_id=0, conversation_id="c1", role="user", content="帮我分析一下贵州茅台"))
    db.add(ChatMessage(user_id=0, conversation_id="c1", role="assistant", content="## 结论\n毛利率 89.56% [E-aaaaaaaaaaaa]。",
                       metadata_json=json.dumps({"status": "passed", "playbook": "stock_deep", "evidence": evidence, "securities": [MAOTAI]})))
    db.commit()
    source = db.exec(select(ChatMessage).where(ChatMessage.role == "assistant")).one()

    settings = SimpleNamespace(active_model="fake", critic_enabled=True, light_model="")
    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator, "create_ai_client", lambda _: SimpleNamespace())
    seen = {}

    async def write(self, question, results, criteria, emit, **kw):
        seen["evidence"] = results[0].evidence
        seen["guide"] = kw["extra_instruction"]
        return "只讲风险：负债率 15.19% [E-aaaaaaaaaaaa]，明年目标 30%。"

    async def no_repair(self, draft, issues, numbers):
        return ""

    monkeypatch.setattr(SynthesizerAgent, "run", write)
    monkeypatch.setattr(SynthesizerAgent, "repair", no_repair)
    monkeypatch.setattr(CriticAgent, "_check_citations", lambda *a, **k: [], raising=False)

    events = [json.loads(line[6:]) async for line in orchestrator.chat_stream(
        "只讲风险", [], [], {}, {}, conversation_id="c1", db_session=db, user_id=0, rewrite_of=source.id)]
    kinds = [e["type"] for e in events]
    assert "tool_call" not in kinds and "task_start" not in kinds          # 没有重新取证
    assert seen["evidence"] == evidence and "只讲风险" in seen["guide"] and "毛利率 89.56%" in seen["guide"]
    done = events[-1]
    assert done["meta"]["playbook"] == "rewrite" and done["meta"]["rewrite_of"] == source.id
    # 模型加了一个证据里没有的 30：修不掉就删掉那半句，标为部分发布
    assert done["meta"]["status"] == "partial" and "30" not in done["content"] and "15.19%" in done["content"]
    saved = db.exec(select(ChatMessage).where(ChatMessage.role == "assistant").order_by(ChatMessage.id.desc())).first()
    assert json.loads(saved.metadata_json)["rewrite_of"] == source.id

    bad = [json.loads(line[6:]) async for line in orchestrator.chat_stream(
        "写短一点", [], [], {}, {}, conversation_id="c1", db_session=db, user_id=0, rewrite_of=999999)]
    assert bad[-1]["meta"]["status"] == "failed" and "找不到" in bad[-1]["content"]
