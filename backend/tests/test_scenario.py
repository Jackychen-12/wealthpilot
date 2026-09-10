"""情景分析测试。"""

from datetime import date

import pytest

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.scenario import (
    PRESET_SCENARIOS,
    run_all_presets,
    run_preset,
    run_scenario,
)


def holding(code, shares=100, cost=1.0, category="equity", industry="", asset_type="fund"):
    return PortfolioHolding(
        user_id=1, asset_type=asset_type, fund_code=code, fund_name=f"标的{code}",
        shares=shares, cost_price=cost, buy_date=date(2026, 1, 1),
        category=category, industry=industry,
    )


class TestShockApplication:
    def test_market_shock_applies_to_all(self):
        h = [holding("A"), holding("B")]
        out = run_scenario(h, {"A": 1.0, "B": 1.0}, market_pct=-10)
        assert out["pnl_pct"] == pytest.approx(-10.0)

    def test_category_overrides_market(self):
        """债券不该吃全市场的权益冲击。"""
        h = [holding("A", category="equity"), holding("B", category="bond")]
        out = run_scenario(h, {"A": 1.0, "B": 1.0},
                           market_pct=-20, category_pct={"bond": -2})
        by = {x["fund_code"]: x for x in out["holdings"]}
        assert by["A"]["shock_pct"] == -20
        assert by["B"]["shock_pct"] == -2
        assert by["B"]["matched_level"] == "category"

    def test_industry_overrides_category(self):
        h = [holding("A", industry="白酒", category="equity")]
        out = run_scenario(h, {"A": 1.0}, market_pct=-5,
                           category_pct={"equity": -10}, industry_pct={"白酒": -30})
        assert out["holdings"][0]["shock_pct"] == -30
        assert out["holdings"][0]["matched_level"] == "industry"

    def test_asset_level_overrides_everything(self):
        h = [holding("A", industry="白酒")]
        out = run_scenario(h, {"A": 1.0}, market_pct=-5,
                           industry_pct={"白酒": -30}, asset_pct={"A": -50})
        assert out["holdings"][0]["shock_pct"] == -50
        assert out["holdings"][0]["matched_level"] == "asset"

    def test_shocks_do_not_stack(self):
        """同一持仓只应用最细的一档，-30 而不是 -30 叠加 -5。"""
        h = [holding("A", industry="白酒")]
        out = run_scenario(h, {"A": 1.0}, market_pct=-5, industry_pct={"白酒": -30})
        assert out["pnl_pct"] == pytest.approx(-30.0)

    def test_asset_type_matched_for_crypto(self):
        h = [holding("BTC", category="equity", asset_type="crypto")]
        out = run_scenario(h, {"BTC": 1.0}, market_pct=0, category_pct={"crypto": -40})
        assert out["holdings"][0]["shock_pct"] == -40
        assert out["holdings"][0]["matched_level"] == "asset_type"


class TestOutput:
    def test_worst_contributors_sorted_by_loss(self):
        h = [holding("A", industry="X"), holding("B", industry="Y")]
        out = run_scenario(h, {"A": 1.0, "B": 1.0},
                           industry_pct={"X": -5, "Y": -40})
        assert out["worst_contributors"][0]["fund_code"] == "B"

    def test_positive_shock_gives_gain(self):
        out = run_scenario([holding("A")], {"A": 1.0}, market_pct=15)
        assert out["pnl"] > 0

    def test_empty_portfolio_errors(self):
        assert "error" in run_scenario([], {}, market_pct=-10)

    def test_carries_assumption_disclaimer(self):
        out = run_scenario([holding("A")], {"A": 1.0}, market_pct=-10)
        assert "不是对未来的预测" in out["assumption"]
        assert "不叠加" in out["assumption"]


class TestPresets:
    def test_all_presets_runnable(self):
        h = [holding("A"), holding("B", category="bond")]
        for key in PRESET_SCENARIOS:
            out = run_preset(h, {"A": 1.0, "B": 1.0}, key)
            assert "error" not in out, key
            assert out["scenario_key"] == key

    def test_unknown_preset_lists_available(self):
        out = run_preset([holding("A")], {"A": 1.0}, "nope")
        assert "error" in out and "market_crash_10" in out["available"]

    def test_run_all_sorted_worst_first(self):
        h = [holding("A")]
        out = run_all_presets(h, {"A": 1.0})
        pnls = [s["pnl"] for s in out["scenarios"]]
        assert pnls == sorted(pnls)
        assert out["most_damaging"]["pnl"] == pnls[0]

    def test_crash_20_worse_than_crash_10(self):
        h = [holding("A")]
        out = {s["scenario_key"]: s["pnl"] for s in run_all_presets(h, {"A": 1.0})["scenarios"]}
        assert out["market_crash_20"] < out["market_crash_10"]

    def test_bond_only_portfolio_barely_hurt_by_equity_crash(self):
        h = [holding("A", category="bond")]
        out = run_preset(h, {"A": 1.0}, "market_crash_20")
        assert out["pnl_pct"] == pytest.approx(-3.0)
