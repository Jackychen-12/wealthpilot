"""BaseAgent — 共享的 tool-use 循环逻辑（真实流式 + 工具调用混合）。"""

import asyncio
import json
from collections.abc import Generator

from anthropic import Anthropic

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.tools import execute_tool
from wealthpilot.settings import get_settings


class BaseAgent:
    """所有专业 Agent 的基类。封装 Claude API 流式 tool-use 循环。"""

    def __init__(
        self,
        name: str,
        tools: list[dict],
        system_prompt: str,
        client: Anthropic,
        model: str,
        holdings: list[PortfolioHolding] | None = None,
        nav_data: dict[str, float] | None = None,
        nav_history: dict[str, list[dict]] | None = None,
    ):
        self.name = name
        self.tools = tools
        self.system_prompt = system_prompt
        self.client = client
        self.model = model
        self.holdings = holdings or []
        self.nav_data = nav_data or {}
        self.nav_history = nav_history

    def run(self, messages: list[dict]) -> Generator[str, None, None]:
        """执行 agent，真实流式输出 + tool-use 循环。"""
        settings = get_settings()
        max_rounds = settings.agent_max_tool_rounds
        max_tokens = settings.agent_max_tokens
        tool_rounds = 0
        final_text = ""

        try:
            while True:
                round_text = ""

                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=[{
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    tools=self.tools,
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        round_text += text
                        yield self._sse({"type": "delta", "content": text})

                    response = stream.get_final_message()

                if response.stop_reason == "tool_use" and tool_rounds < max_rounds:
                    tool_rounds += 1

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            yield self._sse({
                                "type": "tool_call",
                                "agent": self.name,
                                "tool": block.name,
                                "input": block.input,
                            })
                            result = self._run_tool(
                                block.name, block.input,
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })

                    assistant_content = []
                    for block in response.content:
                        if block.type == "text":
                            assistant_content.append({
                                "type": "text",
                                "text": block.text,
                            })
                        elif block.type == "tool_use":
                            assistant_content.append({
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            })

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                    final_text += round_text
                else:
                    final_text += round_text
                    break

            self._final_text = final_text

        except Exception as e:
            yield self._sse({"type": "error", "content": f"{self.name} 异常: {e}"})
            self._final_text = ""

    def _run_tool(self, name: str, input_data: dict) -> str:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                execute_tool(name, input_data, self.holdings, self.nav_data, self.nav_history)
            )
        finally:
            loop.close()

    @property
    def final_text(self) -> str:
        return getattr(self, "_final_text", "")

    @staticmethod
    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
