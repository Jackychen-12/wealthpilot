"""投资者画像测试 —— 画像是仓位建议的硬约束来源，必须真的进到 prompt 里。"""

from datetime import datetime, timedelta

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.prompts import (
    build_planner_prompt,
    build_portfolio_prompt,
    build_profile_context,
    build_risk_prompt,
    build_synthesizer_prompt,
)


def make_profile(**kw) -> InvestorProfile:
    defaults = dict(
        user_id=1,
        risk_level=2,
        horizon_months=36,
        max_drawdown_tolerance=0.15,
        liquidity_reserve=50000.0,
        experience_years=3.0,
        excluded_industries="白酒,房地产",
    )
    defaults.update(kw)
    return InvestorProfile(**defaults)


class TestProfileModel:
    def test_risk_label(self):
        assert make_profile(risk_level=1).risk_label == "保守型"
        assert make_profile(risk_level=4).risk_label == "激进型"

    def test_excluded_list_parsing(self):
        assert make_profile().excluded_list == ["白酒", "房地产"]

    def test_empty_excluded(self):
        assert make_profile(excluded_industries="").excluded_list == []

    def test_fresh_profile_not_stale(self):
        assert make_profile().is_stale() is False

    def test_old_profile_is_stale(self):
        p = make_profile()
        p.updated_at = datetime.now() - timedelta(days=200)
        assert p.is_stale() is True


class TestProfileContext:
    def test_missing_profile_blocks_position_advice(self):
        ctx = build_profile_context(None)
        assert "尚未完成风险测评" in ctx
        assert "不得给出具体仓位比例" in ctx

    def test_context_contains_hard_constraints(self):
        ctx = build_profile_context(make_profile())
        assert "15%" in ctx           # 最大回撤容忍度
        assert "36 个月" in ctx        # 投资期限
        assert "50000" in ctx         # 流动性储备
        assert "白酒" in ctx           # 排除行业
        assert "硬约束" in ctx

    def test_stale_profile_flagged(self):
        p = make_profile()
        p.updated_at = datetime.now() - timedelta(days=200)
        assert "复评" in build_profile_context(p)


class TestProfileInjection:
    """回归测试：画像必须出现在每一个会给建议的 prompt 里。"""

    def test_injected_into_portfolio_prompt(self):
        prompt = build_portfolio_prompt([], {}, make_profile())
        assert "最大回撤容忍度" in prompt
        assert "白酒" in prompt

    def test_injected_into_risk_prompt(self):
        assert "最大回撤容忍度" in build_risk_prompt([], {}, make_profile())

    def test_injected_into_planner_prompt(self):
        assert "最大回撤容忍度" in build_planner_prompt(make_profile())

    def test_injected_into_synthesizer_prompt(self):
        assert "最大回撤容忍度" in build_synthesizer_prompt(make_profile(), [])

    def test_prompts_work_without_profile(self):
        for prompt in (
            build_portfolio_prompt([], {}, None),
            build_risk_prompt([], {}, None),
            build_planner_prompt(None),
            build_synthesizer_prompt(None, []),
        ):
            assert "尚未完成风险测评" in prompt

    def test_synthesizer_carries_success_criteria(self):
        prompt = build_synthesizer_prompt(None, ["需要当前仓位", "需要回撤数据"])
        assert "需要当前仓位" in prompt
        assert "需要回撤数据" in prompt


class TestPlannerPromptRules:
    def test_action_questions_require_risk_task(self):
        """Planner 必须被告知：操作类问题要带 risk 任务。"""
        prompt = build_planner_prompt(None)
        assert "risk 任务" in prompt
        assert "success_criteria" in prompt
