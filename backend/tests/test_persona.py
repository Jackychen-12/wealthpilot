"""说话方式：用户写的那段话到了模型手里，而且压不过规则。全部离线。"""

import argparse

import pytest
from fastapi.testclient import TestClient

from tests.test_pipeline import PLAN, FakeClient, _done, _evidence_id, _run, _tool_use
from wealthpilot import cli
from wealthpilot.main import app
from wealthpilot.services import backup, persona
from wealthpilot.services.agents import prompts, registry
from wealthpilot.services.ai_client import CompletionResult


@pytest.fixture(autouse=True)
def _blank():
    assert "wealthpilot-test-" in str(persona.FILE)
    persona.FILE.unlink(missing_ok=True)
    yield
    persona.FILE.unlink(missing_ok=True)


def test_nothing_written_means_nothing_changes():
    assert persona.read() == "" and persona.block() == ""
    assert "这样跟他说话" not in prompts.build_synthesizer_prompt(None, [], ["结论"])
    assert "这样跟他说话" not in registry.build_prompt("valuation", [], {}, None, stable_prefix=True)


def test_what_the_user_wrote_reaches_every_writer_but_rules_come_first():
    persona.write("像朋友聊天，先说结论。<!-- 这是给自己看的备注 -->")
    for prompt in (prompts.build_synthesizer_prompt(None, ["最新净值"], ["结论", "风险"]), registry.build_prompt("valuation", [], {}, None, stable_prefix=True)):
        assert "像朋友聊天，先说结论。" in prompt and "备注" not in prompt
        assert "以规则为准" in prompt and "证据引用" in prompt
    synth = prompts.build_synthesizer_prompt(None, [], ["结论", "风险"])
    assert synth.index("回答结构（必须遵守）") < synth.index("像朋友聊天") < synth.index("[E-证据ID]")      # 规则在前，引用要求在后面再强调一次
    # 同一段话，两次拼出来的系统提示逐字相同 —— 不破坏上下文缓存
    assert registry.build_prompt("price", [], {}, None, stable_prefix=True) == registry.build_prompt("price", [], {}, None, stable_prefix=True)


async def test_the_model_actually_receives_it(monkeypatch):
    persona.use("friend")

    def on_stream(kwargs):
        if kwargs["messages"][-1]["role"] == "user" and isinstance(kwargs["messages"][-1]["content"], str):
            return _tool_use()
        return CompletionResult(text=f"最新净值 1.5983 [{_evidence_id(kwargs)}]")
    client = FakeClient(on_stream, creates=[PLAN, '{"missing":[]}'])
    done = _done(await _run(monkeypatch, client))
    system = client.stream_calls[0]["system"][0]["text"]
    assert done["meta"]["status"] == "passed" and "像一个懂行的朋友" in system and "套话" in system


def test_presets_limits_and_clearing():
    assert persona.use("novice").startswith("我是新手") and persona.use("多泼冷水").startswith("多给我泼冷水")     # 名字和中文叫法都认
    with pytest.raises(ValueError, match="没有「老板」"):
        persona.use("老板")
    with pytest.raises(ValueError, match="太长了"):
        persona.write("话" * (persona.MAX_CHARS + 1))
    assert persona.read().startswith("多给我泼冷水")                      # 没写成功的那次不影响原来的
    assert persona.write("   ") == "" and not persona.FILE.exists()


def test_api_command_and_backup():
    client = TestClient(app)
    got = client.get("/api/settings/persona").json()
    assert got["text"] == "" and {p["key"] for p in got["presets"]} == set(persona.PRESETS) and got["max_chars"] == persona.MAX_CHARS
    saved = client.put("/api/settings/persona", json={"text": "说短点，别用套话"}).json()
    assert saved["text"] == "说短点，别用套话" and persona.read() == "说短点，别用套话"
    assert client.put("/api/settings/persona", json={"text": "x" * 5000}).status_code == 422

    def run(action=None, text=None):
        out: list[str] = []
        return cli.cmd_persona(argparse.Namespace(action=action, text=text), out=out.append), "\n".join(out)
    assert "说短点，别用套话" in run()[1] and "不会因为它被省掉" in run()[1]
    assert run("use")[0] == 0 and "friend" in run("use")[1] and "懂行的朋友" in run("use")[1]
    assert run("use", "brief")[0] == 0 and persona.read().startswith("我时间少")
    assert run("use", "不存在")[0] == 1 and run("set")[0] == 2
    assert run("set", "先说结论")[0] == 0 and persona.read() == "先说结论"
    archive = backup.create()
    assert "说话方式" in backup.inspect(archive)["contents"]
    assert run("clear")[0] == 0 and persona.read() == "" and "还没有写" in run()[1]
    backup.restore(archive)
    assert persona.read() == "先说结论"
    for file in backup.BACKUP_DIR.glob("*.tar.gz"):
        file.unlink()
