"""装好之后的命令：setup / model / config / status / skills / import。不需要真的终端，也不调用模型。"""

import argparse
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from wealthpilot import cli
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.routes.config import ENV_FILE
from wealthpilot.services import providers
from wealthpilot.settings import HOME, get_settings, reload_settings
from wealthpilot.storage.db import get_engine


@pytest.fixture(autouse=True)
def _fresh_env(monkeypatch):
    """每个测试从一份空配置开始。HOME 是 conftest 给的临时目录，不是开发者自己的 backend/。"""
    assert "wealthpilot-test-" in str(HOME)
    for name in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)       # conftest 用环境变量把它们钉成了空，这里要让写进文件的值生效
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()
    yield
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()


def _args(**kw):
    base = dict(provider=None, key=None, model=None, base_url=None, sample=False, test=False, no_test=False)
    return argparse.Namespace(**{**base, **kw})


def _run_setup(args, answers=(), secrets=(), interactive=True, tester=None):
    out, replies, hidden, tested = [], list(answers), list(secrets), []

    def tester_fn():
        tested.append(True)
        return tester or (True, "ok")
    code = cli.cmd_setup(args, ask=lambda prompt: replies.pop(0) if replies else "", secret=lambda prompt: hidden.pop(0) if hidden else "",
                         out=out.append, interactive=interactive, tester=tester_fn)
    return code, "\n".join(out), tested


def test_one_key_is_enough():
    code, text, tested = _run_setup(_args(key="sk-test-deepseek-000000", no_test=True), interactive=False)
    s = get_settings()
    assert code == 0 and s.ai_provider == "deepseek" and s.deepseek_api_key == "sk-test-deepseek-000000" and s.active_model == "deepseek-chat"
    assert "已保存：DeepSeek" in text and "sk-test" not in text and tested == []          # Key 不回显；说了不测就不测
    assert oct(ENV_FILE.stat().st_mode)[-3:] == "600"
    # Anthropic 的 Key 有自己的前缀，认得出来
    _run_setup(_args(key="sk-ant-test-000000", no_test=True), interactive=False)
    assert get_settings().ai_provider == "anthropic" and get_settings().anthropic_api_key == "sk-ant-test-000000"


def test_a_named_service_fills_in_its_address_and_default_model():
    code, text, _ = _run_setup(_args(provider="智谱", key="zp-test-000000", no_test=True), interactive=False)
    s = get_settings()
    assert code == 0 and (s.ai_provider, s.openai_base_url, s.openai_model) == ("openai", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash")
    _run_setup(_args(provider="ollama", model="qwen2.5:7b", no_test=True), interactive=False)       # 本机模型不要 Key
    s = get_settings()
    assert s.openai_base_url == "http://localhost:11434/v1" and s.openai_model == "qwen2.5:7b"
    code, text, _ = _run_setup(_args(provider="ark", key="k-000000", no_test=True), interactive=False)   # 没有默认模型名的服务要自己给
    assert "--model" in text and get_settings().openai_base_url == "http://localhost:11434/v1"       # 没保存，原来的不动
    assert _run_setup(_args(provider="不存在的", key="x"), interactive=False)[1].startswith("不认识")
    # 清单之外的服务：给地址和模型名就行，自己机器上跑的不要 Key
    assert _run_setup(_args(base_url="http://localhost:8080/v1", model="my-model", no_test=True), interactive=False)[0] == 0
    assert (get_settings().openai_base_url, get_settings().openai_model) == ("http://localhost:8080/v1", "my-model")


def test_the_wizard_walks_three_steps_and_every_step_can_be_skipped(monkeypatch):
    from wealthpilot.routes import onboarding, research
    loaded = []
    monkeypatch.setattr(research, "load_sample", lambda db, uid: loaded.append(uid))
    # 选 1（DeepSeek）→ 模型名回车用默认 → 测试 y → 持仓输入 s
    code, text, tested = _run_setup(_args(), answers=["1", "", "y", "s"], secrets=["sk-test-wizard-000000"])
    assert code == 0 and get_settings().deepseek_api_key == "sk-test-wizard-000000" and tested == [True] and loaded == [0]
    for expected in ("1/3", "2/3", "3/3", "模型可用", "wealthpilot doctor", "手机"):
        assert expected in text, expected
    # 全部跳过：什么都不写
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()
    code, text, tested = _run_setup(_args(), answers=["0", ""])
    assert code == 0 and not ENV_FILE.exists() and tested == [] and "跳过了模型" in text
    assert onboarding.model_ready() is False


def test_a_failed_test_call_says_why_but_keeps_the_config():
    code, text, _ = _run_setup(_args(key="sk-test-000000", test=True), interactive=False, tester=(False, "模型账户余额不足，这次没法研究。"))
    assert code == 0 and "✗ 调不通：模型账户余额不足" in text and get_settings().deepseek_api_key == "sk-test-000000"


def test_setup_without_a_terminal_explains_the_flags():
    code, text, _ = _run_setup(_args(), interactive=False)
    assert code == 2 and "wealthpilot setup --key" in text and not ENV_FILE.exists()


def test_pasting_holdings_in_the_wizard(monkeypatch):
    from wealthpilot.routes import onboarding

    async def search(query, limit=1):
        return [{"code": "600519", "name": "贵州茅台", "asset_type": "stock"}] if "茅台" in query else []

    async def no_profile(code):
        return None
    monkeypatch.setattr(onboarding.securities, "search", search)
    monkeypatch.setattr(onboarding, "fetch_stock_profile", no_profile)
    code, text, _ = _run_setup(_args(), answers=["0", "贵州茅台 100 1500; 不存在 1 1", "y"])
    assert "贵州茅台 600519  100 股  成本 1500" in text and "没找到" in text and "已添加 1 条" in text
    with Session(get_engine()) as db:
        rows = db.exec(select(PortfolioHolding).where(PortfolioHolding.fund_code == "600519", PortfolioHolding.user_id == 0)).all()
        assert len(rows) == 1
        db.delete(rows[0])
        db.commit()


def _capture(fn, args):
    out = []
    return fn(args, out=out.append), "\n".join(out)


def test_config_list_get_set_never_shows_a_key():
    _run_setup(_args(key="sk-test-secret-9876", no_test=True), interactive=False)
    code, text = _capture(cli.cmd_config, argparse.Namespace(action="list", key=None, value=None))
    assert code == 0 and "deepseek_api_key" in text and "…9876" in text and "sk-test-secret" not in text
    code, text = _capture(cli.cmd_config, argparse.Namespace(action="set", key="daily_token_budget", value="500000"))
    assert code == 0 and "daily_token_budget = 500000" in text          # 显示的是改完之后的值，不是改之前的
    assert get_settings().daily_token_budget == 500000
    assert _capture(cli.cmd_config, argparse.Namespace(action="get", key="daily_token_budget", value=None))[1] == "500000"
    assert _capture(cli.cmd_config, argparse.Namespace(action="set", key="debate_enabled", value="off"))[0] == 0 and get_settings().debate_enabled is False
    code, text = _capture(cli.cmd_config, argparse.Namespace(action="set", key="watch_time", value="25点"))
    assert code == 1 and "没有保存" in text
    assert _capture(cli.cmd_config, argparse.Namespace(action="set", key="jwt_secret", value="x"))[0] == 2      # 白名单之外的改不了
    assert _capture(cli.cmd_config, argparse.Namespace(action="path", key=None, value=None))[1] == str(ENV_FILE)


def test_model_show_list_set():
    code, text = _capture(lambda a, out: cli.cmd_model(a, out=out), argparse.Namespace(action=None, name=None, key=None, model=None, base_url=None))
    assert "还没配好" in text
    code, text = _capture(lambda a, out: cli.cmd_model(a, out=out), argparse.Namespace(action="list", name=None, key=None, model=None, base_url=None))
    assert all(p["key"] in text for p in providers.PRESETS)
    code, text = _capture(lambda a, out: cli.cmd_model(a, out=out), argparse.Namespace(action="set", name="moonshot", key="mk-000000", model=None, base_url=None))
    assert code == 0 and get_settings().openai_base_url == "https://api.moonshot.cn/v1"
    code, text = _capture(lambda a, out: cli.cmd_model(a, out=out, tester=lambda: (False, "Key 无效")), argparse.Namespace(action="test", name=None, key=None, model=None, base_url=None))
    assert code == 1 and "Key 无效" in text


def test_status_tells_what_is_missing():
    code, text = _capture(cli.cmd_status, SimpleNamespace())
    assert code == 1 and "还没配好：wealthpilot setup" in text and "数据目录" in text and "今天用量" in text
    _run_setup(_args(key="sk-test-000000", no_test=True), interactive=False)
    code, text = _capture(cli.cmd_status, SimpleNamespace())
    assert code == 0 and "deepseek · deepseek-chat" in text and "还没配好" not in text


def test_skills_from_the_gallery():
    from wealthpilot.services import skills
    code, text = _capture(cli.cmd_skills, argparse.Namespace(action="gallery", name=None, yes=False))
    assert "bank-check" in text
    assert _capture(cli.cmd_skills, argparse.Namespace(action="install", name="bank-check", yes=False))[0] == 0 and skills.get("bank-check")
    assert "bank-check" in _capture(cli.cmd_skills, argparse.Namespace(action="list", name=None, yes=False))[1]
    assert _capture(cli.cmd_skills, argparse.Namespace(action="install", name="no-such", yes=False))[0] == 1
    assert _capture(cli.cmd_skills, argparse.Namespace(action="remove", name="bank-check", yes=False))[0] == 0 and skills.get("bank-check") is None


def test_presets_cover_what_the_settings_page_offers():
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    served = TestClient(app).get("/api/settings").json()["presets"]
    assert {p["key"] for p in served} >= {"siliconflow", "zhipu", "moonshot", "dashscope", "ollama"} and all(p["base_url"].startswith("http") for p in served)
    assert providers.find("Kimi")["key"] == "moonshot" and providers.find("豆包")["key"] == "ark" and providers.find("nope") is None
    assert providers.changes_for(providers.BY_KEY["claude"], "k")["anthropic_model"] == "claude-sonnet-5-5"


def test_import_holdings_from_a_file(tmp_path, monkeypatch):
    from wealthpilot.routes import onboarding

    async def search(query, limit=1):
        return [{"code": "600036", "name": "招商银行", "asset_type": "stock"}] if "招商" in query else []

    async def no_profile(code):
        return None
    monkeypatch.setattr(onboarding.securities, "search", search)
    monkeypatch.setattr(onboarding, "fetch_stock_profile", no_profile)
    file = tmp_path / "holdings.txt"
    file.write_text("招商银行 2000 35.2\n不存在的 1 1\n", encoding="utf-8")
    code, text = _capture(cli.cmd_import, argparse.Namespace(file=str(file), yes=True))
    assert code == 0 and "招商银行 600036  2000 股  成本 35.2" in text and "✗" in text and "已添加 1 条" in text
    with Session(get_engine()) as db:
        rows = db.exec(select(PortfolioHolding).where(PortfolioHolding.fund_code == "600036", PortfolioHolding.user_id == 0)).all()
        assert len(rows) == 1
        db.delete(rows[0])
        db.commit()
    file.write_text("随手写的一行\n", encoding="utf-8")
    code, text = _capture(cli.cmd_import, argparse.Namespace(file=str(file), yes=True))
    assert code == 1 and "没有写入" in text


def test_sessions_lists_or_says_there_are_none():
    code, text = _capture(cli.cmd_sessions, SimpleNamespace())
    assert code == 0 and ("还没有会话" in text or "/sessions <序号>" in text)


def test_the_version_is_the_same_everywhere():
    """版本号写在三处。锁文件落后的话，装好之后 uv sync 会改写它，代码目录变脏，wealthpilot update 就会拒绝拉取。"""
    import tomllib
    from pathlib import Path

    from wealthpilot import __version__
    from wealthpilot.services.upgrade import release_notes
    backend = Path(__file__).resolve().parents[1]
    assert tomllib.loads((backend / "pyproject.toml").read_text())["project"]["version"] == __version__
    locked = next(p for p in tomllib.loads((backend / "uv.lock").read_text())["package"] if p["name"] == "wealthpilot")
    assert locked["version"] == __version__, "改了版本号之后要运行一次 uv lock"
    assert release_notes((backend.parent / "CHANGELOG.md").read_text(encoding="utf-8"))[0]["version"] == __version__


def test_the_installer_parses_and_uninstall_keeps_your_data(tmp_path):
    import subprocess
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / "scripts" / "install.sh"
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    data, app, bin_dir = tmp_path / "data", tmp_path / "data" / "app", tmp_path / "bin"
    (app / "backend").mkdir(parents=True)
    bin_dir.mkdir()
    (bin_dir / "wealthpilot").write_text("#!/bin/sh\n")
    (data / ".env").write_text("AI_PROVIDER=deepseek\n")
    done = subprocess.run(["bash", str(script), "--uninstall"], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "WEALTHPILOT_HOME": str(data), "WEALTHPILOT_BIN_DIR": str(bin_dir)})
    assert done.returncode == 0 and "数据还在" in done.stdout
    assert not app.exists() and not (bin_dir / "wealthpilot").exists() and (data / ".env").exists()


def test_the_windows_installer_is_safe_to_pipe_into_a_shell_and_matches_the_unix_one():
    """这台机器上没有 PowerShell，跑不了它；能钉住的只有这几条会让它在别人电脑上出事的写法。"""
    import re
    from pathlib import Path
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    raw = (scripts / "install.ps1").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "不能带 BOM：irm | iex 会把它当成第一个命令的一部分"
    text = raw.decode("utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"^\s*exit\b", code, re.M), "脚本是在用户自己的窗口里运行的，exit 会把窗口关掉"
    assert not re.search(r"[\u4e00-\u9fff\uff00-\uffef]`", text), "中文后面紧跟反引号：文件被按 GBK 读错时会吞掉转义"
    for opener, closer in ("{}", "()"):
        assert code.count(opener) == code.count(closer), f"{opener}{closer} 没配平"
    assert code.count("'") % 2 == 0
    unix = (scripts / "install.sh").read_text(encoding="utf-8")
    for name in ("WEALTHPILOT_KEY", "WEALTHPILOT_HOME", "WEALTHPILOT_DIR", "WEALTHPILOT_BIN_DIR", "WEALTHPILOT_REPO", "WEALTHPILOT_BRANCH", "WEALTHPILOT_SKIP_WEB"):
        assert name in text and name in unix, name                       # 两边认同一套环境变量
    for same in ("uv sync --quiet --extra feishu --extra dingtalk", "--outDir dist-app --emptyOutDir", "setup --key", "--depth 1 --branch"):
        assert same in text and same in unix, same                      # 装的是同一样东西
    assert "PYTHONUTF8=1" in text and "npm.cmd" in text and "ExpandString" in text


def test_channels_can_be_set_up_and_paired_without_the_web_page(monkeypatch):
    from wealthpilot.services import channels

    def run(*words, **flags):
        out: list[str] = []
        base = dict(action=words[0] if words else None, name=words[1] if len(words) > 1 else None,
                    token=None, app_id=None, app_secret=None, client_id=None, client_secret=None, corp_id=None, agent_id=None, secret=None, aes_key=None)
        return cli.cmd_channels(argparse.Namespace(**{**base, **flags}), out=out.append), "\n".join(out)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    channels.set_owner(None, "telegram")
    channels.set_owner(None, "feishu")
    channels.set_owner(None, "dingtalk")
    code, text = run()
    assert code == 0 and text.count("没有配置") == 4 and "@BotFather" in text and "Stream 模式" in text and "开着的时候" in text
    assert run("pair", "telegram")[0] == 1 and run("setup", "telegram")[0] == 2 and run("pair")[0] == 2      # 没配好不给码；没说哪个渠道
    code, text = run("setup", "feishu", app_id="cli_test")
    assert code == 1 and "--app-secret" in text                                                               # 存了一半：说还缺什么
    code, text = run("setup", "dingtalk", client_id="dingtest1", client_secret="not-a-real-secret-000")
    assert code == 0 and channels.configured("dingtalk") and "channels pair dingtalk" in text and "not-a-real-secret" not in text
    code, text = run("setup", "telegram", token="123456:not-a-real-token-000000000000")
    assert code == 0 and "channels pair telegram" in text and "not-a-real-token" not in text
    code, text = run("pair", "telegram")
    pair = text.split("配对码：")[1][:6]
    assert code == 0 and channels._pair_matches(pair, "telegram") and "/pair " + pair in text
    assert "配好了，还没绑定" in run()[1]
    assert run("test", "telegram")[0] == 1                                                                    # 还没绑定：不发
    channels.set_owner(42, "telegram")
    sent = []

    class Api:
        async def send(self, chat_id, text, buttons=None):
            sent.append((chat_id, text))
    monkeypatch.setattr(channels, "_api_for", lambda name: Api())
    assert run("test", "telegram")[0] == 0 and sent[0][0] == 42 and "已绑定" in run()[1]
    assert run("unpair", "telegram")[0] == 0 and channels.owner("telegram") is None


def test_tab_completion_knows_the_commands_and_their_actions(tmp_path):
    import subprocess
    import sys
    bash = subprocess.run([sys.executable, "-m", "wealthpilot", "completion", "bash"], capture_output=True, text=True)
    zsh = subprocess.run([sys.executable, "-m", "wealthpilot", "completion", "zsh"], capture_output=True, text=True)
    assert bash.returncode == 0 and zsh.returncode == 0 and "compdef _wealthpilot wealthpilot" in zsh.stdout
    script = tmp_path / "completion.bash"
    script.write_text(bash.stdout, encoding="utf-8")
    probe = (f"source '{script}'; COMP_WORDS=(wealthpilot ba); COMP_CWORD=1; _wealthpilot; echo \"${{COMPREPLY[*]}}\"; "
             "COMP_WORDS=(wealthpilot model f); COMP_CWORD=2; _wealthpilot; echo \"${COMPREPLY[*]}\"")
    done = subprocess.run(["bash", "-c", probe], capture_output=True, text=True)
    assert done.stdout.split("\n")[:2] == ["backup", "fallback"], done.stderr
    for name in ("setup", "logs", "restore", "channels", "sessions"):
        assert f"'{name}:" in zsh.stdout          # 新加的命令不用改补全脚本，直接就有
