"""Agent 优化：用量统计、投资者记忆、审计日志、技能。不联网、不调模型。"""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wealthpilot.main import app
from wealthpilot.models.memory import AuditEvent, Memory
from wealthpilot.models.review import TradeProposal
from wealthpilot.services import memory, skills
from wealthpilot.services.agents.planner_agent import PlannerAgent
from wealthpilot.services.agents.registry import build_prompt
from wealthpilot.services.ai_client import Usage
from wealthpilot.storage.db import get_engine

MAOTAI = {"code": "600519", "name": "贵州茅台", "asset_type": "stock"}
EXAMPLES = Path(__file__).resolve().parents[1] / "skills"


@pytest.fixture
def db():
    with TestClient(app):
        pass
    with Session(get_engine()) as session:
        for model in (Memory, AuditEvent, TradeProposal):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        yield session


def test_usage_reports_cache_hit_rate():
    usage = Usage()
    usage.add(1000, 800, 200)
    usage.add(500, 0, 100)
    assert usage.as_dict() == {"calls": 2, "input_tokens": 1500, "cached_tokens": 800, "output_tokens": 300, "cache_hit_pct": 53.3}


def test_stable_prefix_keeps_volatile_holdings_out_of_the_system_prompt():
    holding = SimpleNamespace(fund_code="600519", fund_name="贵州茅台", shares=100, cost_price=1200.0, asset_type="stock",
                              category="equity", industry="白酒", buy_date="2025-01-01")
    volatile = build_prompt("portfolio", [holding], {"600519": 1258.62}, None)
    stable_a = build_prompt("portfolio", [holding], {"600519": 1258.62}, None, stable_prefix=True)
    stable_b = build_prompt("portfolio", [holding], {"600519": 1300.00}, None, stable_prefix=True)
    assert "1258.62" in volatile and "1258.62" not in stable_a
    assert stable_a == stable_b   # 价格变了，系统提示逐字不变，才能命中缓存


def test_only_the_users_own_durable_statements_are_remembered():
    got = memory.extract_preferences("帮我分析一下贵州茅台。记住，我不碰白酒以外的消费股；单只股票不超过两成仓位。它现在贵吗？")
    assert got == ["我不碰白酒以外的消费股", "单只股票不超过两成仓位"]
    assert memory.extract_preferences("茅台现在多少钱") == []
    assert memory.extract_preferences("我不买它是不是错了吗") == []   # 问句不是偏好


def test_memory_is_scoped_by_stock_and_feeds_the_prompt(db):
    memory.add(db, 5, "我只做长线", source="chat")
    memory.add(db, 5, "我只做长线", source="chat")                      # 重复的不再存
    memory.add(db, 5, "2026-10-05 没有采纳对五粮液的减仓建议，原因：仓位本来就小", kind="decision", code="000858")
    assert len(memory.list_memories(db, 5)) == 2
    assert "我只做长线" in memory.note(db, 5, ["600519"]) and "五粮液" not in memory.note(db, 5, ["600519"])
    assert "五粮液" in memory.note(db, 5, ["000858"])
    assert memory.note(db, 6) == ""


def test_audit_log_is_append_only_and_tamper_evident(db):
    memory.record(db, 5, "approval/asked", "减仓 五粮液", {"proposal_id": 1}, actor="agent")
    memory.record(db, 5, "approval/decided", "减仓 五粮液：不采纳", {"proposal_id": 1, "outcome": "rejected"}, actor="user")
    memory.record(db, 5, "order/filled", "buy 贵州茅台 100 股 @ 1258.62", {"order_id": 1}, actor="user")
    assert memory.verify(db, 5) == {"ok": True, "count": 3, "broken_at": None}
    assert [e["kind"] for e in memory.events(db, 5)] == ["order/filled", "approval/decided", "approval/asked"]

    target = db.exec(select(AuditEvent).where(AuditEvent.kind == "approval/decided")).one()
    target.summary = "减仓 五粮液：授权"                                  # 事后改口
    db.add(target)
    db.commit()
    assert memory.verify(db, 5)["ok"] is False and memory.verify(db, 5)["broken_at"] == target.id


def test_rejecting_a_proposal_with_a_reason_becomes_memory_and_audit(db):
    db.add(TradeProposal(user_id=0, code="000858", name="五粮液", action="reduce"))
    db.commit()
    with TestClient(app) as client:
        pid = client.get("/api/proposals").json()[0]["id"]
        assert client.post(f"/api/proposals/{pid}/reject", json={"reason": "仓位本来就小"}).json()["status"] == "rejected"
        remembered = client.get("/api/memory").json()
        assert remembered[0]["kind"] == "decision" and "仓位本来就小" in remembered[0]["content"] and remembered[0]["code"] == "000858"
        log = client.get("/api/audit").json()
        kinds = [e["kind"] for e in log["events"]]
        assert "approval/decided" in kinds and log["integrity"]["ok"]
        decided = next(e for e in log["events"] if e["kind"] == "approval/decided")
        assert decided["payload"]["outcome"] == "rejected" and decided["actor"] == "user"
        # 没有修改或删除审计事件的接口
        assert client.delete(f"/api/audit/{decided['id']}").status_code in (404, 405)


def test_example_skills_parse_and_bad_ones_explain_themselves():
    for file in EXAMPLES.glob("*.md"):
        skill, problems = skills.parse(file.read_text(encoding="utf-8"))
        assert skill is not None, (file.name, problems)
        assert skill.agent_goal(skill.agents[0])
    _, problems = skills.parse("---\nname: Bad Name\nmetadata:\n  wealthpilot:\n    agents: [astrology]\n---\n正文")
    text = "；".join(problems)
    assert "name 必填" in text and "description 必填" in text and "astrology" in text and "sections" in text
    assert skills.parse("没有 frontmatter")[1] == ["文件要以 --- 包起来的 YAML frontmatter 开头"]


def test_a_matching_skill_plans_the_research_without_calling_the_model(tmp_path, monkeypatch):
    shutil.copy(EXAMPLES / "dividend-check.md", tmp_path / "dividend-check.md")
    monkeypatch.setattr(skills, "roots", lambda: [tmp_path])
    client = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(AssertionError("技能命中时不该再问模型怎么规划")))
    plan = PlannerAgent(client, "m").plan("茅台的分红能持续吗，股息率值不值得拿", securities=[MAOTAI])
    assert (plan.playbook, plan.source) == ("skill:dividend-check", "skill")
    assert [t.agent for t in plan.tasks] == ["fundamental", "valuation"]
    assert all(t.goal.startswith("研究贵州茅台（600519）") for t in plan.tasks) and "get_dividend_history" in plan.tasks[0].goal
    assert plan.sections == ["结论", "分红记录", "分红能力", "估值", "风险"] and "吃老本" in plan.method
    # 需要股票却没解析出来：不硬套技能
    fallback = PlannerAgent(SimpleNamespace(create=lambda **kw: SimpleNamespace(text="不是 JSON")), "m").plan("高股息的股票有哪些", securities=[])
    assert not fallback.playbook.startswith("skill:")


def test_skills_can_be_edited_from_the_web_but_only_valid_ones_are_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "roots", lambda: [tmp_path])
    good = (EXAMPLES / "earnings-check.md").read_text(encoding="utf-8")
    with TestClient(app) as client:
        assert client.put("/api/skills/earnings-check", json={"content": good}).status_code == 200
        assert client.put("/api/skills/other-name", json={"content": good}).status_code == 422       # 文件名与 name 不一致
        assert client.put("/api/skills/broken", json={"content": "---\nname: broken\n---\n"}).status_code == 422
        listed = client.get("/api/skills").json()
        assert [s["name"] for s in listed["skills"]] == ["earnings-check"] and "name: my-method" in listed["template"]
        assert "财报季检查" in client.get("/api/skills/earnings-check").json()["content"]
        assert client.delete("/api/skills/earnings-check").status_code == 200
        assert client.get("/api/skills").json()["skills"] == []
