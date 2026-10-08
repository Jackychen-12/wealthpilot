"""会话列表；从自己的对错里记经验；从反复的问法里提议方法。全部离线。"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wealthpilot.main import app
from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.memory import Memory
from wealthpilot.models.review import Checkpoint
from wealthpilot.services import lessons, memory
from wealthpilot.storage.db import get_engine

UID = 0


def _turn(db, conversation, question, name, code, *, status="passed", playbook="free", minutes_ago=10, answer="## 结论\n稳。"):
    when = datetime.now() - timedelta(minutes=minutes_ago)
    db.add(ChatMessage(user_id=UID, conversation_id=conversation, role="user", content=question, created_at=when))
    db.commit()
    meta = {"status": status, "playbook": playbook, "securities": [{"code": code, "name": name, "asset_type": "stock"}],
            "evidence": [{"id": "E-aaaaaaaaaaaa", "tool": "get_stock_quote", "input": {}, "output": "1", "status": "ok"}],
            "summary": {"conclusion": "稳。", "stance": "中性", "truncated": False}}
    row = ChatMessage(user_id=UID, conversation_id=conversation, role="assistant", content=answer, metadata_json=json.dumps(meta, ensure_ascii=False), created_at=when)
    db.add(row)
    db.commit()
    return row.id


def _wipe():
    with Session(get_engine()) as db:
        for model in (ChatMessage, Memory, Checkpoint):
            for row in db.exec(select(model).where(model.user_id == UID)).all():
                db.delete(row)
        db.commit()


def test_conversations_are_listed_newest_first_and_can_be_reopened():
    _wipe()
    with Session(get_engine()) as db:
        _turn(db, "c-old", "帮我分析一下贵州茅台", "贵州茅台", "600519", minutes_ago=300)
        _turn(db, "c-old", "那它的估值呢", "贵州茅台", "600519", minutes_ago=290)
        _turn(db, "c-new", "宁德时代怎么样", "宁德时代", "300750", minutes_ago=5)
        _turn(db, "auto-3-202610070830", "诊断一下我的持仓", "招商银行", "600036", minutes_ago=100)
    client = TestClient(app)
    listed = client.get("/api/conversations").json()
    assert [c["id"] for c in listed] == ["c-new", "auto-3-202610070830", "c-old"]
    old = listed[2]
    assert old["title"] == "帮我分析一下贵州茅台" and old["turns"] == 2 and old["securities"][0]["code"] == "600519"   # 标题是第一个问题
    assert listed[1]["source"] == "定时任务" and listed[0]["source"] == ""
    detail = client.get("/api/conversations/c-old").json()
    assert [t["question"] for t in detail["turns"]] == ["帮我分析一下贵州茅台", "那它的估值呢"]
    assert detail["turns"][0]["meta"]["evidence"][0]["tool"] == "get_stock_quote" and "checkpoints" in detail["turns"][0]
    assert client.get("/api/conversations/nope").status_code == 404
    _wipe()


def _checkpoint(db, *, status="pending", name="贵州茅台", code="600519", metric="revenue_yoy_pct", threshold=10.0, actual=None, statement="增长能恢复"):
    cp = Checkpoint(user_id=UID, code=code, name=name, metric=metric, op=">=", threshold=threshold, statement=statement,
                    baseline_value=12.0, baseline_as_of="2026-03-31", status=status, actual_value=actual, actual_as_of="2026-06-30",
                    checked_at=datetime.now() if status in ("held", "broken") else None, created_at=datetime(2026, 5, 1))
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


def test_a_broken_judgment_becomes_a_lesson_that_comes_back_for_that_stock():
    _wipe()
    with Session(get_engine()) as db:
        cp = _checkpoint(db, status="broken", actual=1.5)
        row = lessons.from_broken(db, cp)
        assert row.kind == "lesson" and row.code == "600519" and row.source == "checkpoint"
        assert "营收同比会不低于 10%" in row.content and "实际是 1.5%" in row.content and "增长能恢复" in row.content and "2026-05-01" in row.content
        assert lessons.from_broken(db, cp).id == row.id                       # 同一条不会记两遍
        memory.add(db, UID, "我只做长线", kind="preference")
        note = memory.note(db, UID, ["600519"])
        assert "你自己过去判断落空后记下的经验" in note and "判断落空" in note and "[偏好] 我只做长线" in note
        assert "判断落空" not in memory.note(db, UID, ["300750"])               # 研究别的股票时不带这条
    assert [m["kind"] for m in TestClient(app).get("/api/lessons").json()] == ["lesson"]
    _wipe()


async def test_verification_records_the_lesson_by_itself(monkeypatch):
    from wealthpilot.services import checkpoints
    _wipe()

    async def values(code):
        return {"revenue_yoy_pct": (1.5, "2026-09-30")}
    monkeypatch.setattr(checkpoints, "current_values", values)
    with Session(get_engine()) as db:
        _checkpoint(db)
        counts = await checkpoints.verify_pending(db, UID, force=True)
        assert counts["broken"] == 1
        found = lessons.list_lessons(db, UID)
        assert len(found) == 1 and "贵州茅台" in found[0].content
    _wipe()


def test_reflection_keeps_only_patterns_backed_by_two_records():
    _wipe()

    class Model:
        def __init__(self):
            self.calls = 0

        def create(self, **kw):
            self.calls += 1
            assert "1. " in kw["messages"][0]["content"]
            return SimpleNamespace(text=json.dumps({"lessons": [
                {"text": "对营收增速恢复的判断普遍偏乐观，下次把门槛放低一些", "based_on": [1, 2]},
                {"text": "只有一条记录支撑的所谓规律", "based_on": [3]},
                {"text": "引用了不存在的记录", "based_on": [8, 9]}]}, ensure_ascii=False))
    with Session(get_engine()) as db:
        model = Model()
        for i in range(2):
            _checkpoint(db, status="broken", actual=1.0 + i, code=f"60000{i}", name=f"公司{i}")
        try:
            lessons.reflect(db, UID, model, "m")
            raise AssertionError("记录不够时不该调用模型")
        except ValueError as e:
            assert "太少" in str(e) and model.calls == 0
        for i in range(2, 4):
            _checkpoint(db, status="held", actual=20.0, code=f"60000{i}", name=f"公司{i}")
        saved = lessons.reflect(db, UID, model, "m")
        assert [m.content for m in saved] == ["对营收增速恢复的判断普遍偏乐观，下次把门槛放低一些"] and saved[0].source == "reflection" and model.calls == 1
    _wipe()


def test_repeated_question_patterns_are_noticed_but_generic_ones_are_not():
    _wipe()
    with Session(get_engine()) as db:
        _turn(db, "s1", "帮我看看贵州茅台的分红能不能持续", "贵州茅台", "600519")
        _turn(db, "s2", "招商银行的分红能持续吗", "招商银行", "600036")
        _turn(db, "s3", "帮我看看茅台分红能不能持续", "贵州茅台", "600519")       # 简称也认得
        _turn(db, "s4", "看看长江电力的分红能不能持续", "长江电力", "600900")
        for i, (name, code) in enumerate([("贵州茅台", "600519"), ("宁德时代", "300750"), ("五粮液", "000858")]):
            _turn(db, f"g{i}", f"帮我深度分析一下{name}", name, code, playbook="stock_deep")   # 通用问法：不算一种方法
        _turn(db, "x1", "比亚迪的海外销量怎么样", "比亚迪", "002594")                          # 只问过一次
        found = lessons.suggestions(db, UID)
        assert len(found) == 1
        s = found[0]
        assert s["times"] == 4 and set(s["stocks"]) == {"贵州茅台", "招商银行", "长江电力"} and "××" in s["pattern"]
        assert "分红能不能持续" in s["description"] and "不要加我没问过的内容" in s["description"]
        client = TestClient(app)
        assert [x["key"] for x in client.get("/api/skills/suggestions").json()] == [s["key"]]
        assert client.post(f"/api/skills/suggestions/{s['key']}/dismiss").json() == {"ok": True}
        assert client.get("/api/skills/suggestions").json() == []                              # 说过不要就不再提
    _wipe()


def test_masking_handles_codes_full_names_and_aliases():
    sec = [{"name": "贵州茅台", "code": "600519"}]
    assert lessons._mask("贵州茅台（600519）的分红", sec) == "××的分红"
    assert lessons._mask("茅台的分红", sec) == "××的分红"
    assert lessons._focus(lessons._mask("帮我深度分析一下贵州茅台", sec)) == ""
    assert lessons._focus(lessons._mask("帮我看看贵州茅台的分红能不能持续", sec)) == "分红能不能持续"


def test_past_sessions_can_be_found_by_what_was_said_in_them():
    import argparse

    from wealthpilot import cli
    _wipe()
    with Session(get_engine()) as db:
        _turn(db, "c-moutai", "帮我分析一下贵州茅台", "贵州茅台", "600519", minutes_ago=300, answer="## 结论\n批价回落，渠道库存偏高，短期承压。")
        _turn(db, "c-catl", "300750 怎么样", "宁德时代", "300750", minutes_ago=5, answer="## 结论\n储能订单在放量。")
    client = TestClient(app)
    found = client.get("/api/conversations", params={"q": "渠道库存"}).json()
    assert [c["id"] for c in found] == ["c-moutai"] and "渠道库存偏高" in found[0]["match"]          # 回答里说过的话也找得到
    by_name = client.get("/api/conversations", params={"q": "宁德"}).json()
    assert [c["id"] for c in by_name] == ["c-catl"] and "宁德时代" in by_name[0]["match"]          # 问的时候只写了代码，按名字也能找到
    assert client.get("/api/conversations", params={"q": "比亚迪"}).json() == []
    assert len(client.get("/api/conversations").json()) == 2 and "match" not in client.get("/api/conversations").json()[0]

    out: list[str] = []
    assert cli.cmd_sessions(argparse.Namespace(query="渠道库存"), out=out.append) == 0
    assert "帮我分析一下贵州茅台" in out[0] and "渠道库存偏高" in out[1] and "300750" not in "\n".join(out)
    out.clear()
    cli.cmd_sessions(argparse.Namespace(query="比亚迪"), out=out.append)
    assert out == ["没有哪个会话提到过「比亚迪」。"]
    out.clear()
    cli.cmd_sessions(argparse.Namespace(query=None), out=out.append)
    assert len(out) == 3 and "wealthpilot -c" in out[-1]
    _wipe()
