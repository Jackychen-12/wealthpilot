"""接什么模型、模型用不了时怎么办。全部用假客户端，不调用任何真实模型。"""

from types import SimpleNamespace

import pytest

from tests.test_pipeline import PLAN, FakeClient, _done, _run, _tool_use
from wealthpilot.services import ai_client
from wealthpilot.services.ai_client import (
    DeepSeekAIClient,
    ModelUnavailableError,
    Usage,
    create_ai_client,
    diagnose,
)


class ApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(Exception):
    pass


@pytest.mark.parametrize("exc,kind", [
    (ApiError(402, "Insufficient Balance"), "balance"),
    (ApiError(400, "You exceeded your current quota, please check your plan and billing details"), "balance"),
    (ApiError(401, "Authentication Fails, Your api key is invalid"), "auth"),
    (ApiError(404, "The model `gpt-9` does not exist"), "model"),
    (ApiError(429, "Rate limit reached"), "rate_limit"),
    (APIConnectionError("Connection error."), "network"),
])
def test_errors_that_mean_the_model_cannot_be_used(exc, kind):
    found = diagnose(exc)
    assert found is not None and found.kind == kind
    assert "设置" in found.message or "再试" in found.message or "启动" in found.message      # 每条都告诉用户下一步做什么


@pytest.mark.parametrize("exc", [RuntimeError("offline"), ApiError(500, "internal error"), TimeoutError("read timed out"),
                                 ApiError(404, "Not Found"), ValueError("bad json")])
def test_ordinary_failures_are_not_mistaken_for_it(exc):
    assert diagnose(exc) is None


async def test_no_balance_stops_the_whole_run_with_one_message(monkeypatch):
    calls = {"create": 0, "stream": 0}

    class Broke(FakeClient):
        def create(self, **kwargs):
            calls["create"] += 1
            raise ApiError(402, "Insufficient Balance")

        def stream(self, **kwargs):
            calls["stream"] += 1
            raise ApiError(402, "Insufficient Balance")

    events = await _run(monkeypatch, Broke(lambda kw: _tool_use()))
    done = _done(events)
    assert done["meta"] == {"status": "failed", "reason": "balance"}
    assert "余额不足" in done["content"] and "Insufficient" not in done["content"]
    assert [e["type"] for e in events].count("error") == 1          # 只说一次，不是每个 Agent 各报一遍
    assert calls == {"create": 1, "stream": 0}                       # 规划那一步就停了，后面的 Agent 没有再去撞墙


async def test_a_bad_key_met_by_the_agents_also_stops_everything(monkeypatch):
    def on_stream(kwargs):
        raise ApiError(401, "Incorrect API key provided")

    events = await _run(monkeypatch, FakeClient(on_stream, creates=[PLAN]))
    done = _done(events)
    assert done["meta"]["reason"] == "auth" and "API Key" in done["content"]
    assert not any(e["type"] == "critic" for e in events)            # 没有再走审核和重写


def _settings(**kw):
    base = dict(ai_provider="openai", openai_api_key="", openai_model="qwen2.5:14b", openai_base_url="http://localhost:11434/v1",
                openai_json_mode=False, openai_max_tokens=4096, ai_timeout_seconds=30, deepseek_api_key="", deepseek_base_url="",
                anthropic_api_key="")
    return SimpleNamespace(**{**base, **kw})


def test_any_openai_compatible_service_can_be_used_and_local_models_need_no_key():
    client = create_ai_client(_settings())
    assert isinstance(client, DeepSeekAIClient) and client.supports_json_mode is False and client.max_output == 4096
    assert str(client._client.base_url).startswith("http://localhost:11434/v1")
    assert ai_client.json_mode(client) == {}                         # 不认 JSON 模式的服务：不传这个参数
    assert ai_client.json_mode(create_ai_client(_settings(openai_json_mode=True))) == {"json_mode": True}
    with pytest.raises(ValueError, match="接口地址"):
        create_ai_client(_settings(openai_base_url=""))


def test_output_cap_follows_the_provider(monkeypatch):
    client = create_ai_client(_settings(openai_max_tokens=2048))
    sent = {}

    def fake_create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="好", tool_calls=None))])
    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    client.create(model="m", max_tokens=16000, system="s", messages=[{"role": "user", "content": "hi"}], json_mode=True)
    assert sent["max_tokens"] == 2048 and "response_format" in sent


def test_cached_tokens_are_read_in_both_dialects():
    usage = Usage()
    ai_client._record_openai_usage(usage, SimpleNamespace(prompt_tokens=100, prompt_cache_hit_tokens=40, completion_tokens=10))
    ai_client._record_openai_usage(usage, SimpleNamespace(prompt_tokens=200, completion_tokens=20,
                                                          prompt_tokens_details=SimpleNamespace(cached_tokens=50)))
    ai_client._record_openai_usage(usage, SimpleNamespace(prompt_tokens=50, completion_tokens=5))
    assert usage.as_dict()["input_tokens"] == 350 and usage.as_dict()["cached_tokens"] == 90


def test_settings_route_accepts_the_third_provider():
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    from wealthpilot.routes.onboarding import model_ready
    client = TestClient(app)
    r = client.put("/api/settings", json={"ai_provider": "openai", "openai_base_url": "http://localhost:11434/v1", "openai_model": "qwen2.5:14b"})
    assert r.status_code == 200 and r.json()["active_model"] == "qwen2.5:14b" and "openai_api_key" in r.json()["secrets"]
    assert model_ready()                                             # 本机模型没有 Key 也算配好了
    assert client.put("/api/settings", json={"ai_provider": "gemini"}).status_code == 422
    client.put("/api/settings", json={"ai_provider": "deepseek", "openai_base_url": "", "openai_model": ""})


def test_model_unavailable_is_an_exception_with_a_kind():
    err = ModelUnavailableError("balance", "余额不足")
    assert err.kind == "balance" and str(err) == "余额不足" and diagnose(err) is err
