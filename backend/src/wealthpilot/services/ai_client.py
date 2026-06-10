"""AI 客户端抽象层 — 支持 Anthropic 和 DeepSeek (OpenAI 兼容) 两种提供商。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field

from anthropic import Anthropic
from openai import OpenAI


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class CompletionResult:
    text: str = ""
    stop_reason: str = "end_turn"
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_content: list[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# 格式转换工具
# ═══════════════════════════════════════════════════════════

def _convert_tools_to_openai(tools: list[dict]) -> list[dict]:
    result = []
    for t in tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        })
    return result


def _convert_messages_to_openai(messages: list[dict]) -> list[dict]:
    converted = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            converted.append({"role": role, "content": str(content)})
            continue

        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"], ensure_ascii=False),
                        },
                    })
            entry: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            converted.append(entry)

        elif role == "user":
            has_tool_results = any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
            if has_tool_results:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        converted.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block.get("content", ""),
                        })
            else:
                converted.append({"role": "user", "content": str(content)})

    return converted


def _extract_system_text(system) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list) and system:
        return system[0].get("text", "")
    return ""


def _anthropic_response_to_result(response) -> CompletionResult:
    text = ""
    tool_calls = []
    raw_content = []

    for block in response.content:
        if block.type == "text":
            text += block.text
            raw_content.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
            raw_content.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })

    stop_reason = "tool_use" if response.stop_reason == "tool_use" else "end_turn"
    return CompletionResult(
        text=text, stop_reason=stop_reason,
        tool_calls=tool_calls, raw_content=raw_content,
    )


# ═══════════════════════════════════════════════════════════
# Anthropic 实现
# ═══════════════════════════════════════════════════════════

class AnthropicStreamContext:
    def __init__(self, client: Anthropic, **kwargs):
        self._stream_mgr = client.messages.stream(**kwargs)
        self._stream = None
        self._response = None

    def __enter__(self):
        self._stream = self._stream_mgr.__enter__()
        return self

    def __exit__(self, *args):
        self._stream_mgr.__exit__(*args)

    @property
    def text_stream(self) -> Iterator[str]:
        yield from self._stream.text_stream

    def get_final_result(self) -> CompletionResult:
        response = self._stream.get_final_message()
        return _anthropic_response_to_result(response)


class AnthropicAIClient:
    def __init__(self, api_key: str):
        self._client = Anthropic(api_key=api_key)

    def create(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None) -> CompletionResult:
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
        if isinstance(system, list):
            kwargs["system"] = system
        elif system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        response = self._client.messages.create(**kwargs)
        return _anthropic_response_to_result(response)

    def stream(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None) -> AnthropicStreamContext:
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
        if isinstance(system, list):
            kwargs["system"] = system
        elif system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        return AnthropicStreamContext(self._client, **kwargs)


# ═══════════════════════════════════════════════════════════
# DeepSeek (OpenAI 兼容) 实现
# ═══════════════════════════════════════════════════════════

class DeepSeekStreamContext:
    def __init__(self, client: OpenAI, **kwargs):
        self._client = client
        self._kwargs = kwargs
        self._stream = None
        self._accumulated_text = ""
        self._tool_accumulators: dict[int, dict] = {}
        self._finish_reason: str | None = None

    def __enter__(self):
        system = self._kwargs.pop("system", None)
        tools = self._kwargs.pop("tools", None)
        messages = list(self._kwargs.pop("messages", []))

        sys_text = _extract_system_text(system)
        if sys_text:
            messages = [{"role": "system", "content": sys_text}] + messages
        messages = _convert_messages_to_openai(messages)

        call_kwargs = dict(self._kwargs, messages=messages, stream=True)
        if tools:
            call_kwargs["tools"] = _convert_tools_to_openai(tools)
        self._stream = self._client.chat.completions.create(**call_kwargs)
        return self

    def __exit__(self, *args):
        if self._stream:
            self._stream.close()

    @property
    def text_stream(self) -> Iterator[str]:
        for chunk in self._stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta and delta.content:
                self._accumulated_text += delta.content
                yield delta.content

            if delta and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in self._tool_accumulators:
                        self._tool_accumulators[idx] = {"id": "", "name": "", "arguments": ""}
                    acc = self._tool_accumulators[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        acc["name"] += tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        acc["arguments"] += tc_delta.function.arguments

            if choice.finish_reason:
                self._finish_reason = choice.finish_reason

    def get_final_result(self) -> CompletionResult:
        tool_calls = []
        raw_content = []

        if self._accumulated_text:
            raw_content.append({"type": "text", "text": self._accumulated_text})

        for idx in sorted(self._tool_accumulators):
            acc = self._tool_accumulators[idx]
            try:
                parsed_input = json.loads(acc["arguments"]) if acc["arguments"] else {}
            except json.JSONDecodeError:
                parsed_input = {}
            tc = ToolCall(id=acc["id"], name=acc["name"], input=parsed_input)
            tool_calls.append(tc)
            raw_content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.input,
            })

        stop_reason = "tool_use" if self._finish_reason == "tool_calls" else "end_turn"
        return CompletionResult(
            text=self._accumulated_text,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            raw_content=raw_content,
        )


class DeepSeekAIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def create(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None) -> CompletionResult:
        oai_messages = list(messages)
        sys_text = _extract_system_text(system)
        if sys_text:
            oai_messages = [{"role": "system", "content": sys_text}] + oai_messages
        oai_messages = _convert_messages_to_openai(oai_messages)

        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=oai_messages)
        if tools:
            kwargs["tools"] = _convert_tools_to_openai(tools)

        response = self._client.chat.completions.create(**kwargs)
        return self._to_result(response)

    def stream(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None) -> DeepSeekStreamContext:
        return DeepSeekStreamContext(
            self._client,
            model=model, max_tokens=max_tokens,
            system=system, messages=messages, tools=tools,
        )

    @staticmethod
    def _to_result(response) -> CompletionResult:
        choice = response.choices[0]
        msg = choice.message
        text = msg.content or ""
        tool_calls = []
        raw_content = []

        if text:
            raw_content.append({"type": "text", "text": text})

        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    parsed = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    parsed = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=parsed))
                raw_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": parsed,
                })

        stop_reason = "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
        return CompletionResult(
            text=text, stop_reason=stop_reason,
            tool_calls=tool_calls, raw_content=raw_content,
        )


# ═══════════════════════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════════════════════

AIClient = AnthropicAIClient | DeepSeekAIClient


def create_ai_client(settings) -> AIClient:
    if settings.ai_provider == "deepseek":
        if not settings.deepseek_api_key:
            raise ValueError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中设置")
        return DeepSeekAIClient(settings.deepseek_api_key, settings.deepseek_base_url)
    else:
        if not settings.anthropic_api_key:
            raise ValueError("未配置 ANTHROPIC_API_KEY，请在 backend/.env 中设置")
        return AnthropicAIClient(settings.anthropic_api_key)
