"""事后验证：验证点的校验、到期核对、成绩单与操作建议单。不联网、不调模型。"""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from wealthpilot.main import app
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import checkpoints, stocks
from wealthpilot.services.agents.critic_agent import CriticAgent
from wealthpilot.services.agents.planner_agent import PlannerAgent
from wealthpilot.storage.db import get_engine

MAOTAI = {"code": "600519", "name": "贵州茅台", "asset_type": "stock"}
BASE = {"600519": {"revenue_yoy_pct": (1.3, "2026-06-30"), "pe_percentile": (4.1, "2026-09-30"),
                   "excess_return_pct": (0.0, "2026-09-30")}}
TODAY = date(2026, 10, 4)


@pytest.fixture
def db():
    with TestClient(app):  # 触发建表
        pass
    with Session(get_engine()) as session:
        for model in (Checkpoint, TradeProposal):
            for row in session.query(model).all():
                session.delete(row)
        session.commit()
        yield session


def advice(monkeypatch, on: bool):
    monkeypatch.setattr(checkpoints, "get_settings", lambda: SimpleNamespace(advice_mode=on, local_user_id=0))


def test_validation_drops_what_code_cannot_verify(monkeypatch):
    advice(monkeypatch, False)
    raw = [
        {"code": "600519", "metric": "revenue_yoy_pct", "op": ">=", "threshold": 0, "statement": "增长未转负"},
        {"code": "600519", "metric": "revenue_yoy_pct", "op": ">=", "threshold": 5},      # 同一指标重复
        {"code": "000001", "metric": "revenue_yoy_pct", "op": ">=", "threshold": 0},      # 不是本次研究的股票
        {"code": "600519", "metric": "target_price", "op": ">=", "threshold": 2000},      # 不在白名单
        {"code": "600519", "metric": "pe_percentile", "op": "<=", "threshold": 130},      # 分位超界
        {"code": "600519", "metric": "gross_margin_pct", "op": ">=", "threshold": 90},    # 取不到基准值
        {"code": "600519", "metric": "excess_return_pct", "op": ">=", "threshold": 0},    # 涨跌类只在建议模式开放
        {"code": "600519", "metric": "pe_percentile", "op": "<", "threshold": 30},        # 非法比较符
        {"code": "600519", "metric": "pe_percentile", "op": "<=", "threshold": 30, "horizon_days": 9999},
    ]
    out = checkpoints.validate_checkpoints(raw, {"600519": MAOTAI}, BASE, TODAY)
    assert [(c["metric"], c["threshold"]) for c in out] == [("revenue_yoy_pct", 0.0), ("pe_percentile", 30.0)]
    assert out[0]["due_date"] == "" and out[0]["baseline_as_of"] == "2026-06-30"   # 财务类等下一期财报
    assert out[1]["due_date"] == "2027-04-02"                                       # 期限被截到 180 天


def test_market_checkpoints_only_in_advice_mode(monkeypatch):
    raw = [{"code": "600519", "metric": "excess_return_pct", "op": ">=", "threshold": 0, "horizon_days": 60}]
    advice(monkeypatch, True)
    assert len(checkpoints.validate_checkpoints(raw, {"600519": MAOTAI}, BASE, TODAY)) == 1


def test_proposals_need_a_held_position_to_reduce():
    holding = SimpleNamespace(fund_code="600519", shares=300)
    raw = [{"code": "600519", "action": "reduce", "shares": 500, "reason": "估值偏高"},
           {"code": "600519", "action": "buy", "shares": 100},           # 同一只只留一条
           {"code": "300750", "action": "short", "shares": 100}]
    out = checkpoints.validate_proposals(raw, {"600519": MAOTAI, "300750": {"name": "宁德时代"}}, [holding])
    assert [(p["action"], p["shares"]) for p in out] == [("reduce", 300)]   # 不能减得比持有的多
    assert checkpoints.validate_proposals([{"code": "600519", "action": "sell"}], {"600519": MAOTAI}, []) == []
    odd = checkpoints.validate_proposals([{"code": "600519", "action": "buy", "shares": 150}], {"600519": MAOTAI}, [])
    assert odd[0]["shares"] is None   # 不是整手，数量留给用户定


def _cp(**kw):
    base = dict(user_id=7, code="600519", name="贵州茅台", metric="revenue_yoy_pct", op=">=", threshold=0,
                baseline_value=1.3, baseline_as_of="2026-06-30")
    return Checkpoint(**{**base, **kw})


async def test_financial_checkpoint_waits_for_next_report_then_judges(db, monkeypatch):
    reports = [{"report_date": "2026-06-30", "revenue_yoy_pct": 1.3}]

    async def indicators(code, periods=8):
        return reports

    monkeypatch.setattr(stocks, "fetch_financial_indicators", indicators)
    db.add(_cp())
    db.add(_cp(metric="net_profit_yoy_pct", threshold=5))
    db.commit()

    first = await checkpoints.verify_pending(db, 7, force=True, today=TODAY)
    assert first["checked"] == 0   # 新一期财报还没出，不能判

    # 出了两期：必须用紧接着的那一期（三季报），而不是最新的年报
    reports[:0] = [{"report_date": "2026-12-31", "revenue_yoy_pct": 9.0, "net_profit_yoy_pct": 9.0},
                   {"report_date": "2026-09-30", "revenue_yoy_pct": -2.5, "net_profit_yoy_pct": 6.0}]
    done = await checkpoints.verify_pending(db, 7, force=True, today=date(2027, 4, 1))
    assert (done["held"], done["broken"]) == (1, 1)
    rows = {c.metric: c for c in checkpoints.list_checkpoints(db, 7)}
    assert (rows["revenue_yoy_pct"].status, rows["revenue_yoy_pct"].actual_value, rows["revenue_yoy_pct"].actual_as_of) == ("broken", -2.5, "2026-09-30")
    assert rows["net_profit_yoy_pct"].status == "held"

    card = checkpoints.scorecard(db, 7)
    assert (card["held"], card["broken"], card["pending"], card["hold_rate_pct"]) == (1, 1, 0, 50.0)
    assert "被证伪" in checkpoints.prior_note(db, 7, ["600519"])
    assert checkpoints.prior_note(db, 7, ["000001"]) == ""


async def test_excess_return_is_measured_against_benchmark_at_due_date(db, monkeypatch):
    series = {"600519": [("2026-09-30", 100), ("2026-10-30", 110), ("2026-11-28", 120)],
              checkpoints.BENCHMARK: [("2026-09-30", 4.0), ("2026-10-30", 4.2), ("2026-11-28", 4.6)]}

    async def kline(code, days=60):
        return [{"nav_date": d, "nav": v} for d, v in reversed(series[code])]

    monkeypatch.setattr(stocks, "fetch_stock_kline", kline)
    db.add(_cp(metric="excess_return_pct", baseline_value=0, baseline_as_of="2026-09-30", due_date="2026-10-31"))
    db.commit()
    assert (await checkpoints.verify_pending(db, 7, force=True, today=date(2026, 10, 20)))["checked"] == 0   # 未到期
    await checkpoints.verify_pending(db, 7, force=True, today=date(2026, 12, 1))
    cp = checkpoints.list_checkpoints(db, 7)[0]
    # 只算到到期日为止：个股 +10%，基准 +5%，不受到期后走势影响
    assert (cp.status, cp.actual_value, cp.actual_as_of) == ("held", 5.0, "2026-10-30")


async def test_verification_is_throttled_unless_forced(db, monkeypatch):
    calls = []

    async def indicators(code, periods=8):
        calls.append(code)
        return []

    monkeypatch.setattr(stocks, "fetch_financial_indicators", indicators)
    db.add(_cp(user_id=8))
    db.commit()
    await checkpoints.verify_pending(db, 8, force=True, today=TODAY)
    assert (await checkpoints.verify_pending(db, 8, today=TODAY)).get("skipped")
    assert len(calls) == 1


def test_authorizing_a_proposal_updates_the_ledger_once(db):
    db.add(TradeProposal(user_id=0, code="600519", name="贵州茅台", action="buy", shares=100, price_ref=1250.0))
    db.add(_cp(user_id=0, status="broken", actual_value=-1.0))
    db.commit()
    with TestClient(app) as client:
        pid = client.get("/api/proposals").json()[0]["id"]
        assert client.post(f"/api/proposals/{pid}/authorize", json={"shares": 0, "price": 1}).status_code == 422
        done = client.post(f"/api/proposals/{pid}/authorize", json={"shares": 100, "price": 1260.5}).json()
        assert (done["status"], done["exec_shares"], done["exec_price"]) == ("executed", 100, 1260.5)
        held = [h for h in client.get("/api/portfolio").json() if h["fund_code"] == "600519"]
        assert held and held[0]["shares"] == 100 and held[0]["asset_type"] == "stock"
        # 同一条建议不能执行两次，也不能执行后再拒绝
        assert client.post(f"/api/proposals/{pid}/authorize", json={"shares": 100, "price": 1}).status_code == 409
        assert client.post(f"/api/proposals/{pid}/reject").status_code == 409
        # 已核对出结果的验证点不许删，成绩单不能靠删除来美化
        cid = client.get("/api/checkpoints").json()[0]["id"]
        assert client.delete(f"/api/checkpoints/{cid}").status_code == 409
        assert client.get("/api/checkpoints/scorecard").json()["broken"] == 1
        client.delete(f"/api/portfolio/{held[0]['id']}")


def test_review_intent_and_advice_mode_rules(monkeypatch):
    assert PlannerAgent.classify_by_rules("复盘一下之前对茅台的判断", [MAOTAI], False) == "review"
    answer = "## 结论\n目标价 1500 元 [E-1]。\n## 建议\n看多，失效条件：估值分位升破 80%。"
    settings = SimpleNamespace(advice_mode=False)
    monkeypatch.setattr("wealthpilot.services.agents.critic_agent.get_settings", lambda: settings)
    assert any("目标价" in i for i in CriticAgent._check_research_rules(answer, ["结论"]))
    settings.advice_mode = True
    assert CriticAgent._check_research_rules(answer, ["结论", "建议"]) == []
    assert any("失效" in i for i in CriticAgent._check_research_rules("## 结论\n## 建议\n买入", ["结论", "建议"]))
    assert any("承诺" in i for i in CriticAgent._check_research_rules(answer + "这只票稳赚。", ["结论", "建议"]))
