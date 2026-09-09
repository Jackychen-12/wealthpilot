"""SynthesizerAgent — 把多个专业 Agent 的结果整合成一份回答。

并行执行带来一个新问题：三个 Agent 各自输出一段文字，直接拼起来是三段互不相干、
甚至互相矛盾的内容。Synthesizer 负责跨 Agent 整合、消解冲突，并在给出仓位或操作
建议前对照用户风险画像做一次约束检查。

单任务的简单问题不走这里 —— orchestrator 会让那个 Agent 直接流式输出，避免多一跳延迟。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.prompts import build_synthesizer_prompt
from wealthpilot.services.agents.streaming import stream_sync_in_thread
from wealthpilot.settings import get_settings

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

Emit = Callable[[dict], Awaitable[None]]

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class SynthesizerAgent:
    def __init__(self, client: AIClient, model: str, profile: InvestorProfile | None = None):
        self.client = client
        self.model = model
        self.profile = profile

    async def run(
        self,
        question: str,
        results: list[AgentResult],
        success_criteria: list[str],
        emit: Emit,
    ) -> str:
        settings = get_settings()
        system = build_synthesizer_prompt(self.profile, success_criteria)
        user_content = self._build_evidence_block(question, results)

        final_text = ""
        stream_error: Exception | None = None

        def make_stream():
            return self.client.stream(
                model=self.model,
                max_tokens=settings.agent_max_tokens,
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": user_content}],
            )

        try:
            async for kind, payload in stream_sync_in_thread(make_stream):
                if kind == "delta":
                    final_text += payload
                    await emit({"type": "delta", "content": payload})
                elif kind == "error":
                    stream_error = payload
            if stream_error is not None:
                raise stream_error
        except Exception as e:  # noqa: BLE001
            await emit({"type": "error", "content": f"synthesizer 异常: {e}"})
            # 退化：直接拼接各 Agent 结果，保证用户至少拿得到内容
            final_text = self._fallback_merge(results)
            await emit({"type": "delta", "content": final_text})

        return final_text

    @staticmethod
    def _build_evidence_block(question: str, results: list[AgentResult]) -> str:
        parts = [f"用户问题：{question}\n", "以下是各专业 Agent 收集到的证据：\n"]
        for r in results:
            parts.append(f"\n### [{r.agent}] {r.goal or '（无显式目标）'}")
            if r.evidence:
                parts.append("工具返回原始数据：")
                for e in r.evidence:
                    parts.append(f"- {e['tool']}({e['input']}) → {e['output']}")
            if r.text.strip():
                parts.append(f"该 Agent 的初步结论：{r.text.strip()}")
        return "\n".join(parts)

    @staticmethod
    def _fallback_merge(results: list[AgentResult]) -> str:
        chunks = [r.text.strip() for r in results if r.text.strip()]
        return "\n\n".join(chunks) if chunks else "本轮未能收集到足够信息，请换个问法再试。"


def check_numeric_grounding(answer: str, results: list[AgentResult]) -> dict:
    """数值溯源检查：答案里出现的数字是否都能在工具返回中找到。

    纯代码检查，不消耗 token。给交易指令的系统里，"LLM 自己编了一个数字" 是最
    致命的失效模式，这个函数把它变成一个可以观测、可以进 CI 的指标。

    返回 {"total": n, "grounded": n, "ungrounded": [...], "rate": 0.0-1.0}
    """
    corpus = " ".join(str(e["output"]) for r in results for e in r.evidence)
    corpus_numbers = {_normalize(n) for n in _NUMBER_RE.findall(corpus)}
    corpus_numbers.discard(None)

    # 过滤掉序号、年份、百分比里的小整数等噪声
    candidates = [n for n in _NUMBER_RE.findall(answer) if _is_meaningful(n)]

    ungrounded = [n for n in candidates if _normalize(n) not in corpus_numbers]
    total = len(candidates)
    grounded = total - len(ungrounded)

    return {
        "total": total,
        "grounded": grounded,
        "ungrounded": sorted(set(ungrounded)),
        "rate": (grounded / total) if total else 1.0,
    }


def _normalize(token: str) -> str | None:
    """按绝对值归一化。

    工具返回的回撤是 `-18.62`，而正文里通常写成"回撤 18.62%"；同理 `1.50` 与 `1.5`
    是同一个数。不做归一会把大量真实引用误判成"编造"，指标就没法用了。
    """
    try:
        value = abs(float(token))
    except ValueError:
        return None
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _is_meaningful(token: str) -> bool:
    try:
        value = abs(float(token))
    except ValueError:
        return False
    if "." in token:
        return True
    # 1-12 多是列表序号或月份；1900-2100 多是年份，都不作为溯源对象
    if value <= 12:
        return False
    return not (1900 <= value <= 2100)
