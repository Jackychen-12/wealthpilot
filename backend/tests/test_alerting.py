"""预警评估、去重与已读测试。"""

from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from wealthpilot.models.alert import Alert
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services import alerting


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def holding(code, shares=100, cost=1.0, name=None, industry=""):
    return PortfolioHolding(
        user_id=1, fund_code=code, fund_name=name or f"基金{code}", shares=shares,
        cost_price=cost, buy_date=date(2026, 1, 1), category="equity", industry=industry,
    )


class TestEvaluate:
    def test_loss_beyond_threshold_alerts(self):
        h = [holding("A", cost=1.0)]
        out = alerting.evaluate_alerts(h, {"A": 0.90}, None, None, 1, -3.0)
        kinds = [a.kind for a in out]
        assert "drawdown" in kinds
        assert out[0].value == pytest.approx(-10.0)

    def test_small_loss_does_not_alert(self):
        out = alerting.evaluate_alerts([holding("A")], {"A": 0.99}, None, None, 1, -3.0)
        assert not [a for a in out if a.kind == "drawdown"]

    def test_severity_scales_with_depth(self):
        mild = alerting.evaluate_alerts([holding("A")], {"A": 0.96}, None, None, 1, -3.0)
        deep = alerting.evaluate_alerts([holding("A")], {"A": 0.50}, None, None, 1, -3.0)
        assert mild[0].severity == "low"
        assert deep[0].severity == "high"

    def test_concentration_alert(self):
        h = [holding("A", shares=900), holding("B", shares=100)]
        out = alerting.evaluate_alerts(h, {"A": 1.0, "B": 1.0}, None, None, 1)
        conc = [a for a in out if a.kind == "concentration"]
        assert conc and conc[0].value == pytest.approx(90.0)

    def test_balanced_portfolio_no_concentration_alert(self):
        h = [holding("A", shares=100), holding("B", shares=100), holding("C", shares=100)]
        out = alerting.evaluate_alerts(h, {"A": 1.0, "B": 1.0, "C": 1.0}, None, None, 1)
        assert not [a for a in out if a.kind == "concentration"]

    def test_no_profile_produces_no_constraint_noise(self):
        """没做测评时不该刷一堆约束预警 —— 引导测评是另一条路径的事。"""
        out = alerting.evaluate_alerts([holding("A")], {"A": 1.0}, None, None, 1)
        assert not [a for a in out if a.kind == "constraint"]

    def test_constraint_violation_alerts(self):
        p = InvestorProfile(user_id=1, max_drawdown_tolerance=0.15,
                            excluded_industries="白酒")
        h = [holding("A", industry="白酒")]
        out = alerting.evaluate_alerts(h, {"A": 1.0}, None, p, 1)
        assert [a for a in out if a.kind == "constraint"]

    def test_empty_portfolio(self):
        assert alerting.evaluate_alerts([], {}, None, None, 1) == []


class TestPersistAndDedup:
    def test_persists_new_alerts(self, db):
        # 单一持仓组合本身就是 100% 集中，所以除了亏损还会有一条集中度预警
        created = alerting.persist_alerts(db, alerting.evaluate_alerts(
            [holding("A")], {"A": 0.9}, None, None, 1, -3.0))
        kinds = sorted(a.kind for a in created)
        assert kinds == ["concentration", "drawdown"]
        assert alerting.unread_count(db, 1) == 2

    def test_second_evaluation_within_cooldown_adds_nothing(self, db):
        """同一条预警每次评估都新增，收件箱几分钟就没法看了。"""
        cands = alerting.evaluate_alerts([holding("A")], {"A": 0.9}, None, None, 1, -3.0)
        alerting.persist_alerts(db, cands)
        before = alerting.unread_count(db, 1)
        again = alerting.persist_alerts(db, cands)
        assert again == []
        assert alerting.unread_count(db, 1) == before

    def test_after_cooldown_alerts_again(self, db):
        cands = alerting.evaluate_alerts([holding("A")], {"A": 0.9}, None, None, 1, -3.0)
        created = alerting.persist_alerts(db, cands)
        for a in created:
            a.created_at = datetime.now() - timedelta(hours=48)
            db.add(a)
        db.commit()
        assert len(alerting.persist_alerts(db, cands, cooldown_hours=12)) == len(created)

    def test_different_funds_are_separate_alerts(self, db):
        """两只标的各自的亏损预警必须分开记，不能被 dedup 合并掉。"""
        h = [holding("A"), holding("B")]
        created = alerting.persist_alerts(db, alerting.evaluate_alerts(
            h, {"A": 0.9, "B": 0.8}, None, None, 1, -3.0))
        drawdowns = sorted(a.fund_code for a in created if a.kind == "drawdown")
        assert drawdowns == ["A", "B"]
        assert len({a.dedup_key for a in created}) == len(created)

    def test_persist_empty_is_noop(self, db):
        assert alerting.persist_alerts(db, []) == []


class TestInboxAndRead:
    def _seed(self, db, n=3):
        for i in range(n):
            db.add(Alert(user_id=1, kind="drawdown", fund_code=f"F{i}",
                         message=f"m{i}", dedup_key=f"1:drawdown:F{i}"))
        db.commit()

    def test_lists_own_only(self, db):
        self._seed(db)
        db.add(Alert(user_id=2, kind="drawdown", message="别人的", dedup_key="2:x"))
        db.commit()
        rows = alerting.list_alerts(db, 1)
        assert len(rows) == 3
        assert all("别人的" != r.message for r in rows)

    def test_unread_filter(self, db):
        self._seed(db)
        alerting.mark_read(db, 1, [alerting.list_alerts(db, 1)[0].id])
        assert len(alerting.list_alerts(db, 1, unread_only=True)) == 2

    def test_mark_all_read(self, db):
        self._seed(db)
        assert alerting.mark_read(db, 1) == 3
        assert alerting.unread_count(db, 1) == 0

    def test_mark_read_is_idempotent(self, db):
        self._seed(db)
        alerting.mark_read(db, 1)
        assert alerting.mark_read(db, 1) == 0

    def test_cannot_mark_others_read(self, db):
        db.add(Alert(user_id=2, kind="drawdown", message="x", dedup_key="2:x"))
        db.commit()
        assert alerting.mark_read(db, 1) == 0
        assert alerting.unread_count(db, 2) == 1


class TestWebhook:
    @pytest.mark.asyncio
    async def test_no_url_reports_reason(self):
        out = await alerting.deliver_webhook("", [Alert(message="x")])
        assert out["delivered"] is False and "未配置" in out["reason"]

    @pytest.mark.asyncio
    async def test_no_alerts_skips_send(self):
        out = await alerting.deliver_webhook("http://example.invalid", [])
        assert out["delivered"] is False and "无新增" in out["reason"]

    @pytest.mark.asyncio
    async def test_unreachable_host_does_not_raise(self):
        """推送失败不应让评估请求整体失败。"""
        out = await alerting.deliver_webhook(
            "http://127.0.0.1:1/hook", [Alert(message="x")], timeout=1.0
        )
        assert out["delivered"] is False and out["reason"]
