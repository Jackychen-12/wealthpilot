"""SynthesizerAgent — 把多个专业 Agent 的结果整合成一份回答。

并行执行带来一个新问题：三个 Agent 各自输出一段文字，直接拼起来是三段互不相干、
甚至互相矛盾的内容。Synthesizer 负责跨 Agent 整合、消解冲突，并在给出仓位或操作
建议前对照用户风险画像做一次约束检查。

单任务的简单问题不走这里 —— orchestrator 会让那个 Agent 直接流式输出，避免多一跳延迟。
"""

from __future__ import annotations

import json
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

# 符号前不能紧挨数字，否则 "09-30" 会被读成 -30
_NUMBER_RE = re.compile(r"(?<![\d.])[+-]?\d+(?:\.\d+)?")
# 日期不是待溯源的数值：2026-09-30 / 2026/9/30 / 09-30 / 9/30 / 9月30日
_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|(?<!\d)\d{1,2}[-/]\d{1,2}(?![\d.%])|\d{1,2}月\d{1,2}日")
# 指数名里的数字是名字的一部分（沪深300、中证500）
_INDEX_NAME_RE = re.compile(r"(沪深|中证|上证|深证|国证|标普|纳指|纳斯达克|恒生|科创|创业板|MSCI\s?)\d+")
_LOSS_RE = re.compile(r"回撤|跌|亏|损失|回落|下降|减少|缩水")


def _evidence_text(e: dict) -> str:
    """一条证据里可被引用的全部文本 —— 入参也算（基金代码、查询天数都来自入参）。"""
    return f"{json.dumps(e.get('input', {}), ensure_ascii=False)} {e['output']}"


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
        *,
        stream_output: bool = True,
        extra_instruction: str = "",
    ) -> str:
        """整合各 Agent 结果。

        Args:
            stream_output: True 时边生成边发 `delta`。Critic 开启时必须传 False ——
                否则未经校验的草稿已经流到用户面前，"打回重写"就无从谈起。
            extra_instruction: Critic 的重写要求，追加在证据之后。
        """
        settings = get_settings()
        system = build_synthesizer_prompt(self.profile, success_criteria)
        user_content = self._build_evidence_block(question, results)
        if extra_instruction:
            user_content += f"\n\n{extra_instruction}"

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
                    if stream_output:
                        await emit({"type": "delta", "content": payload})
                elif kind == "error":
                    stream_error = payload
            if stream_error is not None:
                raise stream_error
        except Exception as e:  # noqa: BLE001
            await emit({"type": "error", "content": f"synthesizer 异常: {e}"})
            # 退化：直接拼接各 Agent 结果，保证用户至少拿得到内容
            final_text = self._fallback_merge(results)
            if stream_output:
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
                    parts.append(f"- [{e.get('id', 'legacy')}] {e['tool']}({e['input']}) → {e['output']}\n元数据：{e.get('provenance', {})}")
            if r.text.strip():
                parts.append(f"该 Agent 的初步结论：{r.text.strip()}")
        return "\n".join(parts)

    @staticmethod
    def _fallback_merge(results: list[AgentResult]) -> str:
        chunks = [r.text.strip() for r in results if r.text.strip()]
        return "\n\n".join(chunks) if chunks else "本轮未能收集到足够信息，请换个问法再试。"


_UNIT_RE = re.compile(r"\s*(%|％|元|天|个月|年|成|份)")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _unit_after(text: str, end: int) -> str:
    m = _UNIT_RE.match(text, end)
    return m.group(1).replace("％", "%") if m else ""


def _same_value(token: str, target: float) -> bool:
    """正文数字是否等于 target 按正文的小数位四舍五入后的值（-0.117 写成 -0.12 算同一个数）。"""
    decimals = len(token.split(".")[1]) if "." in token else 0
    return abs(float(token) - target) <= 0.5 * 10 ** -decimals + 1e-9


def check_numeric_grounding(answer: str, results: list[AgentResult]) -> dict:
    """数值溯源检查：答案里出现的数字是否都能在工具返回中找到。

    纯代码检查，不消耗 token。给交易指令的系统里，"LLM 自己编了一个数字" 是最
    致命的失效模式，这个函数把它变成一个可以观测、可以进 CI 的指标。

    对照范围是本轮全部可用证据（含工具入参），而不只是该行引用的那条 —— 一行里
    常会顺带提到别的证据里的数。要防的是凭空编造，不是引用标错了行。
    模型对数字做的三种"换写法"不算编造：四舍五入（-0.117 → -0.12）、
    小数转百分比（权重 0.1619 → 16.19%）、千分位（8348.4 → 8,348.4）。

    返回 {"total": n, "grounded": n, "ungrounded": [...], "rate": 0.0-1.0}
    """
    records = [e for r in results for e in r.evidence if e.get("status", "ok") == "ok"]
    corpus = _THOUSANDS_RE.sub("", _DATE_RE.sub(" ", " ".join(_evidence_text(e) for e in records)))
    # (数值, 单位, 前文是否提到回撤)
    sources = [
        (float(m.group()), _unit_after(corpus, m.end()),
         bool(re.search(r"回撤|drawdown", corpus[max(0, m.start() - 24):m.start()])))
        for m in _NUMBER_RE.finditer(corpus)
    ]

    ungrounded = []
    total = 0
    for line in answer.splitlines():
        clean = re.sub(r"\[E-[a-f0-9]+\]", "", line)
        clean = re.sub(r"^\s*\d+[.)、]\s*", "", clean)
        clean = _THOUSANDS_RE.sub("", _INDEX_NAME_RE.sub(" ", _DATE_RE.sub(" ", clean)))
        for match in _NUMBER_RE.finditer(clean):
            token = match.group()
            unit = _unit_after(clean, match.end())
            if not unit and not _is_meaningful(token):
                continue
            if unit in ("年", "个月") or (unit == "" and 1900 <= abs(float(token)) <= 2100):
                continue
            total += 1
            before = clean[max(0, match.start() - 12):match.start()]
            unsigned = token[0] not in "+-"
            # "下跌 4.47%" 对应源数据 -4.47：正文用文字表达了方向，数值不带符号
            loss = unsigned and bool(_LOSS_RE.search(before))
            for value, source_unit, source_drawdown in sources:
                # 回撤幅度写成 11.75% 还是 -11.75% 是同一个事实；收益率等指标必须保留符号
                if source_drawdown:
                    targets = [value, -value]
                elif loss and value < 0:
                    targets = [value, abs(value)]
                else:
                    targets = [value]
                if unit == "%" and not source_unit and abs(value) <= 1:
                    # 工具用小数表示占比，正文写成百分比
                    targets += [t * 100 for t in targets]
                elif unit and source_unit and unit != source_unit:
                    continue
                if any(_same_value(token, t) for t in targets):
                    break
            else:
                ungrounded.append(token)
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
        value = float(token)
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
