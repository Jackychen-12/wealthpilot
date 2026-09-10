"""BaseAgent — 异步 tool-use 循环（并发工具调用 + 可选流式输出）。

与旧版的两点关键差异：
1. `run` 是 async 的，多个 Agent 可以被 asyncio.gather 真正并行调度；
2. 同一轮内的多个工具调用用 asyncio.gather 并发执行，而不是 for 循环串行等待。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.streaming import stream_sync_in_thread
from wealthpilot.services.agents.tools import execute_tool
from wealthpilot.services.evidence import ToolSession, record_evidence
from wealthpilot.settings import get_settings

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

Emit = Callable[[dict], Awaitable[None]]


class AgentResult:
    """一个 Agent 的执行产物，供 Synthesizer 消费。"""

    def __init__(self, agent: str, goal: str, text: str, evidence: list[dict], status: str = "completed"):
        self.agent = agent
        self.goal = goal
        self.text = text
        self.evidence = evidence  # [{"tool": ..., "input": ..., "output": ...}]
        self.status = status

    @property
    def tool_names(self) -> list[str]:
        return [e["tool"] for e in self.evidence]


class BaseAgent:
    """所有专业 Agent 的基类。"""

    def __init__(
        self,
        name: str,
        tools: list[dict],
        system_prompt: str,
        client: AIClient,
        model: str,
        holdings: list[PortfolioHolding] | None = None,
        nav_data: dict[str, float] | None = None,
        nav_history: dict[str, list[dict]] | None = None,
        profile: InvestorProfile | None = None,
    ):
        self.name = name
        self.tools = tools
        self.system_prompt = system_prompt
        self.client = client
        self.model = model
        self.holdings = holdings or []
        self.nav_data = nav_data or {}
        self.nav_history = nav_history
        self.profile = profile
        self.runtime = ToolSession()

    async def run(
        self,
        messages: list[dict],
        emit: Emit,
        *,
        goal: str = "",
        stream_text: bool = True,
    ) -> AgentResult:
        """执行 agent。

        Args:
            messages: 对话消息列表（会被就地追加 tool-use 轮次）。
            emit: 异步事件回调，用于把 SSE 事件送回 orchestrator。
            goal: 本次执行的子任务目标，仅用于回传标注。
            stream_text: True 时把模型增量文本作为 `delta` 事件发出（单任务快路径）；
                False 时静默缓冲，由 Synthesizer 统一输出（并行多任务）。
        """
        settings = get_settings()
        max_rounds = settings.agent_max_tool_rounds
        max_tokens = settings.agent_max_tokens

        tool_rounds = 0
        final_text = ""
        evidence: list[dict] = []
        status = "completed"

        try:
            while True:
                round_text = ""
                response = None
                stream_error: Exception | None = None

                def make_stream(msgs=messages):
                    return self.client.stream(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=[
                            {
                                "type": "text",
                                "text": self.system_prompt,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        tools=self.tools,
                        messages=msgs,
                    )

                async for kind, payload in stream_sync_in_thread(make_stream):
                    if kind == "delta":
                        round_text += payload
                        if stream_text:
                            await emit({"type": "delta", "content": payload})
                    elif kind == "final":
                        response = payload
                    elif kind == "error":
                        stream_error = payload

                if stream_error is not None:
                    raise stream_error
                if response is None:
                    break

                if response.stop_reason == "tool_use" and tool_rounds < max_rounds:
                    tool_rounds += 1

                    for tc in response.tool_calls:
                        await emit(
                            {
                                "type": "tool_call",
                                "agent": self.name,
                                "tool": tc.name,
                                "input": tc.input,
                            }
                        )

                    # 同一轮内的工具并发执行 —— 3 次网络往返压缩成 1 次的耗时
                    outputs = await asyncio.gather(
                        *[self._run_tool(tc.name, tc.input) for tc in response.tool_calls],
                        return_exceptions=True,
                    )

                    tool_results = []
                    for tc, out in zip(response.tool_calls, outputs, strict=True):
                        content = f"工具执行失败: {out}" if isinstance(out, Exception) else out
                        record = record_evidence(tc.name, tc.input, content, self.nav_history)
                        evidence.append(record)
                        await emit({"type": "evidence", "agent": self.name, "evidence": record})
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tc.id,
                                "content": content,
                            }
                        )

                    messages.append({"role": "assistant", "content": response.raw_content})
                    messages.append({"role": "user", "content": tool_results})
                    final_text += round_text
                else:
                    if response.stop_reason == "tool_use":
                        status = "budget_exhausted"
                    final_text += round_text
                    break

        except Exception as e:  # noqa: BLE001
            status = "failed"
            await emit({"type": "error", "content": f"{self.name} 异常: {e}"})

        return AgentResult(agent=self.name, goal=goal, text=final_text, evidence=evidence, status=status)

    async def _run_tool(self, name: str, input_data: dict) -> str:
        if name not in {t["name"] for t in self.tools}:
            raise ValueError(f"该 Agent 无权调用工具：{name}")
        return await self.runtime.execute(name, input_data, lambda: execute_tool(
            name, input_data, self.holdings, self.nav_data, self.nav_history, self.profile
        ))
