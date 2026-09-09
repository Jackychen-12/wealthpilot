"""Critic 双闸门测试。

闸门 B（输出合规性）全是纯代码判定，可以完整覆盖；
闸门 A（证据充分性）依赖 LLM，这里只测它的降级与短路行为 —— 语义判断本身
不适合用单测钉死，属于评估集该管的范围。
"""

from datetime import datetime, timedelta

import pytest

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.critic_agent import (
    CriticAgent,
    Verdict,
    rewrite_instruction,
)


def result(output: str = "", text: str = "", tool: str = "get_x") -> AgentResult:
    evidence = [{"tool": tool, "input": {}, "output": output}] if output else []
    return AgentResult("risk", "goal", text, evidence)


def profile(**kw) -> InvestorProfile:
    defaults = dict(
        user_id=1, risk_level=2, horizon_months=36,
        max_drawdown_tolerance=0.15, liquidity_reserve=0.0,
        experience_years=3.0, excluded_industries="白酒,房地产",
    )
    defaults.update(kw)
    return InvestorProfile(**defaults)


class _StubClient:
    """按预设文本响应的假 client，用于闸门 A。"""

    def __init__(self, text: str = "", raise_exc: bool = False):
        self.text = text
        self.raise_exc = raise_exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("LLM 挂了")
        return type("R", (), {"text": self.text})()


# ══════════════════════════════════════════════════════════
# 闸门 B：数值溯源
# ══════════════════════════════════════════════════════════

class TestAnswerGrounding:
    def test_grounded_answer_passes(self):
        c = CriticAgent(_StubClient(), "m", profile())
        v = c.review_answer("最大回撤 18.62%，恢复用了 47 天。", [result("最大回撤 -18.62%，恢复 47 天")])
        assert v.passed
        assert v.grounding_rate == 1.0

    def test_invented_number_is_rejected(self):
        c = CriticAgent(_StubClient(), "m", profile())
        v = c.review_answer("净值 1.5983，预计涨到 1.8500。", [result("最新净值 1.5983")])
        assert not v.passed
        assert "1.8500" in v.ungrounded_numbers
        assert any("编造" in i for i in v.issues)

    def test_sign_difference_is_not_a_violation(self):
        """工具返回 -18.62（回撤），正文写 18.62% —— 同一个数。"""
        c = CriticAgent(_StubClient(), "m", profile())
        assert c.review_answer("回撤 18.62%", [result("最大回撤 -18.62%")]).passed


# ══════════════════════════════════════════════════════════
# 闸门 B：画像约束
# ══════════════════════════════════════════════════════════

class TestProfileConstraints:
    def test_no_profile_blocks_position_advice(self):
        c = CriticAgent(_StubClient(), "m", None)
        v = c.review_answer("建议加仓 3% 到该基金。", [result("净值 3")])
        assert not v.passed
        assert any("风险测评" in i for i in v.issues)

    @pytest.mark.parametrize("text", [
        "建议减仓 5%", "止损 12%", "仓位控制在 30%", "买入 2 成",
    ])
    def test_various_action_phrasings_caught(self, text):
        c = CriticAgent(_StubClient(), "m", None)
        assert not c.review_answer(text, [result("x")]).passed

    def test_no_profile_allows_pure_analysis(self):
        """没有画像时不是什么都不能说，只是不能给具体仓位。"""
        c = CriticAgent(_StubClient(), "m", None)
        v = c.review_answer(
            "该基金近 30 天下跌，主要受上游价格影响。当前无法判断是否已见底。",
            [result("近30天 -5%")],
        )
        assert v.passed

    def test_excluded_industry_recommendation_rejected(self):
        c = CriticAgent(_StubClient(), "m", profile())
        v = c.review_answer("可以考虑配置白酒板块作为分散。", [result("x")])
        assert not v.passed
        assert any("白酒" in i for i in v.issues)

    def test_merely_mentioning_excluded_industry_is_fine(self):
        """用户排除白酒，不代表不能提到它 —— 只有建议配置才算违规。"""
        c = CriticAgent(_StubClient(), "m", profile())
        v = c.review_answer("本周白酒板块整体下跌，但与你的持仓无关。", [result("x")])
        assert v.passed

    def test_profile_present_allows_position_advice(self):
        c = CriticAgent(_StubClient(), "m", profile())
        assert c.review_answer("建议减仓 5%", [result("持仓占比 45%")]).passed


# ══════════════════════════════════════════════════════════
# 闸门 A：证据充分性
# ══════════════════════════════════════════════════════════

class TestEvidenceGate:
    def test_no_criteria_short_circuits(self):
        client = _StubClient('{"missing":[]}')
        c = CriticAgent(client, "m", None)
        assert c.review_evidence("q", [], [result("x")]).passed
        assert client.calls == 0, "没有 criteria 时不该调用 LLM"

    def test_empty_evidence_fails_without_llm(self):
        client = _StubClient('{"missing":[]}')
        c = CriticAgent(client, "m", None)
        v = c.review_evidence("q", ["需要当前仓位"], [result()])
        assert not v.passed
        assert client.calls == 0, "一条证据都没有时不必问 LLM"

    def test_missing_criteria_detected(self):
        c = CriticAgent(_StubClient('{"missing":["需要回撤数据"]}'), "m", None)
        v = c.review_evidence("q", ["需要当前仓位", "需要回撤数据"], [result("仓位 45%")])
        assert not v.passed
        assert v.missing_evidence == ["需要回撤数据"]

    def test_all_covered_passes(self):
        c = CriticAgent(_StubClient('{"missing":[]}'), "m", None)
        assert c.review_evidence("q", ["需要当前仓位"], [result("仓位 45%")]).passed

    def test_llm_failure_fails_open(self):
        """Critic 不能变成新的单点故障。"""
        c = CriticAgent(_StubClient(raise_exc=True), "m", None)
        assert c.review_evidence("q", ["需要当前仓位"], [result("仓位 45%")]).passed

    def test_garbage_response_fails_open(self):
        c = CriticAgent(_StubClient("这不是 JSON"), "m", None)
        assert c.review_evidence("q", ["需要当前仓位"], [result("仓位 45%")]).passed


# ══════════════════════════════════════════════════════════
# 重写指令与事件
# ══════════════════════════════════════════════════════════

class TestRewriteInstruction:
    def test_lists_every_issue(self):
        v = Verdict(passed=False, issues=["问题一", "问题二"], ungrounded_numbers=["1.85"])
        text = rewrite_instruction(v)
        assert "问题一" in text and "问题二" in text
        assert "未溯源" in text

    def test_discourages_vagueness(self):
        text = rewrite_instruction(Verdict(passed=False, issues=["x"]))
        assert "含糊其辞" in text


class TestVerdictEvent:
    def test_event_shape(self):
        v = Verdict(passed=False, issues=["a"], ungrounded_numbers=["1.5"], grounding_rate=0.5)
        e = v.as_event("answer")
        assert e["type"] == "critic"
        assert e["gate"] == "answer"
        assert e["passed"] is False
        assert e["grounding_rate"] == 0.5

    def test_supplementary_goals(self):
        goals = CriticAgent.supplementary_goals(["需要回撤数据"])
        assert goals == ["补充查证：需要回撤数据"]


class TestStaleProfileStillConstrains:
    def test_expired_profile_is_not_treated_as_missing(self):
        """画像过期只是提示复评，不该退化成"没有画像"从而放宽约束。"""
        p = profile()
        p.updated_at = datetime.now() - timedelta(days=400)
        c = CriticAgent(_StubClient(), "m", p)
        assert c.review_answer("建议减仓 5%", [result("持仓占比 45%")]).passed


class TestRewriteLoop:
    """把「打回 → 带着意见重写 → 通过」这条回路完整跑一遍。

    不驱动真实 orchestrator（那需要 API Key），而是用假 Synthesizer 复现
    orchestrator 里那段循环的控制流，验证契约本身成立：
    不通过就带着 Critic 的意见重来，且在上限内收敛。
    """

    class _FakeSynthesizer:
        """第一版编造数字，收到重写要求后改用证据里的真实数字。"""

        def __init__(self):
            self.calls: list[str] = []

        def run(self, instruction: str = "") -> str:
            self.calls.append(instruction)
            if instruction:
                return "该基金最新净值 1.5983，近期无法判断后续走势。"
            return "该基金最新净值 1.5983，预计将涨到 1.8500。"

    def _loop(self, critic, synth, results, max_rewrites: int):
        instruction, text, verdicts = "", "", []
        for attempt in range(max_rewrites + 1):
            text = synth.run(instruction)
            verdict = critic.review_answer(text, results)
            verdicts.append(verdict)
            if verdict.passed or attempt == max_rewrites:
                break
            instruction = rewrite_instruction(verdict)
        return text, verdicts

    def test_bad_draft_is_rewritten_and_then_passes(self):
        critic = CriticAgent(_StubClient(), "m", profile())
        synth = self._FakeSynthesizer()
        text, verdicts = self._loop(critic, synth, [result("最新净值 1.5983")], max_rewrites=2)

        assert len(synth.calls) == 2, "第一版被打回后应该重写一次"
        assert synth.calls[0] == "", "第一次调用不带重写要求"
        assert "1.8500" in synth.calls[1], "重写要求里要点名那个编造的数字"
        assert verdicts[0].passed is False and verdicts[-1].passed is True
        assert "1.8500" not in text, "最终输出不应再含编造的数字"

    def test_gives_up_after_max_rewrites(self):
        """屡改不过时必须收敛，不能无限重试。"""
        class _Stubborn:
            def run(self, instruction: str = "") -> str:
                return "预计涨到 1.8500。"

        critic = CriticAgent(_StubClient(), "m", profile())
        text, verdicts = self._loop(critic, _Stubborn(), [result("净值 1.5983")], max_rewrites=2)
        assert len(verdicts) == 3, "上限 2 次重写 → 共 3 次尝试"
        assert verdicts[-1].passed is False, "最终仍不通过，但已停止重试"

    def test_good_draft_is_not_rewritten(self):
        critic = CriticAgent(_StubClient(), "m", profile())
        synth = self._FakeSynthesizer()
        # 证据里直接含 1.8500，第一版即合规
        text, verdicts = self._loop(
            critic, synth, [result("最新净值 1.5983，目标位 1.8500")], max_rewrites=2
        )
        assert len(synth.calls) == 1, "合规的草稿不该触发重写"
        assert verdicts[0].passed
