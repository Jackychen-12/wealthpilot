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
    # 命中缓存的 token 数：DeepSeek 放在 prompt_cache_hit_tokens，OpenAI 及多数兼容服务放在 prompt_tokens_details.cached_tokens
    cached = getattr(u, "prompt_cache_hit_tokens", None)
    if cached is None:
        details = getattr(u, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details is not None else 0
    usage.add(getattr(u, "prompt_tokens", 0) or 0, cached or 0, getattr(u, "completion_tokens", 0) or 0)


class DeepSeekAIClient:
    """兼容 OpenAI 接口的客户端。DeepSeek 用它，其他兼容服务（含本机的 Ollama）也用它，只是地址和几个开关不同。"""

    supports_json_mode = True

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 timeout: float | None = None, *, json_mode: bool = True, max_output: int = 8192):
        self.usage = Usage()
        # 有的服务不认 response_format（会直接报 400）：关掉后各处退回用正则从回复里取 JSON
        self.supports_json_mode = json_mode
        self.max_output = max_output
        # 本机模型一般不要 Key，但 SDK 不接受空串
        self._client = OpenAI(api_key=api_key or "not-needed", base_url=base_url,
                              **({"timeout": timeout} if timeout else {}))

    def create(self, *, model: str, max_tokens: int, system, messages: list[dict],
               tools: list[dict] | None = None, tool_choice: str | None = None, json_mode: bool = False) -> CompletionResult:
        oai_messages = list(messages)
        sys_text = _extract_system_text(system)
        if sys_text:
            oai_messages = [{"role": "system", "content": sys_text}] + oai_messages
        oai_messages = _convert_messages_to_openai(oai_messages)

        kwargs: dict = dict(model=model, max_tokens=min(max_tokens, self.max_output),
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
            model=model, max_tokens=min(max_tokens, self.max_output),
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


class ModelUnavailableError(RuntimeError):
    """模型这一轮肯定用不了（余额、Key、模型名、连不上）。

    这类错误重试也没用。认出来之后整轮研究立刻停，给用户一句能照着做的话，
    而不是让六个 Agent 各自报一串英文错误、再走完审核和重写。
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


_UNAVAILABLE = (
    ("balance", (402,), ("insufficient balance", "insufficient_quota", "insufficient quota", "exceeded your current quota", "payment required",
                         "余额不足", "欠费", "arrearage", "account balance"),
     "模型账户余额不足，这次没法研究。充值之后再试；或者到「设置」把模型换成别的服务 —— 任何兼容 OpenAI 接口的都行，包括本机的 Ollama。"
     "行情、选股、持仓、盯盘这些不用模型的功能不受影响。"),
    ("auth", (401, 403), ("invalid api key", "incorrect api key", "invalid_api_key", "authentication", "unauthorized", "api key not valid"),
     "模型的 API Key 无效或已过期。到「设置」重新填一个，填完点「测试当前配置」。"),
    ("model", (404,), ("model not found", "model_not_found", "no such model", "does not exist", "model not exist"),
     "模型名不对：服务商那边没有这个模型。到「设置」核对模型名和接口地址。"),
    ("rate_limit", (429,), ("rate limit", "rate_limit", "too many requests"),
     "模型服务限流了：请求太密，或者这个时段的额度用完了。等一两分钟再试。"),
)


def diagnose(exc: BaseException) -> ModelUnavailableError | None:
    """这个异常是不是"模型肯定用不了"。是就返回带人话的 ModelUnavailableError，不是返回 None。"""
    if isinstance(exc, ModelUnavailableError):
        return exc
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    for kind, codes, phrases, message in _UNAVAILABLE:
        if any(p in text for p in phrases) or (status in codes and kind != "model") or (kind == "model" and status == 404 and "model" in text):
            return ModelUnavailableError(kind, message)
    if "connect" in type(exc).__name__.lower() or "connection error" in text:
        return ModelUnavailableError("network", "连不上模型服务：网络不通，或者接口地址不对。用的是本机模型的话，先确认它已经启动。")
    return None


def raise_if_unavailable(exc: BaseException) -> None:
    found = diagnose(exc)
    if found is not None:
        raise found from exc


def create_ai_client(settings) -> AIClient:
    timeout = getattr(settings, "ai_timeout_seconds", None)
    if settings.ai_provider == "openai":
        if not settings.openai_base_url.strip() or not settings.openai_model.strip():
            raise ValueError("还没有填模型服务的接口地址和模型名")
        return DeepSeekAIClient(settings.openai_api_key, settings.openai_base_url.strip(), timeout,
                                json_mode=settings.openai_json_mode, max_output=settings.openai_max_tokens)
    if settings.ai_provider == "deepseek":
        if settings.deepseek_api_key.strip() in _PLACEHOLDER_KEYS:
            raise ValueError("还没有填 DeepSeek 的 API Key")
        return DeepSeekAIClient(settings.deepseek_api_key, settings.deepseek_base_url, timeout)
    else:
        if settings.anthropic_api_key.strip() in _PLACEHOLDER_KEYS:
            raise ValueError("还没有填 Claude 的 API Key")
        return AnthropicAIClient(settings.anthropic_api_key, timeout)
