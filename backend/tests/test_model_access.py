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


# ── 备用模型：主模型这一轮用不了时换过去，而不是整轮作废 ──────────────────

def _working():
    from tests.test_pipeline import _evidence_id
    from wealthpilot.services.ai_client import CompletionResult

    def on_stream(kwargs):
        if kwargs["messages"][-1]["role"] == "user" and isinstance(kwargs["messages"][-1]["content"], str):
            return _tool_use()
        return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")
    return FakeClient(on_stream, creates=[PLAN, '{"missing":[]}'])


class _Broke(FakeClient):
    def __init__(self, exc):
        super().__init__(lambda kw: _tool_use())
        self.exc, self.calls = exc, 0

    def create(self, **kwargs):
        self.calls += 1
        raise self.exc

    def stream(self, **kwargs):
        self.calls += 1
        raise self.exc


async def test_the_backup_model_takes_over_when_the_main_one_has_no_balance(monkeypatch):
    from wealthpilot.services.ai_client import FailoverClient
    primary, backup = _Broke(ApiError(402, "Insufficient Balance")), _working()
    events = await _run(monkeypatch, FailoverClient(primary, backup, "backup-model", "DeepSeek · backup-model"))
    done = _done(events)
    assert done["meta"]["status"] == "passed" and "1.5983" in done["content"]            # 这一轮照样出了结果
    assert done["meta"]["fallback"]["model"] == "DeepSeek · backup-model" and done["meta"]["fallback"]["reason"] == "balance"   # 而且如实说了是谁答的
    assert primary.calls == 1                                                              # 撞了一次墙就换，后面不再回头试主模型
    assert backup.stream_calls and all(c["model"] == "backup-model" for c in backup.stream_calls)   # 模型名换成了备用模型自己的


async def test_when_the_backup_fails_too_the_run_stops_with_the_usual_message(monkeypatch):
    from wealthpilot.services.ai_client import FailoverClient
    client = FailoverClient(_Broke(ApiError(429, "Rate limit reached")), _Broke(ApiError(401, "Incorrect API key provided")), "m")
    done = _done(await _run(monkeypatch, client))
    assert done["meta"]["status"] == "failed" and done["meta"]["reason"] == "auth"        # 报的是备用模型为什么也不行


def test_an_ordinary_error_does_not_trigger_the_switch():
    from wealthpilot.services.ai_client import FailoverClient
    client = FailoverClient(_Broke(ValueError("bad request: messages too long")), _working(), "m")
    with pytest.raises(ValueError):
        client.create(model="x", max_tokens=10, system="", messages=[])
    assert client.switched is None and client.fallback_info() is None                    # 不是"模型用不了"的错：不换，照常抛


def test_a_refused_stream_switches_before_any_text_is_shown():
    from wealthpilot.services.ai_client import CompletionResult, FailoverClient

    class Refuses(FakeClient):
        def stream(self, **kwargs):
            class Ctx:
                def __enter__(self):
                    raise ApiError(402, "Insufficient Balance")      # 真实的 SDK 是在这一步发请求、被拒的

                def __exit__(self, *a):
                    return False
            return Ctx()
    backup = FakeClient(lambda kw: CompletionResult(text="来自备用模型"))
    backup.supports_json_mode = False
    client = FailoverClient(Refuses(lambda kw: None), backup, "backup-model")
    with client.stream(model="main-model", max_tokens=10, system="", messages=[], json_mode=True) as s:
        assert "".join(s.text_stream) == "来自备用模型" and s.get_final_result().text == "来自备用模型"
    assert backup.stream_calls[0]["model"] == "backup-model" and "json_mode" not in backup.stream_calls[0]
    assert client.supports_json_mode is False and client.usage is backup.usage           # 之后按备用模型的能力来；两边记同一本账


def test_which_backup_is_in_effect():
    from wealthpilot.services.ai_client import FailoverClient, fallback_provider
    main = dict(ai_provider="deepseek", deepseek_api_key="sk-test-000000", deepseek_base_url="https://api.deepseek.com", deepseek_model="deepseek-chat",
                anthropic_model="claude-sonnet-5-5")
    assert fallback_provider(_settings(**main)) == ""                                     # 没设
    assert fallback_provider(_settings(**main, ai_fallback="deepseek")) == ""             # 和主模型同一家：不算
    assert fallback_provider(_settings(**main, ai_fallback="anthropic")) == ""            # 那一家没填 Key：不算
    assert fallback_provider(_settings(**main, ai_fallback="openai")) == "openai"         # 本机 Ollama 配好了：算
    client = create_ai_client(_settings(**main, ai_fallback="openai"))
    assert isinstance(client, FailoverClient) and client.fallback_model == "qwen2.5:14b" and "兼容服务" in client.fallback_label
    assert isinstance(create_ai_client(_settings(**main)), DeepSeekAIClient)              # 没设备用：和以前一样
    assert create_ai_client(_settings(**main, ai_max_retries=5))._client.max_retries == 5


def test_setting_a_backup_from_the_command_line():
    import argparse

    from wealthpilot import cli
    from wealthpilot.routes.config import ENV_FILE
    from wealthpilot.settings import get_settings, reload_settings

    def model(*words, **flags):
        out: list[str] = []
        args = argparse.Namespace(action=words[0] if words else None, name=words[1] if len(words) > 1 else None,
                                  key=flags.get("key"), model=flags.get("model"), base_url=None)
        return cli.cmd_model(args, out=out.append), "\n".join(out)
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()
    try:
        cli._apply({"ai_provider": "deepseek"})
        assert "没有" in model()[1]
        code, text = model("fallback", "deepseek", key="sk-x")
        assert code == 1 and "不同的位置" in text                                          # 和主模型同一个位置：不行，说清楚为什么
        code, text = model("fallback", "ollama", model="qwen2.5:7b")
        s = get_settings()
        assert code == 0 and (s.ai_fallback, s.ai_provider, s.openai_model) == ("openai", "deepseek", "qwen2.5:7b") and "qwen2.5:7b" in text
        code, text = model("fallback", "claude")                                          # 没给 Key：存了，但如实说还没生效
        assert code == 0 and "还没生效" in text
        assert model("fallback", "off")[0] == 0 and get_settings().ai_fallback == ""
        with pytest.raises(ValueError, match="备用模型"):
            cli._apply({"ai_fallback": "gpt"})
    finally:
        ENV_FILE.unlink(missing_ok=True)
        reload_settings()
