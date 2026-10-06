"""主动干活：定时任务的时间解析与补跑、每日上限、提醒的触发与停用。"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from wealthpilot.main import app
from wealthpilot.models.automation import Automation
from wealthpilot.services import automations, watcher
from wealthpilot.storage.db import get_engine

MON = datetime(2026, 10, 5, 12, 0)   # 周一


@pytest.mark.parametrize("text,expected", [
    ("每天 8:30", "每天 08:30"),
    ("每日08：05", "每天 08:05"),
    ("工作日 15:40", "工作日 15:40"),
    ("交易日下午3点半", "工作日 15:30"),
    ("每周一 09:00", "每周一 09:00"),
    ("每周一三五 9点", "每周一三五 09:00"),
    ("周五晚上8点", "每周五 20:00"),
    ("每周一、周三 9点15分", "每周一三 09:15"),
    ("8:30", "每天 08:30"),
])
def test_parse_schedule(text, expected):
    assert automations.parse_schedule(text)["text"] == expected


@pytest.mark.parametrize("text", ["", "明天", "每天 25:00", "每月一号 9:00", "有空的时候 9:00"])
def test_parse_schedule_rejects(text):
    assert automations.parse_schedule(text) is None


def _task(**kw) -> Automation:
    base = dict(user_id=0, kind="task", title="复盘", schedule="工作日 08:30", prompt="复盘一下我的持仓", created_at=MON - timedelta(days=3))
    return Automation(**{**base, **kw})


def test_due_runs_once_per_slot_and_catches_up():
    auto = _task()
    assert automations.due(auto, MON)                         # 周一 08:30 已过，还没跑
    auto.last_run_at = MON
    assert not automations.due(auto, MON + timedelta(hours=3))  # 同一个时点不再跑
    assert automations.due(auto, MON + timedelta(days=1))       # 周二 08:30 之后又到点
    # 合着盖错过了：36 小时内补跑，再久就等下一次
    weekly = _task(schedule="每周一 09:00", created_at=MON - timedelta(days=10))
    assert automations.due(weekly, datetime(2026, 10, 6, 10, 0))
    assert not automations.due(weekly, datetime(2026, 10, 8, 10, 0))
    # 刚建的任务不会因为“今天的时间已经过了”立刻跑
    assert not automations.due(_task(created_at=MON), MON + timedelta(minutes=5))


def _fake_ask(status="passed", answer="结论：稳。" * 80):
    async def ask(message, history, conversation_id, *, depth="auto", user_id=None):
        yield {"type": "delta", "content": answer}
        yield {"type": "done", "content": answer, "meta": {"status": status, "message_id": 7,
                                                            "summary": {"conclusion": "组合整体稳健。", "stance": "", "truncated": True}}}
    return ask


def test_run_task_records_result_and_respects_daily_cap(monkeypatch):
    sent = []

    async def notify(text, buttons=None):
        sent.append(text)
        return True
    monkeypatch.setattr(automations.channels, "notify", notify)
    monkeypatch.setattr(automations.get_settings(), "auto_daily_runs_max", 1, raising=False)
    with Session(get_engine()) as db:
        first = automations.save(db, 0, {"kind": "task", "prompt": "复盘一下我的持仓", "schedule": "工作日 08:30"})
        second = automations.save(db, 0, {"kind": "task", "prompt": "看看自选有没有变化", "schedule": "工作日 08:35"})
        out = asyncio.run(automations.run_task(db, first, ask=_fake_ask(), now=MON))
        assert out["last_status"] == "ok" and out["last_result"] == "组合整体稳健。" and out["last_message_id"] == 7
        assert "复盘一下我的持仓" in sent[0] and "组合整体稳健" in sent[0]
        # 第二条撞上每日上限：不跑，但记下原因
        out = asyncio.run(automations.run_task(db, second, ask=_fake_ask(), now=MON))
        assert out["last_status"] == "skipped" and "上限" in out["last_result"]
        # 手动点的不受限
        out = asyncio.run(automations.run_task(db, second, manual=True, ask=_fake_ask(), now=MON))
        assert out["last_status"] == "ok"
        # 没产出可发布的结论：如实记为失败
        out = asyncio.run(automations.run_task(db, second, manual=True, ask=_fake_ask(status="rejected"), now=MON))
        assert out["last_status"] == "failed" and "rejected" in out["last_result"]
        for a in automations.list_all(db, 0):
            automations.delete(db, 0, a.id)


def test_alert_fires_once_then_pauses(monkeypatch):
    sent = []

    async def notify(text, buttons=None):
        sent.append(text)
        return True

    price = {"value": 1380.0}

    async def quotes(codes):
        return {c: {"price": price["value"], "change_pct": -1.2} for c in codes}
    monkeypatch.setattr(automations.channels, "notify", notify)
    monkeypatch.setattr(automations, "fetch_sina_quotes", quotes)
    with Session(get_engine()) as db:
        auto = automations.save(db, 0, {"kind": "alert", "code": "600519", "name": "贵州茅台", "metric": "price", "op": "<=", "threshold": 1350})
        assert auto.title == "贵州茅台 最新价 ≤ 1350元"
        assert asyncio.run(automations.check_alerts(db, 0, MON)) == []          # 没到条件
        price["value"] = 1349.5
        fired = asyncio.run(automations.check_alerts(db, 0, MON))
        assert len(fired) == 1 and fired[0]["enabled"] is False and "1349.5" in fired[0]["last_result"]
        assert "贵州茅台" in sent[0] and "已停" in sent[0]
        assert asyncio.run(automations.check_alerts(db, 0, MON)) == []          # 提醒一次就停
        # 重复提醒：同一天不再响，第二天还会
        again = automations.save(db, 0, {"kind": "alert", "code": "600519", "metric": "price", "op": "<=", "threshold": 1350, "repeat": True})
        assert len(asyncio.run(automations.check_alerts(db, 0, MON))) == 1
        assert asyncio.run(automations.check_alerts(db, 0, MON + timedelta(hours=1))) == []
        assert len(asyncio.run(automations.check_alerts(db, 0, MON + timedelta(days=1)))) == 1
        # 取不到价格：不判，不拿默认值去触发
        async def nothing(codes):
            return {}
        monkeypatch.setattr(automations, "fetch_sina_quotes", nothing)
        assert asyncio.run(automations.check_alerts(db, 0, MON + timedelta(days=2))) == []
        for a in (auto, again):
            automations.delete(db, 0, a.id)


def test_events_reach_the_daily_digest(monkeypatch):
    async def quotes(codes):
        return {c: {"price": 10.0, "change_pct": 0.1} for c in codes}

    async def notify(text, buttons=None):
        return True
    monkeypatch.setattr(automations, "fetch_sina_quotes", quotes)
    monkeypatch.setattr(automations.channels, "notify", notify)
    monkeypatch.setattr(watcher, "fetch_sina_quotes", quotes)
    day = datetime(2026, 11, 2, 10, 0)
    with Session(get_engine()) as db:
        auto = automations.save(db, 0, {"kind": "alert", "code": "000001", "name": "平安银行", "metric": "price", "op": "<=", "threshold": 11})
        asyncio.run(automations.check_alerts(db, 0, day))
        # 盯盘之前触发的提醒：当天的简报里要有它，而且不能让盯盘误以为今天已经跑过
        assert watcher.recent(db, 0, 1) == [] or watcher.recent(db, 0, 1)[0]["day"] != "2026-11-02"
        digest = asyncio.run(watcher.run(db, 0, today=day.date(), push=False))
        assert any(e["kind"] == "alert" and "平安银行" in e["name"] for e in digest["events"])
        # 之后再跑一次任务：直接写进已有的简报，重跑盯盘也不丢
        task = automations.save(db, 0, {"kind": "task", "prompt": "复盘一下我的持仓", "schedule": "每天 08:30"})
        asyncio.run(automations.run_task(db, task, manual=True, ask=_fake_ask(), now=day))
        digest = asyncio.run(watcher.run(db, 0, today=day.date(), push=False))
        kinds = [e["kind"] for e in digest["events"]]
        assert kinds.count("alert") == 1 and kinds.count("task") == 1
        for a in (auto, task):
            automations.delete(db, 0, a.id)


def test_routes():
    client = TestClient(app)
    r = client.post("/api/automations", json={"kind": "task", "prompt": "复盘一下我的持仓", "schedule": "每周一 9点"})
    assert r.status_code == 200 and r.json()["schedule"] == "每周一 09:00" and r.json()["next_run_at"]
    tid = r.json()["id"]
    assert client.post("/api/automations", json={"kind": "task", "prompt": "复盘一下", "schedule": "有空的时候"}).status_code == 422
    assert client.post("/api/automations", json={"kind": "alert", "code": "茅台", "metric": "price", "op": "<=", "threshold": 1}).status_code == 422
    assert client.post("/api/automations/schedule/parse", json={"text": "工作日下午3点40"}).json()["text"] == "工作日 15:40"
    r = client.put(f"/api/automations/{tid}", json={"enabled": False})
    assert r.json()["enabled"] is False and r.json()["next_run_at"] is None
    listing = client.get("/api/automations").json()
    assert [a["id"] for a in listing["items"]] == [tid] and {m["key"] for m in listing["metrics"]} >= {"price", "pe_percentile"}
    assert client.delete(f"/api/automations/{tid}").json() == {"ok": True}
    assert client.delete(f"/api/automations/{tid}").status_code == 404
