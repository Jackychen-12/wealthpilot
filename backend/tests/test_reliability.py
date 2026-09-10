"""Regression cases from the research-framework review; no live model required."""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from wealthpilot.main import app
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services import analysis, backtest, simulation
from wealthpilot.services.agents import orchestrator, tools
from wealthpilot.services.agents.base import AgentResult, BaseAgent
from wealthpilot.services.agents.critic_agent import CriticAgent, Verdict
from wealthpilot.services.agents.planner_agent import Plan, PlannerAgent, Task
from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent, check_numeric_grounding


def holding(code, amount=100):
    return PortfolioHolding(fund_code=code, fund_name=code, shares=amount,
                            cost_price=1, buy_date=date(2025, 1, 1))


def series(values, start=date(2025, 1, 1)):
    return [{"nav_date": str(start + timedelta(days=i)), "nav": v,
             "daily_return": 0 if i == 0 else (v / values[i - 1] - 1) * 100}
            for i, v in enumerate(values)]


def evidence(output):
    return [AgentResult("risk", "verify", "", [{"tool": "test", "input": {}, "output": output}])]


def test_missing_benchmark_is_not_fabricated():
    assert analysis.calculate_overview([], {})["excess_return_pct"] is None


def test_correlation_requires_common_dates():
    a = series([1, 2, 3, 4, 5, 6])
    b = series([1, 2, 3, 4, 5, 6], date(2026, 1, 1))
    assert analysis.calculate_correlation({"A": a, "B": b})["A"]["B"] is None


def test_correlation_preserves_zero_returns():
    dates = [str(date(2025, 1, 1) + timedelta(days=i)) for i in range(6)]
    a = [0, 1, 0, 2, 0, 3]
    b = [3, 0, 2, 0, 1, 0]
    hist = {c: [{"nav_date": d, "daily_return": r} for d, r in zip(dates, values)]
            for c, values in [("A", a), ("B", b)]}
    assert analysis.calculate_correlation(hist)["A"]["B"] == round(analysis._pearson(a, b), 3)


def test_annualization_uses_trading_year():
    assert backtest._annualized(10, 252) == pytest.approx(10)


def test_backtest_executes_after_signal():
    result = backtest.backtest_rule(series([100, 90, 80, 85]), [{"drawdown_pct": 5, "add_pct": 50}], execution_lag=1)
    event = result["strategy"]["events"][0]
    assert event["date"] == "2025-01-03"
    assert event["nav"] == 80
    assert event["signal_date"] == "2025-01-02"


def test_multiple_targets_are_solved_together():
    out = simulation.simulate_change([holding("A"), holding("B")], {"A": 1, "B": 1}, None,
                                    [{"fund_code": "A", "target_pct": 30}, {"fund_code": "B", "target_pct": 70}])
    assert out["after"]["weights"] == {"A": 0.3, "B": 0.7}


def test_duplicate_lots_are_aggregated():
    weights = simulation.portfolio_weights([holding("A"), holding("A"), holding("B")], {"A": 1, "B": 1})
    assert weights["A"] == pytest.approx(2 / 3)


def test_missing_history_cannot_pass_constraints():
    result = simulation.check_constraints(InvestorProfile(), [holding("A")], {"A": 1}, None)
    assert result["passed"] is False
    assert result["status"] == "insufficient_data"


def test_missing_history_cannot_produce_position_limit():
    result = simulation.max_position_within_drawdown("A", [holding("A"), holding("B")],
                                                   {"A": 1, "B": 1}, None, InvestorProfile())
    assert "error" in result
    assert "max_pct_within_tolerance" not in result


def test_cash_reserve_requires_cash_balance():
    result = simulation.check_constraints(InvestorProfile(liquidity_reserve=1000), [holding("A")],
                                         {"A": 1}, {"A": series([1, 1, 1])})
    assert result["passed"] is False


@pytest.mark.parametrize("answer,output", [
    ("收益率 +23.45%", "收益率 -23.45%"),
    ("预计收益率 5%", "无数据"),
    ("净值 1.5 元", "收益率 1.5%"),
])
def test_numeric_sign_unit_and_small_percent(answer, output):
    assert check_numeric_grounding(answer, evidence(output))["ungrounded"]


def test_critic_failure_does_not_pass():
    client = SimpleNamespace(create=Mock(side_effect=RuntimeError("offline")))
    verdict = CriticAgent(client, "m").review_evidence("q", ["需来源"], evidence("x"))
    assert not verdict.review_complete


def test_critic_receives_raw_evidence():
    client = SimpleNamespace(create=Mock(return_value=SimpleNamespace(text='{"missing":[]}')))
    CriticAgent(client, "m").review_evidence("q", ["原始净值"], evidence("RAW_NAV_1.5983"))
    assert "RAW_NAV_1.5983" in client.create.call_args.kwargs["messages"][0]["content"]


@pytest.mark.parametrize("count", [1, 2])
async def test_real_orchestrator_never_releases_rejected_draft(monkeypatch, count):
    settings = SimpleNamespace(active_model="fake", critic_enabled=True, agent_max_parallel=2,
                               critic_max_replans=1, critic_max_rewrites=2)
    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator, "create_ai_client", lambda _: Mock())
    monkeypatch.setattr(PlannerAgent, "plan", Mock(return_value=Plan("test", [
        Task(f"t{i}", "market", "query") for i in range(count)
    ], ["需要证据"])))
    monkeypatch.setattr(BaseAgent, "run", AsyncMock(return_value=AgentResult("market", "query", "BAD_DRAFT_1.85", [])))
    monkeypatch.setattr(SynthesizerAgent, "run", AsyncMock(return_value="BAD_DRAFT_1.85"))
    monkeypatch.setattr(CriticAgent, "review_evidence", Mock(return_value=Verdict(passed=True)))
    monkeypatch.setattr(CriticAgent, "review_answer", Mock(return_value=Verdict(passed=False, issues=["未溯源"])))
    events = []
    async def emit(event):
        events.append(event)
    await orchestrator._run_pipeline("q", [], [], {}, {}, None, None, None, 0, emit)
    assert all("BAD_DRAFT" not in e.get("content", "") for e in events if e["type"] in ("delta", "done"))
    done = next(e for e in events if e["type"] == "done")
    assert done["meta"]["status"] != "passed"


async def test_backtest_fetches_requested_window(monkeypatch):
    fetch = AsyncMock(return_value=series([1] * 250))
    monkeypatch.setattr(tools, "fetch_fund_nav", fetch)
    await tools.execute_tool("backtest_rule", {"fund_code": "A", "days": 250, "triggers": []},
                             [], {}, {"A": series([1] * 60)})
    fetch.assert_awaited_once_with("A", 250)


def test_alert_endpoint_has_user_dependency():
    with TestClient(app) as client:
        assert client.get("/api/alerts").status_code == 200
