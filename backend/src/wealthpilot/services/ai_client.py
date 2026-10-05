"""AI 客户端抽象层 — 支持 Anthropic 和 DeepSeek (OpenAI 兼容) 两种提供商。"""

from __future__ import annotations

import json
import threading
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


class Usage:
    """一个客户端实例上累计的用量。编排器每轮研究新建一个客户端，所以这就是"这一轮花了多少"。

    cached 是命中上下文缓存的输入 token：系统提示和工具定义保持不变时，同一个 Agent 的
    后续调用只为新增的部分按全价付费。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = self.input = self.cached = self.output = 0

    def add(self, input_tokens: int = 0, cached: int = 0, output: int = 0) -> None:
        with self._lock:
            self.calls += 1
            self.input += int(input_tokens or 0)
            self.cached += int(cached or 0)
            self.output += int(output or 0)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input, "cached_tokens": self.cached, "output_tokens": self.output,
                "cache_hit_pct": round(self.cached / self.input * 100, 1) if self.input else 0.0}


def json_mode(client) -> dict:
    """支持 JSON 输出模式的客户端加上这个参数：规划、审核、提取这些只要 JSON 的调用不再靠正则去抠。"""
    return {"json_mode": True} if getattr(client, "supports_json_mode", False) else {}


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
                            "content": str(block.get("content", "")),
                        })
            else:
                converted.append({"role": "user", "content": "\n".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in content)})

    return converted


def _extract_system_text(system) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))
    return ""


# 调用方需要区分的停止原因；其余一律视作正常结束
_STOP_REASONS = ("tool_use", "max_tokens", "refusal")
_OPENAI_FINISH = {"tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}


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
        elif block.type in ("thinking", "redacted_thinking"):
            # 开启思考的模型在工具轮次回放 assistant 消息时，思考块必须原样带回
            raw_content.append(block.model_dump(exclude_none=True))

    stop_reason = response.stop_reason if response.stop_reason in _STOP_REASONS else "end_turn"
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
    def __init__(self, api_key: str, timeout: float | None = None):
        self._client = Anthropic(api_key=api_key, **({"timeout": timeout} if timeout else {}))
        self.usage = Usage()

    @staticmethod
    def _kwargs(model, max_tokens, system, messages, tools, tool_choice) -> dict:
        kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = {"type": tool_choice}
        return kwargs

    def create(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None, tool_choice: str | None = None) -> CompletionResult:
        response = self._client.messages.create(
            **self._kwargs(model, max_tokens, system, messages, tools, tool_choice))
        u = getattr(response, "usage", None)
        if u is not None and hasattr(self, "usage"):
            cached = getattr(u, "cache_read_input_tokens", 0) or 0
            self.usage.add((getattr(u, "input_tokens", 0) or 0) + cached, cached, getattr(u, "output_tokens", 0))
        return _anthropic_response_to_result(response)

    def stream(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None, tool_choice: str | None = None) -> AnthropicStreamContext:
        return AnthropicStreamContext(
            self._client, **self._kwargs(model, max_tokens, system, messages, tools, tool_choice))


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
        tool_choice = self._kwargs.pop("tool_choice", None)
        messages = list(self._kwargs.pop("messages", []))

        sys_text = _extract_system_text(system)
        if sys_text:
            messages = [{"role": "system", "content": sys_text}] + messages
        messages = _convert_messages_to_openai(messages)

        self._usage = self._kwargs.pop("usage", None)
        call_kwargs = dict(self._kwargs, messages=messages, stream=True, stream_options={"include_usage": True})
        if tools:
            call_kwargs["tools"] = _convert_tools_to_openai(tools)
            if tool_choice:
                call_kwargs["tool_choice"] = tool_choice
        self._stream = self._client.chat.completions.create(**call_kwargs)
        return self

    def __exit__(self, *args):
        if self._stream:
            self._stream.close()

    @property
    def text_stream(self) -> Iterator[str]:
        for chunk in self._stream:
            if getattr(chunk, "usage", None) and self._usage is not None:
                _record_openai_usage(self._usage, chunk.usage)
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

        stop_reason = _OPENAI_FINISH.get(self._finish_reason or "", "end_turn")
        return CompletionResult(
            text=self._accumulated_text,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            raw_content=raw_content,
        )


# deepseek-chat 的输出上限；超过会直接 400，而 AGENT_MAX_TOKENS 的默认值是按 Claude 定的
_DEEPSEEK_MAX_OUTPUT = 8192


def _record_openai_usage(usage: Usage, u) -> None:
    usage.add(getattr(u, "prompt_tokens", 0), getattr(u, "prompt_cache_hit_tokens", 0) or 0, getattr(u, "completion_tokens", 0))


class DeepSeekAIClient:
    supports_json_mode = True

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 timeout: float | None = None):
        self.usage = Usage()
        self._client = OpenAI(api_key=api_key, base_url=base_url,
                              **({"timeout": timeout} if timeout else {}))

    def create(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None, tool_choice: str | None = None, json_mode: bool = False) -> CompletionResult:
        oai_messages = list(messages)
        sys_text = _extract_system_text(system)
        if sys_text:
            oai_messages = [{"role": "system", "content": sys_text}] + oai_messages
        oai_messages = _convert_messages_to_openai(oai_messages)

        kwargs: dict = dict(model=model, max_tokens=min(max_tokens, _DEEPSEEK_MAX_OUTPUT),
                            messages=oai_messages)
        if tools:
            kwargs["tools"] = _convert_tools_to_openai(tools)
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        if json_mode and not tools:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**kwargs)
        if getattr(response, "usage", None):
            _record_openai_usage(self.usage, response.usage)
        return self._to_result(response)

    def stream(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None, tool_choice: str | None = None) -> DeepSeekStreamContext:
        return DeepSeekStreamContext(
            self._client,
            model=model, max_tokens=min(max_tokens, _DEEPSEEK_MAX_OUTPUT),
            system=system, messages=messages, tools=tools, tool_choice=tool_choice, usage=self.usage,
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

        stop_reason = _OPENAI_FINISH.get(choice.finish_reason or "", "end_turn")
        return CompletionResult(
            text=text, stop_reason=stop_reason,
            tool_calls=tool_calls, raw_content=raw_content,
        )


# ═══════════════════════════════════════════════════════════
# 工厂函数
# ═══════════════════════════════════════════════════════════

AIClient = AnthropicAIClient | DeepSeekAIClient


# .env.example 里的占位值 —— 原样留着等于没配，早点报清楚比让每个 Agent 各吃一次 401 强
_PLACEHOLDER_KEYS = ("", "sk-ant-xxx", "sk-xxx")


def create_ai_client(settings) -> AIClient:
    timeout = getattr(settings, "ai_timeout_seconds", None)
    if settings.ai_provider == "deepseek":
        if settings.deepseek_api_key.strip() in _PLACEHOLDER_KEYS:
            raise ValueError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中设置")
        return DeepSeekAIClient(settings.deepseek_api_key, settings.deepseek_base_url, timeout)
    else:
        if settings.anthropic_api_key.strip() in _PLACEHOLDER_KEYS:
            raise ValueError("未配置 ANTHROPIC_API_KEY，请在 backend/.env 中设置")
        return AnthropicAIClient(settings.anthropic_api_key, timeout)
