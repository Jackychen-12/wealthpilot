"""省钱：预算上限、用量流水、压缩历史、沿用最近的研究。全部离线，不调用模型。"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.test_pipeline import FakeClient, _done, _run, _tool_use
from wealthpilot.main import app
from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.usage import UsageLog
from wealthpilot.services import budget
from wealthpilot.services.agents import orchestrator
from wealthpilot.services.ai_client import Usage
from wealthpilot.storage.db import get_engine

UID = 7701


def _usage(tokens_in=1000, cached=200, out=100) -> Usage:
    u = Usage()
    u.add(tokens_in, cached, out)
    return u


def _clear():
    with Session(get_engine()) as db:
        for row in db.exec(select(UsageLog).where(UsageLog.user_id == UID)).all():
            db.delete(row)
        db.commit()


def test_usage_is_recorded_and_summed(monkeypatch):
    _clear()
    budget.record(UID, _usage(100_000, 20_000, 10_000), "deepseek-chat", "stock_deep")
    budget.record(UID, _usage(10_000, 0, 2_000), "deepseek-chat", "rewrite")
    budget.record(UID, Usage(), "deepseek-chat", "stock_deep")          # 一个 token 没花：不记
    data = budget.summary(UID)
    assert data["today"] == {"runs": 2, "input_tokens": 110_000, "cached_tokens": 20_000, "output_tokens": 12_000, "tokens": 122_000, "cost": None}
    assert data["by_day"][-1]["tokens"] == 122_000 and len(data["by_day"]) == 14
    assert [k["kind"] for k in data["by_kind"]] == ["stock_deep", "rewrite"] and data["by_kind"][0]["avg_tokens"] == 110_000
    assert budget.typical_tokens(UID, "stock_deep") == 110_000 and budget.typical_tokens(UID, "screen") is None
    # 填了单价才折成钱
    monkeypatch.setattr(budget, "get_settings", lambda: SimpleNamespace(token_price_input=2.0, token_price_output=8.0, daily_token_budget=0))
    assert budget.summary(UID)["today"]["cost"] == round(110_000 / 1e6 * 2 + 12_000 / 1e6 * 8, 4)
    _clear()


def test_daily_budget_blocks_only_when_reached(monkeypatch):
    _clear()
    monkeypatch.setattr(budget, "get_settings", lambda: SimpleNamespace(daily_token_budget=100_000, token_price_input=0, token_price_output=0))
    assert budget.blocked(UID) == ""
    budget.record(UID, _usage(90_000, 0, 5_000), "m", "stock_deep")
    assert budget.blocked(UID) == ""
    budget.record(UID, _usage(5_000, 0, 500), "m", "rewrite")
    message = budget.blocked(UID)
    assert "上限" in message and "10.0 万" in message and "设置" in message
    assert budget.blocked(UID, datetime.now() + timedelta(days=1)) == ""          # 第二天自动恢复
    monkeypatch.setattr(budget, "get_settings", lambda: SimpleNamespace(daily_token_budget=0, token_price_input=0, token_price_output=0))
    assert budget.blocked(UID) == ""                                               # 0 = 不限
    _clear()


async def test_over_budget_run_does_not_touch_the_model(monkeypatch):
    monkeypatch.setattr(orchestrator.budget, "blocked", lambda uid: "今天的模型用量已经到你设的上限了")
    client = FakeClient(lambda kw: _tool_use())
    events = await _run(monkeypatch, client)
    assert _done(events)["meta"] == {"status": "failed", "reason": "budget"} and client.stream_calls == []


async def test_every_run_leaves_a_usage_record(monkeypatch):
    seen = []
    monkeypatch.setattr(orchestrator.budget, "record", lambda uid, usage, model, kind: seen.append((model, kind)))
    await _run(monkeypatch, FakeClient(lambda kw: _tool_use()))                    # 假模型一路失败也要记
    assert seen == [("fake", "free")]


def test_history_given_to_agents_keeps_questions_and_only_the_conclusion_of_answers():
    long_answer = "## 结论\\n宁德时代基本面扎实，估值处在低位。\\n\\n## 基本面\\n" + "营收同比增长很多。" * 600
    history = [{"role": "assistant", "content": "开头是回答，要去掉"},
               {"role": "user", "content": "帮我深度分析一下宁德时代"}, {"role": "assistant", "content": long_answer},
               {"role": "user", "content": "那它的估值呢"}]
    out = orchestrator.compact_history(history)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]              # 必须以用户的话开头
    assert out[0]["content"] == "帮我深度分析一下宁德时代" and out[2]["content"] == "那它的估值呢"
    assert "估值处在低位" in out[1]["content"] and len(out[1]["content"]) < 400 < len(long_answer)
    assert sum(len(m["content"]) for m in out) < len(long_answer) / 10             # 原来整篇照抄，现在不到十分之一


def _saved_research(question="帮我深度分析一下贵州茅台", minutes_ago=30, status="passed", code="600519"):
    evidence = [{"id": "E-aaaaaaaaaaaa", "tool": "get_valuation_history", "input": {"code": code}, "output": "PE 19.32", "status": "ok"}]
    meta = {"status": status, "playbook": "stock_deep", "intent": "个股深度研究", "securities": [{"code": code, "name": "贵州茅台", "asset_type": "stock"}],
            "evidence": evidence, "summary": {"conclusion": "稳。", "stance": "中性", "truncated": False},
            "debate": {"bull": {"points": [], "weakness": ""}, "bear": {"points": [], "weakness": ""}}}
    when = datetime.now() - timedelta(minutes=minutes_ago)
    with Session(get_engine()) as db:
        conversation = f"reuse-{code}-{minutes_ago}-{status}"
        db.add(ChatMessage(user_id=UID, conversation_id=conversation, role="user", content=question, created_at=when))
        db.commit()
        answer = ChatMessage(user_id=UID, conversation_id=conversation, role="assistant", content="## 结论\\nPE 19.32 [E-aaaaaaaaaaaa]",
                             metadata_json=json.dumps(meta, ensure_ascii=False), created_at=when)
        db.add(answer)
        db.commit()
        return answer.id


def _forget():
    with Session(get_engine()) as db:
        for row in db.exec(select(ChatMessage).where(ChatMessage.user_id == UID)).all():
            db.delete(row)
        db.commit()


def test_recent_research_is_found_only_when_fresh_passed_and_same_stock():
    _forget()
    mid = _saved_research(minutes_ago=30)
    _saved_research(minutes_ago=20, status="rejected")                             # 没发布的不算
    with Session(get_engine()) as db:
        row, meta, asked, minutes = orchestrator.recent_research(db, UID, "600519", 4)
        assert row.id == mid and asked == "帮我深度分析一下贵州茅台" and 29 <= minutes <= 31
        assert orchestrator.recent_research(db, UID, "300750", 4) is None          # 别的股票
        assert orchestrator.recent_research(db, UID, "600519", 0.25) is None       # 超过时限
        assert orchestrator.recent_research(db, UID, "600519", 0) is None          # 设成 0 就是关掉
        assert orchestrator.recent_research(db, UID + 1, "600519", 4) is None      # 别人的研究
    _forget()


async def test_the_same_question_is_replayed_for_free_and_a_new_angle_reuses_the_evidence(monkeypatch):
    _forget()
    mid = _saved_research(minutes_ago=90)
    events, client = [], SimpleNamespace(usage=Usage())

    async def emit(e):
        events.append(e)
    run = {"kind": "free"}
    with Session(get_engine()) as db:
        found = orchestrator.recent_research(db, UID, "600519", 4)
        await orchestrator._reuse(found, "帮我深度分析一下贵州茅台？", "c1", db, None, UID, emit, client, "m", SimpleNamespace(), 0.0, run)
    done = events[-1]
    assert done["type"] == "done" and done["content"].startswith("## 结论") and done["meta"]["usage"] == {}
    assert done["meta"]["message_id"] == mid and done["meta"]["reused"]["mode"] == "replay" and done["meta"]["reused"]["age"] == "1.5 小时前"
    assert [e["type"] for e in events][:3] == ["reused", "plan", "evidence"] and any(e["type"] == "debate" for e in events)
    assert run["kind"] == "reuse" and client.usage.as_dict()["input_tokens"] == 0  # 一个 token 没花

    called = {}

    async def fake_rewrite(instruction, rewrite_of, *a, note="", reused=None, **k):
        called.update(instruction=instruction, rewrite_of=rewrite_of, note=note, reused=reused)
    monkeypatch.setattr(orchestrator, "_run_rewrite", fake_rewrite)
    events.clear()
    with Session(get_engine()) as db:
        found = orchestrator.recent_research(db, UID, "600519", 4)
        await orchestrator._reuse(found, "茅台现在能不能买", "c1", db, None, UID, emit, client, "m", SimpleNamespace(), 0.0, run)
    assert called["rewrite_of"] == mid and called["instruction"] == "茅台现在能不能买"
    assert "没有重新取数" in called["note"] and called["reused"]["mode"] == "evidence" and events[0]["type"] == "reused"
    _forget()


def test_usage_route_and_settings_fields():
    client = TestClient(app)
    data = client.get("/api/settings/usage").json()
    assert {"today", "last_7_days", "last_30_days", "by_day", "by_kind", "daily_token_budget"} <= set(data)
    r = client.put("/api/settings", json={"daily_token_budget": 500000, "token_price_input": 2, "token_price_output": 8, "research_reuse_hours": 6})
    assert r.status_code == 200 and r.json()["values"]["daily_token_budget"] == 500000
    assert client.put("/api/settings", json={"daily_token_budget": -1}).status_code == 422
    client.put("/api/settings", json={"daily_token_budget": 0, "token_price_input": 0, "token_price_output": 0, "research_reuse_hours": 4})


# ── 推送：各家群机器人认的格式 ──────────────────────────

def test_each_chat_bot_gets_the_format_it_accepts():
    from wealthpilot.services.channels import webhook_payload
    assert webhook_payload("https://open.feishu.cn/open-apis/bot/v2/hook/x", "hi") == {"msg_type": "text", "content": {"text": "hi"}}
    assert webhook_payload("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x", "hi") == {"msgtype": "text", "text": {"content": "hi"}}
    assert webhook_payload("https://oapi.dingtalk.com/robot/send?access_token=x", "hi") == {"msgtype": "text", "text": {"content": "hi"}}
    assert webhook_payload("https://hooks.slack.com/services/x", "hi") == {"text": "hi"}
    assert webhook_payload("https://discord.com/api/webhooks/x", "hi") == {"content": "hi"}
    assert webhook_payload("https://my.server/hook", "hi")["source"] == "wealthpilot"
    assert len(webhook_payload("https://qyapi.weixin.qq.com/x", "字" * 5000)["text"]["content"]) == 1800


async def test_notify_reaches_the_webhook_and_reads_the_bots_error_code(monkeypatch):
    import httpx

    from wealthpilot.services import channels
    posted = []

    def handler(request):
        posted.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"code": 0} if str(request.url).endswith("/ok") else {"code": 19001, "msg": "param invalid"})
    real = httpx.AsyncClient
    monkeypatch.setattr(channels.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"}))
    monkeypatch.setattr(channels, "owner", lambda: None)                           # 没绑 Telegram
    monkeypatch.setattr(channels, "get_settings", lambda: SimpleNamespace(
        telegram_bot_token="", telegram_api_base="", alert_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/ok"))
    assert await channels.notify("**⏰ 定时任务**\\n结论在这") is True
    assert posted[0][1]["msg_type"] == "text" and "定时任务" in posted[0][1]["content"]["text"]
    # 飞书拒收时也回 200：要看返回体里的错误码，不能当成发出去了
    assert await channels.send_webhook("https://open.feishu.cn/open-apis/bot/v2/hook/bad", "x") is False
    monkeypatch.setattr(channels, "get_settings", lambda: SimpleNamespace(telegram_bot_token="", telegram_api_base="", alert_webhook_url=""))
    assert await channels.notify("没有任何渠道") is False


# ── 用自己的成绩校准 ────────────────────────────────────

def test_calibration_note_speaks_only_about_groups_with_enough_checks(monkeypatch):
    from wealthpilot.services import checkpoints

    def card(*groups):
        return {"by_group": [{"label": label, "held": held, "broken": broken, "hold_rate_pct": rate} for label, held, broken, rate in groups]}
    monkeypatch.setattr(checkpoints, "scorecard", lambda db, uid: card(("财务", 2, 6, 25.0), ("估值", 7, 1, 87.5), ("涨跌", 1, 1, 50.0)))
    note = checkpoints.calibration_note(None, 0)
    assert "财务类：已核对 8 条，成立 2 条（25%）" in note and "更保守" in note
    assert "估值类" in note and "大多成立" in note
    assert "涨跌" not in note                                                     # 只核对过两条：不拿它说事
    monkeypatch.setattr(checkpoints, "scorecard", lambda db, uid: card(("财务", 1, 1, 50.0)))
    assert checkpoints.calibration_note(None, 0) == ""
