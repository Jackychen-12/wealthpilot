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
from wealthpilot.services.ai_client import json_mode
from wealthpilot.services.evidence import brief
from wealthpilot.settings import get_settings

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

# 操作类措辞 + 紧跟的数字 —— 未完成风险测评时不允许出现
_ACTION_NUMBER_RE = re.compile(
    r"(加仓|减仓|买入|卖出|建仓|清仓|止损|止盈|仓位)[^。；\n]{0,12}?(\d+(?:\.\d+)?)\s*(%|％|元|成)"
)


# 确定性的涨跌预测与目标价 —— 研究只陈述事实和推断，不做这类承诺
_FORECAST_RE = re.compile(r"目标价|必涨|必然上涨|一定会涨|肯定会涨|稳赚|保证收益|将涨到|会涨到|翻倍在即")
# 建议模式下允许给目标价和方向判断，但"保证"类承诺任何时候都不行
_GUARANTEE_RE = re.compile(r"必涨|必然上涨|一定会涨|肯定会涨|稳赚|保证收益|翻倍在即")
# "券商给出的目标价"是在转述别人的观点，不是我们自己给目标价
_ATTRIBUTED_RE = re.compile(r"(券商|卖方|机构|研报|分析师|一致预期)[^。；\n]{0,14}$")
_NEGATION_RE = re.compile(r"(不|无|没有|未|非|避免|拒绝|不会|不得|不应)[^，。；\n]{0,8}$")
_FINANCIAL_RE = re.compile(r"营收|营业收入|净利润|ROE|毛利率|净利率|每股收益")
_PERIOD_RE = re.compile(r"\d{4}[-/年]\d{1,2}|年报|中报|半年报|季报|一季|三季|前三季|上半年|报告期")


@dataclass
class Verdict:
    """一次校验的结论。passed=False 时 issues 非空，调用方据此决定重试。"""

    passed: bool
    issues: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    ungrounded_numbers: list[str] = field(default_factory=list)
    grounding_rate: float = 1.0
    review_complete: bool = True

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
        for e in r.evidence:
            # 审核只判断"要求的证据有没有取到"，看压缩后的就够了；完整内容留给代码做数字核对
            flag = "" if e.get("status", "ok") == "ok" else "（未取到数据）"
            lines.append(f"  证据{flag} {brief(e, 500)}")
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
        if not any(e.get("status", "ok") == "ok" for r in results for e in r.evidence):
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
                model=self.model, max_tokens=4000, system=system,
                messages=[{"role": "user", "content": user}],
                **json_mode(self.client),
            )
            match = re.search(r"\{.*\}", out.text.strip(), re.DOTALL)
            if not match:
                raise ValueError("审核结果不是 JSON")
            data = json.loads(match.group())
            if not isinstance(data.get("missing"), list):
                raise ValueError("审核缺少 missing 列表")
            missing = data["missing"]
            missing = [str(m) for m in missing if str(m).strip()][:4]
        except Exception:
            return Verdict(passed=True, issues=["证据审核未完成"], missing_evidence=list(success_criteria), review_complete=False)

        if not missing:
            return Verdict(passed=True)
        return Verdict(
            passed=False,
            issues=[f"证据不足：{m}" for m in missing],
            missing_evidence=missing,
        )

    # ── 闸门 B：输出是否可信、是否越过画像约束 ─────────────────
    def review_answer(self, answer: str, results: list[AgentResult], question: str = "",
                      context: str = "", sections: list[str] | None = None) -> Verdict:
        """纯代码判定，不消耗 token。

        question 用于识别"用户自己提出的规则参数"；context 是系统交给模型的持仓快照
        （代码、份额、成本、最新价、收益率），模型转述其中的数字同样不算编造。
        """
        issues: list[str] = []

        grounding = check_numeric_grounding(answer, results)
        # 用户在问题里自己给出的数字（规则参数、金额）复述出来不算编造
        asked = {float(m.group()) for m in re.finditer(r"\d+(?:\.\d+)?", f"{question} {context}")}
        if self.profile is not None:
            # 画像里的约束值（期限、回撤容忍度、储备金）是系统给模型的前提，转述它们不算编造
            p = self.profile
            asked |= {float(v) for v in (
                p.risk_level, p.horizon_months, round(p.max_drawdown_tolerance * 100, 2),
                p.liquidity_reserve, p.experience_years, getattr(p, "available_cash", None),
            ) if v is not None}
        if asked and grounding["ungrounded"]:
            grounding["ungrounded"] = [n for n in grounding["ungrounded"] if abs(float(n)) not in asked]
        # 画像存在时，动作幅度是用户提出的目标而非行情事实；其是否可执行由
        # check_profile_constraint 的结构化结果校验，避免把动作数字误当成行情数字。
        if self.profile is not None and _ACTION_NUMBER_RE.search(answer):
            grounding["ungrounded"] = [n for n in grounding["ungrounded"]
                                        if not re.search(rf"(?:加仓|减仓|买入|卖出|建仓|清仓|止损|止盈|仓位)[^。；\n]{{0,12}}{re.escape(n)}", answer)]
            grounding["grounded"] = grounding["total"] - len(grounding["ungrounded"])
            grounding["rate"] = grounding["grounded"] / grounding["total"] if grounding["total"] else 1.0
        if grounding["ungrounded"]:
            nums = "、".join(grounding["ungrounded"][:6])
            issues.append(f"以下数字未出现在工具返回中，可能是编造的：{nums}")

        issues.extend(self._check_profile_constraints(answer, question, results))
        issues.extend(self._check_research_rules(answer, sections or []))
        available = {e["id"] for r in results for e in r.evidence if e.get("id") and e.get("status", "ok") == "ok"}
        # 引用一条"没取到数据"的证据来说明缺口是正当的；只有凭空捏造的 ID 才算违规
        known = {e["id"] for r in results for e in r.evidence if e.get("id")}
        cited = set(re.findall(r"\[(E-[a-f0-9]+)\]", answer))
        if cited - known:
            issues.append("回答引用了不存在的证据 ID：" + "、".join(sorted(cited - known)))
        if available and not cited:
            issues.append("回答必须引用具体证据 ID")

        return Verdict(
            passed=not issues,
            issues=issues,
            ungrounded_numbers=grounding["ungrounded"],
            grounding_rate=grounding["rate"],
        )

    def _check_profile_constraints(
        self, answer: str, question: str = "", results: list[AgentResult] | None = None
    ) -> list[str]:
        issues: list[str] = []

        if self.profile is None:
            # 复述用户自己提出的规则参数、或转述回测工具算出的结果，不是在给仓位建议
            described = {m.group() for m in re.finditer(r"\d+(?:\.\d+)?", question)}
            for r in results or []:
                for e in r.evidence:
                    if e.get("tool") == "backtest_rule" and e.get("status", "ok") == "ok":
                        described |= {str(abs(float(m.group()))).rstrip("0").rstrip(".") for m in
                                      re.finditer(r"\d+(?:\.\d+)?", f"{e.get('input')} {e['output']}")}
            hits = [h for h in _ACTION_NUMBER_RE.findall(answer)
                    if h[1] not in described and h[1].rstrip("0").rstrip(".") not in described]
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
                if re.search(r"建议|可以|考虑|配置|加仓|买入|增持", context) and not re.search(r"不建议|不得|不应|避免|不要|不配置", context):
                    issues.append(f"用户已排除「{industry}」行业，但回答中建议配置：{context.strip()}")

        return issues

    @staticmethod
    def _check_research_rules(answer: str, sections: list[str]) -> list[str]:
        """研究类回答的三条硬规则：章节完整、财务数字带报告期、不做确定性预测。"""
        issues: list[str] = []

        if sections:
            headings = " ".join(line for line in answer.splitlines() if line.lstrip().startswith("#"))
            missing = [s for s in sections if s not in headings]
            if missing:
                issues.append("回答缺少必须的章节（需作为标题出现）：" + "、".join(missing))

        # 财报是滞后数据：只要引用了财务指标，全文就必须交代过是哪一期的
        if _FINANCIAL_RE.search(answer) and re.search(r"\d", answer) and not _PERIOD_RE.search(answer):
            issues.append("引用了财务数据但没有写明报告期，读者无法判断数据的时点")

        advice = getattr(get_settings(), "advice_mode", False)
        for match in (_GUARANTEE_RE if advice else _FORECAST_RE).finditer(answer):
            before = answer[max(0, match.start() - 12):match.start()]
            if match.group() == "目标价" and _ATTRIBUTED_RE.search(answer[max(0, match.start() - 18):match.start()]):
                continue
            if not _NEGATION_RE.search(before):
                issues.append(f"出现了对收益的承诺（“{match.group()}”），建议可以给，但不能保证结果" if advice else
                              f"出现了目标价或确定性的涨跌预测（“{match.group()}”），研究只能陈述事实与推断")
                break
        if advice and "建议" in (sections or []) and "失效" not in answer:
            issues.append("给出了建议但没有写明失效条件（什么情况下这条建议不再成立）")
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
