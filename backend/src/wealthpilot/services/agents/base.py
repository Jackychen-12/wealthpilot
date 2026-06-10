"""BaseAgent — 共享的 tool-use 循环逻辑。"""

import asyncio
import json
from collections.abc import Generator

from anthropic import Anthropic

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.tools import execute_tool


class BaseAgent:
    """所有专业 Agent 的基类。封装 Claude API tool-use 循环。"""

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
        """执行 agent，返回 SSE 格式字符串的生成器。"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
                tools=self.tools,
                messages=messages,
            )

            loop = asyncio.new_event_loop()
            tool_rounds = 0
            while response.stop_reason == "tool_use" and tool_rounds < 3:
                tool_rounds += 1
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield self._sse({"type": "tool_call", "agent": self.name, "tool": block.name, "input": block.input})
                        result = loop.run_until_complete(
                            execute_tool(block.name, block.input, self.holdings, self.nav_data, self.nav_history)
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
                    tools=self.tools,
                    messages=messages,
                )

            loop.close()

            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text

            chunk_size = 20
            for i in range(0, len(final_text), chunk_size):
                chunk = final_text[i:i + chunk_size]
                yield self._sse({"type": "delta", "content": chunk})

            yield from ()  # done event emitted by orchestrator
            self._final_text = final_text

        except Exception as e:
            yield self._sse({"type": "error", "content": f"{self.name} 异常: {e}"})
            self._final_text = ""

    @property
    def final_text(self) -> str:
        return getattr(self, "_final_text", "")

    @staticmethod
    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
