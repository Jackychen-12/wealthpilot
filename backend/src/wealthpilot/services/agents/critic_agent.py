"""CriticAgent — 证据充分性与输出合规性的双重校验。

在此之前，Planner 会声明 success_criteria、Synthesizer 会做数值溯源检查，
但两者都没有"不通过就打回"的回路：criteria 无人核对，溯源只发一条 warning。
结果是"看起来有约束，实际上什么都拦不住"。

这里补上两道闸门：

    Plan → 并行 Execute → [闸门 A 证据充分性] → 不足则补任务重跑
                              ↓ 通过
                          Synthesize → [闸门 B 输出合规性] → 不合规则重写
                                           ↓ 通过
                                        最终回答

闸门 B 全部是纯代码判定，不消耗 token，也因此可以直接作为 CI 指标；
闸门 A 需要语义判断，用一次小额 LLM 调用，失败时 fail-open 放行 ——
Critic 的职责是提高下限，不是制造新的单点故障。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

# 操作类措辞 + 紧跟的数字 —— 未完成风险测评时不允许出现
_ACTION_NUMBER_RE = re.compile(
    r"(加仓|减仓|买入|卖出|建仓|清仓|止损|止盈|仓位)[^。；\n]{0,12}?(\d+(?:\.\d+)?)\s*(%|％|元|成)"
)


@dataclass
class Verdict:
    """一次校验的结论。passed=False 时 issues 非空，调用方据此决定重试。"""

    passed: bool
    issues: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    ungrounded_numbers: list[str] = field(default_factory=list)
    grounding_rate: float = 1.0

    def as_event(self, gate: str) -> dict:
        return {
            "type": "critic",
            "gate": gate,
            "passed": self.passed,
            "issues": self.issues[:6],
            "missing_evidence": self.missing_evidence[:4],
            "ungrounded": self.ungrounded_numbers[:8],
            "grounding_rate": round(self.grounding_rate, 3),
        }


def _build_evidence_digest(results: list[AgentResult]) -> str:
    lines = []
    for r in results:
        tools = "、".join(r.tool_names) or "未调用工具"
        lines.append(f"- [{r.agent}] 目标：{r.goal or '（无）'}；工具：{tools}")
        if r.text.strip():
            lines.append(f"  结论：{r.text.strip()[:220]}")
    return "\n".join(lines) or "（本轮没有收集到任何证据）"


class CriticAgent:
    def __init__(
        self,
        client: AIClient,
        model: str,
        profile: InvestorProfile | None = None,
    ):
        self.client = client
        self.model = model
        self.profile = profile

    # ── 闸门 A：证据是否足以支撑 success_criteria ──────────────
    def review_evidence(
        self, question: str, success_criteria: list[str], results: list[AgentResult]
    ) -> Verdict:
        if not success_criteria:
            return Verdict(passed=True)

        # 一条证据都没有时不必问 LLM
        if not any(r.evidence or r.text.strip() for r in results):
            return Verdict(
                passed=False,
                issues=["本轮没有收集到任何证据"],
                missing_evidence=list(success_criteria),
            )

        system = (
            "你是投研流程的证据审核员。判断已收集的证据能否支撑给定的每一条要求。\n"
            "严格但务实：证据里能直接读到或直接推出的，算覆盖；需要额外查询才能知道的，算未覆盖。\n"
            '只返回 JSON：{"missing":["未被覆盖的要求原文", ...]}\n'
            "全部覆盖时返回 {\"missing\":[]}。"
        )
        user = (
            f"用户问题：{question}\n\n"
            f"必须满足的要求：\n" + "\n".join(f"- {c}" for c in success_criteria) + "\n\n"
            f"已收集的证据：\n{_build_evidence_digest(results)}"
        )

        try:
            out = self.client.create(
                model=self.model, max_tokens=400, system=system,
                messages=[{"role": "user", "content": user}],
            )
            match = re.search(r"\{.*\}", out.text.strip(), re.DOTALL)
            if not match:
                return Verdict(passed=True)
            missing = json.loads(match.group()).get("missing") or []
            missing = [str(m) for m in missing if str(m).strip()][:4]
        except Exception:
            # fail-open：Critic 不该成为新的单点故障
            return Verdict(passed=True)

        if not missing:
            return Verdict(passed=True)
        return Verdict(
            passed=False,
            issues=[f"证据不足：{m}" for m in missing],
            missing_evidence=missing,
        )

    # ── 闸门 B：输出是否可信、是否越过画像约束 ─────────────────
    def review_answer(self, answer: str, results: list[AgentResult]) -> Verdict:
        """纯代码判定，不消耗 token。"""
        issues: list[str] = []

        grounding = check_numeric_grounding(answer, results)
        if grounding["ungrounded"]:
            nums = "、".join(grounding["ungrounded"][:6])
            issues.append(f"以下数字未出现在工具返回中，可能是编造的：{nums}")

        issues.extend(self._check_profile_constraints(answer))

        return Verdict(
            passed=not issues,
            issues=issues,
            ungrounded_numbers=grounding["ungrounded"],
            grounding_rate=grounding["rate"],
        )

    def _check_profile_constraints(self, answer: str) -> list[str]:
        issues: list[str] = []

        if self.profile is None:
            hits = _ACTION_NUMBER_RE.findall(answer)
            if hits:
                sample = "、".join(f"{a}{n}{u}" for a, n, u in hits[:3])
                issues.append(
                    f"用户尚未完成风险测评，不得给出具体仓位或价位，但回答中出现：{sample}"
                )
            return issues

        for industry in self.profile.excluded_list:
            if industry and industry in answer:
                # 只有在建议配置的语境下才算违规，单纯提及不算
                window = re.search(
                    rf"[^。；\n]{{0,30}}{re.escape(industry)}[^。；\n]{{0,30}}", answer
                )
                context = window.group() if window else industry
                if re.search(r"建议|可以|考虑|配置|加仓|买入|增持", context):
                    issues.append(f"用户已排除「{industry}」行业，但回答中建议配置：{context.strip()}")

        return issues

    # ── 由未覆盖项生成补充任务 ────────────────────────────────
    @staticmethod
    def supplementary_goals(missing: list[str]) -> list[str]:
        return [f"补充查证：{m}" for m in missing]


def rewrite_instruction(verdict: Verdict) -> str:
    """把 Critic 的意见转成给 Synthesizer 的重写要求。"""
    lines = ["上一版回答未通过校验，请据以下意见重写："]
    lines += [f"{i + 1}. {issue}" for i, issue in enumerate(verdict.issues)]
    if verdict.ungrounded_numbers:
        lines.append(
            "对于未溯源的数字：要么删除，要么改用工具返回中确实存在的数值，"
            "不要保留任何无法在证据中找到的数字。"
        )
    lines.append("不要为了通过校验而含糊其辞 —— 数据不足就直说缺哪个数据。")
    return "\n".join(lines)
