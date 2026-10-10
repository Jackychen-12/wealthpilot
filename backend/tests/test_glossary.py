"""少记一点、少猜一点：专业的词都有一句大白话，命令可以用中文叫，打错了有人提醒。"""

import io

from fastapi.testclient import TestClient
from rich.console import Console

from tests.test_tui import ApiBackend, run_api
from wealthpilot import tui
from wealthpilot.main import app
from wealthpilot.services import channels, glossary


def test_every_term_has_a_plain_sentence_and_can_be_found_by_its_other_names():
    for name, (plain, how, _aliases) in glossary.TERMS.items():
        assert 6 <= len(plain) <= 60 and plain.endswith("。") and how, name
    assert glossary.lookup("封板率")[0] == "封板率" and glossary.lookup("追高")[0] == "追涨" and glossary.lookup("越跌越买")[0] == "亏损加仓"
    assert glossary.lookup("dcf")[0] == "反向 DCF" and glossary.lookup("说话方式")[0] == "回答风格" and glossary.lookup("情绪刻度")[0] == "市场情绪"
    assert glossary.lookup("pe 分位")[0] == "历史分位" and glossary.lookup("不存在的词") is None and glossary.lookup("  ") is None
    out = glossary.explain("处置效应")
    assert out.startswith("处置效应：赚钱的股票急着卖，亏钱的股票一直拿着。") and "也叫：拿不住" in out
    assert "没有「量子纠缠」这个词条" in glossary.explain("量子纠缠") and "封板率" in glossary.explain("")


def test_the_words_used_on_screen_are_all_in_the_glossary():
    """界面上新换的专业叫法，都得查得到解释 —— 不然就是把学习成本转嫁给了用户。"""
    for word in ("封板率", "炸板", "连板", "昨日涨停溢价", "市场情绪", "涨停题材", "龙虎榜", "席位", "隐含增长率", "折现率", "超额收益", "胜率", "盈亏比",
                 "追涨", "亏损加仓", "处置效应", "验证点", "建议单", "每日简报", "大盘复盘", "回答风格", "备用模型", "PMI", "LPR", "中美利差"):
        assert glossary.lookup(word) is not None, word
    client = TestClient(app)
    assert client.get("/api/settings/glossary", params={"q": "连板梯队"}).json()["term"] == "连板"
    assert len(client.get("/api/settings/glossary").json()) == len(glossary.TERMS) and client.get("/api/settings/glossary", params={"q": "zzz"}).status_code == 404


async def test_chinese_words_work_as_commands_in_the_terminal_and_typos_get_a_hint():
    app_, out = run_api({("GET", "/api/market/macro"): {"indicators": [], "rates": []}})
    await app_.handle("宏观")                                       # 整句话正好是这个词：当命令，不调用模型
    assert app_.backend.sent == [("GET", "/api/market/macro", None)] and app_.backend.calls == []
    await app_.handle("/宏观")
    assert len(app_.backend.sent) == 2
    await app_.handle("/glossary 封板率")
    assert "涨停之后一直封到收盘的比例" in out.getvalue()
    await app_.handle("/recpa")
    assert "是不是想用 /recap" in out.getvalue()
    await app_.handle("/zzzzzz")
    assert "/help all 看全部" in out.getvalue()
    await app_.handle("/help")
    assert "中文词直接打就行" in out.getvalue() and "/glossary 封板率" in out.getvalue()


async def test_a_question_that_merely_contains_a_command_word_is_still_a_question():
    events = [{"type": "done", "content": "结论：……", "meta": {"status": "passed"}}]
    out = io.StringIO()
    app_ = tui.App(ApiBackend({}), Console(file=out, width=120, force_terminal=False))
    app_.backend.events = events
    await app_.handle("帮我复盘一下宁德时代上周为什么跌")
    assert app_.backend.calls[0]["message"] == "帮我复盘一下宁德时代上周为什么跌" and app_.backend.sent == []


async def test_the_phone_takes_plain_words_and_explains_terms(monkeypatch):
    from wealthpilot.services import macro

    class Sink:
        def __init__(self):
            self.sent = []

        async def send(self, chat_id, text, buttons=None):
            self.sent.append(text)

    async def snapshot():
        return {"indicators": [], "rates": []}
    monkeypatch.setattr(macro, "snapshot", snapshot)
    asked = []

    async def ask(question, history, conversation, depth="auto", **kw):
        asked.append(question)
        yield {"type": "done", "content": "结论", "meta": {"status": "passed"}}
    channels.set_owner("me", "feishu")
    try:
        sink = Sink()
        bot = channels.Bot(sink, ask=ask, channel="feishu")
        await bot.message("me", "宏观")
        assert "取不到宏观数据" in sink.sent[-1] and asked == []
        await bot.message("me", "解释 封板率")
        assert sink.sent[-1].startswith("封板率：涨停之后一直封到收盘的比例。") and asked == []
        await bot.message("me", "状态")
        assert "模型：" in sink.sent[-1]
        await bot.message("me", "帮助")
        assert "发下面这些词" in sink.sent[-1] and "解释 封板率" in sink.sent[-1]
        await bot.message("me", "宏观环境对白酒有什么影响")              # 只是包含"宏观"两个字：照常研究
        assert asked == ["宏观环境对白酒有什么影响"]
    finally:
        channels.set_owner(None, "feishu")


def test_command_line_help_is_grouped_by_purpose_and_lists_every_command():
    import subprocess
    import sys

    from wealthpilot.__main__ import OVERVIEW, OVERVIEW_ALL
    shown = subprocess.run([sys.executable, "-m", "wealthpilot", "--help"], capture_output=True, text=True).stdout
    assert "第一次用" in shown and "进去之后常用的五件事" in shown and "出了问题" in shown and len(shown.splitlines()) <= 40   # 连同启动参数一屏看完
    everything = subprocess.run([sys.executable, "-m", "wealthpilot", "help"], capture_output=True, text=True).stdout
    assert everything.strip() == OVERVIEW_ALL and "connectors" in everything and "connectors" not in OVERVIEW        # 不常用的收在全表里
    assert "positional arguments" not in shown and "{run,setup" not in shown                     # argparse 那张平铺的表收起来了
    bash = subprocess.run([sys.executable, "-m", "wealthpilot", "completion", "bash"], capture_output=True, text=True).stdout
    commands = bash.split('compgen -W "')[1].split('"')[0].split()
    missing = [c for c in commands if c not in OVERVIEW + OVERVIEW_ALL and c not in ("chat", "tui")]   # 旧入口不再往外介绍
    assert not missing, f"帮助里漏了这些命令：{missing}"
    one = subprocess.run([sys.executable, "-m", "wealthpilot", "model", "--help"], capture_output=True, text=True).stdout
    assert "fallback" in one                                                                    # 单个命令的帮助照旧


def test_workflow_files_only_use_contexts_that_exist_where_they_are_written():
    """GitHub 对工作流文件很严：job 这一级的 env 里拿不到 runner（运行器还没分配），写了整个文件就作废，而且只在推上去之后才知道。"""
    from pathlib import Path

    import yaml
    folder = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    files = sorted(folder.glob("*.yml"))
    assert {f.name for f in files} >= {"deploy.yml", "test.yml", "daily.yml"}
    for file in files:
        flow = yaml.safe_load(file.read_text(encoding="utf-8"))
        assert isinstance(flow.get("jobs"), dict) and (True in flow or "on" in flow), file.name       # YAML 把 on 读成 True
        for value in (flow.get("env") or {}).values():
            assert "runner." not in str(value) and "steps." not in str(value), file.name
        for name, job in flow["jobs"].items():
            for value in (job.get("env") or {}).values():
                assert "runner." not in str(value) and "steps." not in str(value), f"{file.name} · {name}"
            assert "runner." not in str(job.get("if", "")), f"{file.name} · {name}"
            for step in job.get("steps") or []:
                assert ("run" in step) != ("uses" in step), f"{file.name} · {name}：每一步要么 run 要么 uses"


def test_every_term_a_page_offers_to_explain_actually_has_an_entry():
    """页面上列出来的词如果词典里没有，那一行会悄悄少一个词 —— 用户以为没得查。"""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "workbench" / "src"
    offered: dict[str, str] = {}
    for file in src.rglob("*.tsx"):
        for group in re.findall(r"(?:terms|words)=\{\[([^\]]+)\]\}", file.read_text(encoding="utf-8")):
            for word in re.findall(r"'([^']+)'", group):
                offered[word] = file.name
    assert len(offered) >= 40
    missing = {w: f for w, f in offered.items() if w not in glossary.TERMS}
    assert not missing, f"词典里没有这些词：{missing}"
    assert len({f for f in offered.values()}) >= 15                      # 不只是新页面：旧页面也都挂上了
