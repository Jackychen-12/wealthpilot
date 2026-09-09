"""规则回测测试。

回测器的价值在于"能不能证伪一条规则"，所以用构造好的净值路径把每种情形
钉死：该触发的触发、不该触发的不触发、基线对比方向正确。
"""

import pytest

from wealthpilot.services.backtest import backtest_rule


def series(navs: list[float], newest_first: bool = False) -> list[dict]:
    """按给定净值构造序列，日期递增。"""
    out = [
        {"nav_date": f"2026-01-{i + 1:02d}", "nav": v}
        for i, v in enumerate(navs)
    ]
    return list(reversed(out)) if newest_first else out


class TestOrdering:
    def test_accepts_newest_first(self):
        """数据源普遍最新在前，回测必须自己纠正顺序。"""
        asc = backtest_rule(series([100, 90]), [{"drawdown_pct": 5, "add_pct": 50}])
        desc = backtest_rule(series([100, 90], newest_first=True),
                             [{"drawdown_pct": 5, "add_pct": 50}])
        assert asc["period"]["start"] == desc["period"]["start"] == "2026-01-01"

    def test_too_short_returns_error(self):
        assert "error" in backtest_rule(series([100]), [{"drawdown_pct": 5, "add_pct": 50}])


class TestTriggers:
    def test_fires_when_drawdown_reached(self):
        out = backtest_rule(series([100, 94]), [{"drawdown_pct": 5, "add_pct": 50}])
        assert out["strategy"]["trigger_count"] == 1
        assert out["strategy"]["events"][0]["drawdown_pct"] == pytest.approx(6.0)

    def test_does_not_fire_below_threshold(self):
        out = backtest_rule(series([100, 97]), [{"drawdown_pct": 5, "add_pct": 50}])
        assert out["strategy"]["trigger_count"] == 0
        assert out["strategy"]["deployed_pct"] == 0

    def test_each_tier_fires_once(self):
        """同一档不能在持续下跌中反复触发。"""
        out = backtest_rule(
            series([100, 94, 93, 92, 91]), [{"drawdown_pct": 5, "add_pct": 30}]
        )
        assert out["strategy"]["trigger_count"] == 1

    def test_multiple_tiers_fire_in_order(self):
        out = backtest_rule(
            series([100, 94, 91, 87]),
            [{"drawdown_pct": 5, "add_pct": 20}, {"drawdown_pct": 12, "add_pct": 20}],
        )
        assert out["strategy"]["trigger_count"] == 2
        assert out["strategy"]["deployed_pct"] == pytest.approx(40.0)

    def test_respects_max_position(self):
        out = backtest_rule(
            series([100, 94, 87]),
            [{"drawdown_pct": 5, "add_pct": 40}, {"drawdown_pct": 12, "add_pct": 40}],
            max_position_pct=50,
        )
        assert out["strategy"]["deployed_pct"] <= 50.0

    def test_peak_resets_drawdown(self):
        """创新高之后，回调应从新高点重新计算。"""
        out = backtest_rule(
            series([100, 98, 120, 113]), [{"drawdown_pct": 5, "add_pct": 50}]
        )
        # 98 相对 100 只跌 2%，不触发；113 相对 120 跌 5.8%，触发
        assert out["strategy"]["trigger_count"] == 1
        assert out["strategy"]["events"][0]["nav"] == pytest.approx(113.0)


class TestStopLoss:
    def test_stop_loss_clears_position(self):
        out = backtest_rule(
            series([100, 94, 70]),
            [{"drawdown_pct": 5, "add_pct": 100}],
            stop_loss_pct=15,
        )
        actions = [e["action"] for e in out["strategy"]["events"]]
        assert "stop_loss" in actions

    def test_no_stop_loss_when_not_configured(self):
        out = backtest_rule(series([100, 94, 70]), [{"drawdown_pct": 5, "add_pct": 100}])
        assert all(e["action"] != "stop_loss" for e in out["strategy"]["events"])

    def test_stop_loss_not_triggered_above_threshold(self):
        out = backtest_rule(
            series([100, 94, 92]),
            [{"drawdown_pct": 5, "add_pct": 100}],
            stop_loss_pct=15,
        )
        assert all(e["action"] != "stop_loss" for e in out["strategy"]["events"])


class TestBaselines:
    def test_lump_sum_tracks_price(self):
        """一次性买入的收益就是净值涨幅。"""
        out = backtest_rule(series([100, 120]), [{"drawdown_pct": 50, "add_pct": 100}])
        assert out["baseline_lump_sum"]["total_return_pct"] == pytest.approx(20.0)

    def test_strategy_beats_lump_sum_when_buying_the_dip(self):
        """先跌后涨的路径里，抄底策略应优于一次性买在高点。"""
        out = backtest_rule(
            series([100, 80, 100]), [{"drawdown_pct": 15, "add_pct": 100}]
        )
        assert out["excess_vs_lump_sum_pct"] > 0

    def test_strategy_underperforms_in_straight_up_market(self):
        """单边上涨里，一直等回调的策略必然跑输 —— 回测要能显示这一点。"""
        out = backtest_rule(
            series([100, 110, 120, 130]), [{"drawdown_pct": 10, "add_pct": 100}]
        )
        assert out["strategy"]["trigger_count"] == 0
        assert out["excess_vs_lump_sum_pct"] < 0

    def test_dca_baseline_present(self):
        out = backtest_rule(series([100] * 60), [{"drawdown_pct": 5, "add_pct": 50}])
        assert out["baseline_dca"]["installments"] >= 1


class TestMetrics:
    def test_max_drawdown_of_equity_curve(self):
        """买入之后继续下跌才会产生权益回撤。"""
        out = backtest_rule(series([100, 94, 60]), [{"drawdown_pct": 5, "add_pct": 100}])
        assert out["strategy"]["max_drawdown_pct"] > 30

    def test_buying_at_the_bottom_creates_no_equity_drawdown(self):
        """在最低点一次性买入，权益曲线不会因这笔买入而回撤 ——
        净值回撤和权益回撤是两件事，回测报的是后者。"""
        out = backtest_rule(series([100, 50]), [{"drawdown_pct": 5, "add_pct": 100}])
        assert out["strategy"]["trigger_count"] == 1
        assert out["strategy"]["max_drawdown_pct"] == 0.0

    def test_flat_market_zero_return(self):
        out = backtest_rule(series([100] * 10), [{"drawdown_pct": 5, "add_pct": 100}])
        assert out["strategy"]["total_return_pct"] == pytest.approx(0.0)

    def test_period_reported(self):
        out = backtest_rule(series([100, 90, 95]), [{"drawdown_pct": 5, "add_pct": 50}])
        assert out["period"]["trading_days"] == 3
        assert out["period"]["end"] == "2026-01-03"

    def test_limitations_always_present(self):
        """回测结论不能脱离样本区间与成本假设单独呈现。"""
        out = backtest_rule(series([100, 90]), [{"drawdown_pct": 5, "add_pct": 50}])
        assert "不计申赎费" in out["limitations"]
        assert "历史表现不代表未来" in out["limitations"]
