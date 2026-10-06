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


# ── 证据外置与定点修订 ─────────────────────────────────

def test_long_evidence_is_compacted_for_the_model_but_short_evidence_is_untouched():
    import json

    from wealthpilot.services import evidence

    short = json.dumps({"price": 1258.62, "pe_ttm": 19.32})
    assert evidence.compact(short) == short
    peers = [{"code": f"60{i:04d}", "name": f"公司{i}", "pe_ttm": 10 + i, "total_mv_yi": 1000 - i} for i in range(30)]
    report = {"title": "2026年半年度报告", "sections": [{"topic": "管理层讨论", "excerpt": "正文" * 1500}], "peers": peers,
              "limitations": ["只有 6 个持有期"]}
    out = evidence.compact(json.dumps(report, ensure_ascii=False), 1600)
    data = json.loads(out)
    assert len(out) <= 1600 and data["title"] == "2026年半年度报告" and data["limitations"] == ["只有 6 个持有期"]
    assert "已省略" in data["sections"][0]["excerpt"] and "项已省略" in data["peers"][-1]
    assert data["peers"][0]["pe_ttm"] == 10                      # 留下的行里数字原样保留
    text = evidence.brief({"id": "E-abc", "tool": "get_x", "input": {"code": "600519"}, "output": "未获取到数据",
                           "provenance": {"as_of": {"600519": "2026-09-30"}, "basis": "很长的口径说明" * 20}})
    assert text == '[E-abc] get_x({"code":"600519"}) → 未获取到数据（数据日期 2026-09-30）'   # 不再附整段元数据


async def test_repair_patches_only_the_flagged_spots_and_gives_up_cleanly():
    import json

    from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent

    draft = "## 结论\n毛利率 23.93% [E-1]，预计明年回到 30% 左右。\n## 风险\n负债率 63.65% [E-1]。"
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(text=json.dumps({"edits": [{"find": "，预计明年回到 30% 左右", "replace": ""}]}, ensure_ascii=False))

    fixed = await SynthesizerAgent(SimpleNamespace(create=create), "m").repair(draft, ["以下数字未出现在工具返回中，可能是编造的：30"], ["30"])
    assert fixed == "## 结论\n毛利率 23.93% [E-1]。\n## 风险\n负债率 63.65% [E-1]。"
    assert "证据" not in calls[0]["messages"][0]["content"].split("回答全文")[0] and len(calls) == 1   # 不重发证据

    bad = lambda text: SynthesizerAgent(SimpleNamespace(create=lambda **kw: SimpleNamespace(text=text)), "m")  # noqa: E731
    assert await bad('{"edits":[{"find":"原文里没有这句","replace":""}]}').repair(draft, [], ["30"]) == ""   # 套不上：放弃，退回完整重写
    assert await bad("不是 JSON").repair(draft, [], ["30"]) == ""
    assert await bad('{"edits":[]}').repair(draft, [], ["30"]) == ""


def test_last_resort_trim_drops_only_the_clause_with_the_unverifiable_number():
    from wealthpilot.services.agents.synthesizer_agent import strip_ungrounded

    answer = ("## 结论\n上涨 2567 家 [E-1]，下跌 2824 家 [E-1]，上涨家数不足 50%，情绪偏弱。\n"
              "- 生物制品领涨，中位涨幅 3.16% [E-2]。\n- 预计明天反弹 50 点。\n\n| 行业 | 涨幅 |\n|---|---|\n| 元件 | 50 |\n## 50 这个标题不动")
    out = strip_ungrounded(answer, ["50"])
    assert "上涨 2567 家 [E-1]，下跌 2824 家 [E-1]，情绪偏弱。" in out          # 只删中间那半句
    assert "3.16%" in out and "预计明天反弹" not in out                      # 整条都靠这个数的列表项被删掉
    assert "| 元件 | — |" in out and "## 50 这个标题不动" in out             # 表格换成"—"，标题不碰
    assert "2567" in strip_ungrounded("上涨 2567 家，占 50%。", ["50"])      # 2567 里的 "5" 不会被误伤
    assert strip_ungrounded(answer, []) == answer


# ── 多空辩论 ────────────────────────────────────────────

def _debate_results():
    from wealthpilot.services.agents.base import AgentResult
    ev = [{"id": "E-aaaaaaaaaaaa", "tool": "get_valuation_history", "input": {"code": "600519"}, "status": "ok",
           "output": '{"pe": {"current": 19.32, "percentile": 4.1}}'},
          {"id": "E-bbbbbbbbbbbb", "tool": "get_financial_indicators", "input": {"code": "600519"}, "status": "ok",
           "output": '{"reports": [{"report_date": "2026-06-30", "revenue_yoy_pct": 1.47, "net_profit_yoy_pct": -1.95}]}'}]
    return [AgentResult("valuation", "研究估值", "PE 19.32", ev)]


def test_debate_drops_points_with_fake_evidence_or_invented_numbers():
    from wealthpilot.services.agents import debate
    raw = {"points": [
        {"text": "PE 分位只有 4.1%，是近几年最便宜的时候", "evidence": ["E-aaaaaaaaaaaa"]},
        {"text": "明年利润会增长 30%", "evidence": ["E-bbbbbbbbbbbb"]},          # 30 不在任何证据里
        {"text": "机构都在抢筹", "evidence": ["E-cccccccccccc"]},               # 证据编号是编的
        {"text": "没有证据的话", "evidence": []},
    ], "weakness": "净利润同比 -1.95%，增长还没恢复"}
    out = debate.validate(raw, _debate_results())
    assert [p["text"] for p in out["points"]] == ["PE 分位只有 4.1%，是近几年最便宜的时候"]
    assert out["points"][0]["evidence"] == ["E-aaaaaaaaaaaa"] and "1.95" in out["weakness"]


def test_debate_runs_both_sides_and_briefs_the_writer():
    import asyncio
    from types import SimpleNamespace

    from wealthpilot.services.agents import debate

    class Model:
        def __init__(self):
            self.systems = []

        def create(self, **kw):
            self.systems.append(kw["system"])
            if "看多方" in kw["system"]:
                return SimpleNamespace(text='{"points":[{"text":"PE 分位 4.1%，很便宜","evidence":["E-aaaaaaaaaaaa"]}],"weakness":"增长停了"}')
            return SimpleNamespace(text='{"points":[{"text":"净利润同比 -1.95%，还在掉","evidence":["E-bbbbbbbbbbbb"]}],"weakness":"估值已经很低"}')

    model = Model()
    out = asyncio.run(debate.run(model, "m", "贵州茅台（600519）", "分析茅台", _debate_results()))
    assert len(model.systems) == 2 and out["bull"]["points"] and out["bear"]["points"]
    text = debate.brief(out)
    assert "看多方" in text and "看空方" in text and "[E-aaaaaaaaaaaa]" in text and "不要各打五十大板" in text

    class Broken:
        def create(self, **kw):
            raise RuntimeError("offline")
    assert asyncio.run(debate.run(Broken(), "m", "x", "q", _debate_results())) is None      # 辩论失败不影响研究

    class Empty:
        def create(self, **kw):
            return SimpleNamespace(text='{"points":[],"weakness":""}')
    assert asyncio.run(debate.run(Empty(), "m", "x", "q", _debate_results())) is None


def test_broker_target_price_can_be_quoted_but_not_asserted():
    from wealthpilot.services.agents.critic_agent import CriticAgent
    check = CriticAgent._check_research_rules
    assert not [i for i in check("## 预期\n券商给出的目标价区间是 1430 到 2030 元。", []) if "目标价" in i]
    assert [i for i in check("## 结论\n我们给出目标价 1800 元。", []) if "目标价" in i]


def test_playbook_evidence_is_judged_by_code_not_by_the_model():
    from unittest.mock import Mock

    from wealthpilot.services.agents.base import AgentResult
    from wealthpilot.services.agents.critic_agent import CriticAgent
    from wealthpilot.services.agents.playbooks import PLAYBOOKS

    def result(*tools):
        return AgentResult("x", "g", "", [{"id": f"E-{i:012d}", "tool": t, "input": {}, "output": "{}", "status": "ok"} for i, t in enumerate(tools)])

    client = Mock()
    critic = CriticAgent(client, "m")
    criteria = list(PLAYBOOKS["stock_deep"].criteria)
    full = result("get_financial_indicators", "get_valuation_history", "get_stock_kline", "get_industry_peers",
                  "get_capital_flow", "get_consensus_forecast")
    assert critic.review_evidence("q", criteria, [full]).passed
    client.create.assert_not_called()                      # 固定模板：取到了就是取到了，不再问模型
    partial = result("get_financial_indicators", "get_valuation_history", "get_stock_kline")
    verdict = critic.review_evidence("q", criteria, [partial])
    assert not verdict.passed and verdict.missing_evidence == ["所属行业与同行对比", "资金流向或股东、机构持仓的变化", "卖方一致预期或公司的业绩预告"]
    client.create.assert_not_called()


def test_sizing_violation_is_repairable_but_never_published_as_is():
    from wealthpilot.services.agents.critic_agent import number_only, repairable
    numbers = "以下数字未出现在工具返回中，可能是编造的：12.4"
    sizing = "用户尚未完成风险测评，不得给出具体仓位或价位，但回答中出现：减仓5%"
    assert repairable([numbers, sizing]) and not number_only([numbers, sizing])
    assert number_only([numbers]) and not repairable([numbers, "回答缺少必须的章节（需作为标题出现）：多空"])
    assert not repairable([])


def test_miscopied_evidence_ids_are_fixed_by_code():
    from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent
    results = _debate_results()
    draft = "PE 19.32 [E-aaaaaaaaaaa]，营收同比 1.47% [E-bbbbbbbbbbbb]，还有一句乱引 [E-123456789abc]。"
    fixed = SynthesizerAgent.fix_citations(draft, results)
    assert "[E-aaaaaaaaaaaa]" in fixed           # 少抄一位：能唯一对上，补全
    assert "[E-bbbbbbbbbbbb]" in fixed           # 本来就对的不动
    assert "E-123456789abc" not in fixed and "还有一句乱引" in fixed   # 对不上的只删标记，不删话


def test_repair_applies_what_it_can():
    import asyncio
    from types import SimpleNamespace

    from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent
    reply = '{"edits":[{"find":"减仓 5%","replace":"适当减仓"},{"find":"这一段原文里没有","replace":"x"}]}'
    client = SimpleNamespace(create=lambda **kw: SimpleNamespace(text=reply), supports_json_mode=False)
    out = asyncio.run(SynthesizerAgent(client, "m").repair("建议减仓 5%，其余不动。", ["x"], []))
    assert out == "建议适当减仓，其余不动。"


def test_third_party_actions_are_facts_not_advice():
    from wealthpilot.services.agents.critic_agent import user_actions
    # 别人做了什么：事实
    assert user_actions("公募基金二季度减仓 33.27%，筹码在松动。") == []
    assert user_actions("| 基金 | 减仓 | -31.58% |") == []
    assert user_actions("大宗交易里机构专用席位卖出 1299.52 元，平价成交。") == []
    # 让用户做什么：建议
    assert user_actions("基金都在减仓，建议你也减仓 30%。") == [("减仓", "30", "%")]
    assert user_actions("跌破均线就止损，卖出价 1475 元。") == [("卖出", "1475", "元")]
    assert user_actions("仓位控制在 2 成以内。") == [("仓位", "2", "成")]
