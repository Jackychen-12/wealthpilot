"""仓位推演与约束校验测试。

这组函数存在的意义就是"不让模型算"，所以它们自己必须算对 —— 全是纯函数，
可以把数值精确钉死。
"""

from datetime import date

import pytest

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.simulation import (
    check_constraints,
    concentration_metrics,
    max_position_within_drawdown,
    portfolio_weights,
    simulate_change,
)


def holding(code: str, shares: float, cost: float = 1.0, industry: str = "") -> PortfolioHolding:
    return PortfolioHolding(
        user_id=1, fund_code=code, fund_name=f"基金{code}", shares=shares,
        cost_price=cost, buy_date=date(2026, 1, 1), category="equity", industry=industry,
    )


def nav_series(drawdown_pct: float) -> list[dict]:
    """构造一段净值序列，其最大回撤约等于给定百分比。最新在前。"""
    peak = 100.0
    trough = peak * (1 - drawdown_pct / 100)
    # 时间正序为 [peak, trough, trough]，函数内部会 reverse，所以这里倒着放
    return [
        {"nav_date": "2026-03-01", "nav": trough, "daily_return": 0.0},
        {"nav_date": "2026-02-01", "nav": trough, "daily_return": 0.0},
        {"nav_date": "2026-01-01", "nav": peak, "daily_return": 0.0},
    ]


def profile(**kw) -> InvestorProfile:
    d = dict(user_id=1, risk_level=2, horizon_months=36, max_drawdown_tolerance=0.15,
             liquidity_reserve=0.0, experience_years=3.0, excluded_industries="")
    d.update(kw)
    return InvestorProfile(**d)


# ══════════════════════════════════════════════════════════
class TestWeights:
    def test_two_equal_holdings(self):
        h = [holding("A", 100), holding("B", 100)]
        w = portfolio_weights(h, {"A": 1.0, "B": 1.0})
        assert w == {"A": 0.5, "B": 0.5}

    def test_uneven_weights(self):
        h = [holding("A", 300), holding("B", 100)]
        w = portfolio_weights(h, {"A": 1.0, "B": 1.0})
        assert w["A"] == pytest.approx(0.75)
        assert w["B"] == pytest.approx(0.25)

    def test_uses_nav_not_cost(self):
        """权重按市值算，不是按成本。"""
        h = [holding("A", 100, cost=1.0), holding("B", 100, cost=1.0)]
        w = portfolio_weights(h, {"A": 3.0, "B": 1.0})
        assert w["A"] == pytest.approx(0.75)

    def test_missing_nav_falls_back_to_cost(self):
        h = [holding("A", 100, cost=2.0)]
        assert portfolio_weights(h, {})["A"] == 1.0

    def test_empty(self):
        assert portfolio_weights([], {}) == {}


class TestConcentration:
    def test_evenly_split_four(self):
        m = concentration_metrics({"A": .25, "B": .25, "C": .25, "D": .25})
        assert m["hhi"] == pytest.approx(0.25)
        assert m["effective_holdings"] == pytest.approx(4.0)
        assert m["max_weight"] == 0.25

    def test_single_holding(self):
        m = concentration_metrics({"A": 1.0})
        assert m["hhi"] == 1.0
        assert m["effective_holdings"] == 1.0

    def test_effective_holdings_exposes_fake_diversification(self):
        """持有 5 只但一只占 90% —— 有效持仓数应远小于 5。"""
        w = {"A": .90, "B": .025, "C": .025, "D": .025, "E": .025}
        m = concentration_metrics(w)
        assert m["count"] == 5
        assert m["effective_holdings"] < 1.3
        assert m["max_weight_code"] == "A"

    def test_empty(self):
        assert concentration_metrics({})["count"] == 0


class TestSimulateChange:
    def test_target_pct_reaches_target(self):
        """把 A 调到 60% 之后，A 的权重就应该正好是 60%。"""
        h = [holding("A", 100), holding("B", 100)]
        nav = {"A": 1.0, "B": 1.0}
        out = simulate_change(h, nav, None, [{"fund_code": "A", "target_pct": 60}])
        assert out["after"]["weights"]["A"] == pytest.approx(0.6, abs=1e-4)
        assert out["after"]["weights"]["B"] == pytest.approx(0.4, abs=1e-4)

    def test_target_pct_computes_delta_amount(self):
        h = [holding("A", 100), holding("B", 100)]
        out = simulate_change(h, {"A": 1.0, "B": 1.0}, None,
                              [{"fund_code": "A", "target_pct": 60}])
        # others=100，目标 60% → new = 100*0.6/0.4 = 150，delta = +50
        assert out["changes"][0]["delta_amount"] == pytest.approx(50.0)

    def test_amount_change(self):
        h = [holding("A", 100), holding("B", 100)]
        out = simulate_change(h, {"A": 1.0, "B": 1.0}, None,
                              [{"fund_code": "A", "amount": 100}])
        assert out["after"]["weights"]["A"] == pytest.approx(200 / 300, abs=1e-4)

    def test_negative_amount_cannot_go_below_zero(self):
        h = [holding("A", 100), holding("B", 100)]
        out = simulate_change(h, {"A": 1.0, "B": 1.0}, None,
                              [{"fund_code": "A", "amount": -500}])
        assert out["after"]["weights"].get("A", 0) == 0
        assert out["changes"][0]["after_value"] == 0

    def test_before_is_untouched(self):
        h = [holding("A", 100), holding("B", 100)]
        out = simulate_change(h, {"A": 1.0, "B": 1.0}, None,
                              [{"fund_code": "A", "target_pct": 80}])
        assert out["before"]["weights"]["A"] == pytest.approx(0.5)

    def test_target_100_rejected(self):
        h = [holding("A", 100), holding("B", 100)]
        out = simulate_change(h, {"A": 1.0, "B": 1.0}, None,
                              [{"fund_code": "A", "target_pct": 100}])
        assert "error" in out["changes"][0]

    def test_missing_spec_reports_error(self):
        h = [holding("A", 100)]
        out = simulate_change(h, {"A": 1.0}, None, [{"fund_code": "A"}])
        assert "error" in out["changes"][0]

    def test_weighted_drawdown_moves_with_weight(self):
        """把回撤大的基金加重，加权回撤估计应该上升。"""
        h = [holding("A", 100), holding("B", 100)]
        nav = {"A": 1.0, "B": 1.0}
        hist = {"A": nav_series(40), "B": nav_series(10)}
        out = simulate_change(h, nav, hist, [{"fund_code": "A", "target_pct": 80}])
        assert out["after"]["weighted_max_drawdown"] > out["before"]["weighted_max_drawdown"]

    def test_result_carries_caveat(self):
        out = simulate_change([holding("A", 100)], {"A": 1.0}, None,
                              [{"fund_code": "A", "amount": 10}])
        assert "保守上界" in out["note"]


class TestCheckConstraints:
    def test_no_profile_fails(self):
        r = check_constraints(None, [holding("A", 100)], {"A": 1.0}, None)
        assert not r["passed"]
        assert "风险测评" in r["violations"][0]

    def test_drawdown_within_tolerance_passes(self):
        h = [holding("A", 100)]
        r = check_constraints(profile(max_drawdown_tolerance=0.20), h, {"A": 1.0},
                              {"A": nav_series(10)})
        assert r["passed"]

    def test_drawdown_exceeding_tolerance_fails(self):
        h = [holding("A", 100)]
        r = check_constraints(profile(max_drawdown_tolerance=0.15), h, {"A": 1.0},
                              {"A": nav_series(40)})
        assert not r["passed"]
        assert any("回撤" in v for v in r["violations"])

    def test_excluded_industry_holding_flagged(self):
        h = [holding("A", 100, industry="白酒")]
        r = check_constraints(profile(excluded_industries="白酒"), h, {"A": 1.0}, None)
        assert not r["passed"]
        assert any("白酒" in v for v in r["violations"])

    def test_checks_proposed_change_not_just_current(self):
        """当前合规，但加仓后越界 —— 必须能拦住。"""
        h = [holding("A", 100), holding("B", 100)]
        nav, hist = {"A": 1.0, "B": 1.0}, {"A": nav_series(40), "B": nav_series(4)}
        p = profile(max_drawdown_tolerance=0.25)
        assert check_constraints(p, h, nav, hist)["passed"]
        after = check_constraints(p, h, nav, hist, [{"fund_code": "A", "target_pct": 90}])
        assert not after["passed"]

    def test_reports_what_was_checked(self):
        r = check_constraints(profile(), [holding("A", 100)], {"A": 1.0}, None)
        assert any("回撤" in c for c in r["checked"])


class TestPositionSizing:
    def test_no_profile_returns_error(self):
        r = max_position_within_drawdown("A", [holding("A", 100)], {"A": 1.0}, None, None)
        assert "error" in r

    def test_headroom_is_relative_to_current(self):
        h = [holding("A", 100), holding("B", 100)]
        nav, hist = {"A": 1.0, "B": 1.0}, {"A": nav_series(20), "B": nav_series(4)}
        r = max_position_within_drawdown("A", h, nav, hist, profile(max_drawdown_tolerance=0.15))
        assert r["current_pct"] == pytest.approx(50.0)
        assert r["headroom_pct"] == pytest.approx(r["max_pct_within_tolerance"] - 50.0)

    def test_riskier_fund_gets_lower_cap(self):
        h = [holding("A", 100), holding("B", 100)]
        nav = {"A": 1.0, "B": 1.0}
        p = profile(max_drawdown_tolerance=0.15)
        cap_risky = max_position_within_drawdown(
            "A", h, nav, {"A": nav_series(50), "B": nav_series(4)}, p
        )["max_pct_within_tolerance"]
        cap_mild = max_position_within_drawdown(
            "A", h, nav, {"A": nav_series(16), "B": nav_series(4)}, p
        )["max_pct_within_tolerance"]
        assert cap_risky < cap_mild

    def test_cap_never_exceeds_tolerance(self):
        h = [holding("A", 100), holding("B", 100)]
        nav, hist = {"A": 1.0, "B": 1.0}, {"A": nav_series(30), "B": nav_series(5)}
        p = profile(max_drawdown_tolerance=0.15)
        r = max_position_within_drawdown("A", h, nav, hist, p)
        assert r["drawdown_at_max"] <= p.max_drawdown_tolerance

    def test_result_carries_caveat(self):
        h = [holding("A", 100), holding("B", 100)]
        r = max_position_within_drawdown("A", h, {"A": 1.0, "B": 1.0},
                                         {"A": nav_series(10), "B": nav_series(5)}, profile())
        assert "不构成操作建议" in r["note"]
