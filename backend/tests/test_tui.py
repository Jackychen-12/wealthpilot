"""终端入口：命令解析、本机后端直连、研究过程渲染。不联网、不调模型。"""

import io

import pytest
from rich.console import Console

from wealthpilot import tui


def test_screen_shorthand_maps_to_screener_criteria():
    assert tui.parse_screen("pe<15 roe>15 mv>200 白酒") == {
        "limit": 20, "pe_max": 15.0, "roe_min": 15.0, "mv_min_yi": 200.0, "industry": "白酒"}
    assert tui.parse_screen("mv<500 rev>=30 profit>30 chg>-2") == {
        "limit": 20, "mv_max_yi": 500.0, "revenue_yoy_min": 30.0, "profit_yoy_min": 30.0, "change_min": -2.0}
    with pytest.raises(ValueError, match="roe 只支持"):
        tui.parse_screen("roe<5")
    with pytest.raises(ValueError, match="不认识的条件"):
        tui.parse_screen("eps>1")


def test_citations_are_shortened_for_the_terminal():
    assert tui.cite("营收 100 亿 [E-5ea7c0ffee12]。") == "营收 100 亿 `5ea7`。"


class FakeBackend(tui.Backend):
    label = "测试"

    def __init__(self, events):
        self.events = events
        self.calls: list[dict] = []

    async def chat(self, message, history, conversation_id, *, depth="auto", rewrite_of=None):
        self.calls.append({"message": message, "depth": depth, "rewrite_of": rewrite_of})
        for e in self.events:
            yield e

    async def close(self):
        pass


def run_app(events):
    out = io.StringIO()
    app = tui.App(FakeBackend(events), Console(file=out, width=120, force_terminal=False))
    return app, out


async def test_research_renders_process_answer_checkpoints_and_proposals():
    cp = {"name": "贵州茅台", "code": "600519", "metric_label": "营收同比", "op": ">=", "threshold": 0.0, "baseline_value": 1.3,
          "baseline_as_of": "2026-06-30", "status": "pending", "actual_value": None, "actual_as_of": "", "due": "下一期财报"}
    proposal = {"id": 3, "action_label": "加仓", "name": "贵州茅台", "code": "600519", "shares": 100, "price_ref": 1258.62,
                "reason": "估值处于低位", "invalidation": "营收同比转负", "status": "proposed", "exec_shares": None, "exec_price": None}
    app, out = run_app([
        {"type": "resolved", "securities": [{"name": "贵州茅台", "code": "600519"}]},
        {"type": "plan", "intent": "个股深度研究", "tasks": [{"agent": "valuation", "label": "⚖️ 估值", "goal": "研究估值"}]},
        {"type": "evidence", "evidence": {"id": "E-5ea7c0ffee12", "tool": "get_valuation_history", "input": {"code": "600519"}, "output": "PE 19.32"}},
        {"type": "task_done", "agent": "valuation", "status": "completed", "tools": ["get_valuation_history"]},
        {"type": "critic", "gate": "answer", "attempt": 1, "passed": False, "issues": ["以下数字未出现在工具返回中：42"]},
        {"type": "checkpoints", "items": [cp], "proposals": [proposal]},
        {"type": "done", "content": "## 结论\nPE 19.32 [E-5ea7c0ffee12]", "meta": {"status": "passed"}},
    ])
    await app.research("帮我分析一下贵州茅台")
    text = out.getvalue()
    for expected in ("已解析", "600519", "个股深度研究", "打回", "PE 19.32", "已通过校验", "营收同比 ≥ 0%", "下一期财报 核对",
                     "#3", "加仓", "失效条件：营收同比转负", "/approve"):
        assert expected in text, expected
    assert len(app.history) == 2 and app.evidence[0]["tool"] == "get_valuation_history"

    out.truncate(0)
    await app.cmd_evidence("5ea7")
    assert "PE 19.32" in out.getvalue()


async def test_unpublished_answers_do_not_enter_the_conversation_and_errors_do_not_crash():
    app, out = run_app([{"type": "done", "content": "证据不足", "meta": {"status": "rejected"}}])
    assert await app.handle("随便问问") is True
    assert app.history == [] and "未通过校验" in out.getvalue()
    assert await app.handle("/nope") is True and "没有这个命令" in out.getvalue()
    assert await app.handle("/screen eps>1") is True and "不认识的条件" in out.getvalue()
    assert await app.handle("/quit") is False


async def test_local_backend_serves_the_api_in_process():
    backend = tui.LocalBackend()
    try:
        assert (await backend.request("GET", "/health"))["status"] == "ok"
        assert isinstance(await backend.request("GET", "/api/checkpoints/scorecard"), dict)
        with pytest.raises(RuntimeError, match="未知工具"):
            await backend.tool("delete_everything")
    finally:
        await backend.close()
        from wealthpilot.main import app
        app.dependency_overrides.clear()


# ── 对话：深度、改写、调出历史 ──────────────────────────

LONG = {"type": "done", "content": "## 结论\n基本面稳。\n" + "正文。" * 200,
        "meta": {"status": "passed", "message_id": 42, "summary": {"conclusion": "基本面稳，估值不贵。", "stance": "中性偏多", "truncated": False}}}


async def test_depth_and_rewrite_reach_the_backend():
    app, out = run_app([{"type": "plan", "intent": "个股深度研究", "tasks": [], "eta_seconds": 40}, LONG])
    await app.handle("/quick 茅台贵不贵")
    await app.handle("/deep 帮我分析茅台")
    await app.handle("/depth quick")
    await app.handle("随便问一句")
    assert [c["depth"] for c in app.backend.calls] == ["quick", "deep", "quick"]
    text = out.getvalue()
    assert "预计约 40 秒" in text and "中性偏多" in text and "基本面稳，估值不贵。" in text and "/rewrite" in text
    # 改写：带上上一次研究的消息编号，不重新取证
    await app.handle("/rewrite 只讲风险")
    assert app.backend.calls[-1] == {"message": "只讲风险", "depth": "quick", "rewrite_of": 42}
    assert await app.handle("/depth turbo") is True and "只能是" in out.getvalue()


async def test_rewrite_needs_something_to_rewrite():
    app, out = run_app([LONG])
    await app.handle("/rewrite 更短一点")
    assert "还没有可以改写的研究" in out.getvalue() and app.backend.calls == []


class ApiBackend(FakeBackend):
    """把请求记下来并按路径回放，测命令怎么调接口。"""

    def __init__(self, routes):
        super().__init__([])
        self.routes, self.sent = routes, []

    async def request(self, method, path, **kw):
        self.sent.append((method, path, kw.get("json")))
        return self.routes[(method, path)]


def run_api(routes, answers=()):
    out = io.StringIO()
    app = tui.App(ApiBackend(routes), Console(file=out, width=140, force_terminal=False))
    replies = list(answers)

    async def ask(prompt):
        out.write(prompt)
        return replies.pop(0)
    app.ask = ask
    return app, out


async def test_history_can_be_recalled_and_continued():
    app, out = run_api({("GET", "/api/research/history/7"): {
        "id": 7, "question": "帮我分析茅台", "answer": "## 结论\n稳。", "created_at": "2026-10-01T09:30:00",
        "meta": {"evidence": [{"id": "E-5ea7c0ffee12", "tool": "get_stock_quote", "input": {}, "output": "1258"}]}}})
    await app.handle("/history 7")
    assert "帮我分析茅台" in out.getvalue() and app.last_message_id == 7
    assert app.history[0]["content"] == "帮我分析茅台" and app.evidence[0]["tool"] == "get_stock_quote"


async def test_add_previews_then_asks_before_writing():
    rows = [{"ok": True, "name": "贵州茅台", "code": "600519", "shares": 100.0, "cost": 1500.0, "line": "贵州茅台 100 1500", "problem": "", "asset_type": "stock"},
            {"ok": False, "name": "", "code": "", "shares": None, "cost": None, "line": "五粮液 300", "problem": "没看到成本价", "asset_type": ""}]
    routes = {("POST", "/api/portfolio/parse"): {"rows": rows}, ("POST", "/api/portfolio/batch"): {"added": 1, "skipped": []}}
    app, out = run_api(routes, answers=["n"])
    await app.handle("/add 贵州茅台 100 1500; 五粮液 300")
    assert app.backend.sent[0][2] == {"text": "贵州茅台 100 1500\n五粮液 300"}
    assert "没看到成本价" in out.getvalue() and "已取消" in out.getvalue()
    assert not any(path == "/api/portfolio/batch" for _, path, _ in app.backend.sent)      # 没点头就不写
    app, out = run_api(routes, answers=["y"])
    await app.handle("/add 贵州茅台 100 1500; 五粮液 300")
    assert app.backend.sent[-1] == ("POST", "/api/portfolio/batch", {"rows": [rows[0]]}) and "已添加 1 条" in out.getvalue()


async def test_tasks_and_alerts_commands():
    listing = {"items": [], "metrics": [], "daily_runs_max": 6, "running": True}
    routes = {("POST", "/api/automations"): {"id": 1, "kind": "task", "schedule": "工作日 08:30", "prompt": "诊断一下我的持仓", "next_run_at": "2026-10-07T08:30:00"},
              ("GET", "/api/automations"): listing,
              ("GET", "/api/securities/search"): [{"code": "600519", "name": "贵州茅台", "asset_type": "stock"}]}
    app, out = run_api(routes)
    await app.handle("/tasks add 工作日 08:30 | 诊断一下我的持仓")
    assert app.backend.sent[0][2] == {"kind": "task", "schedule": "工作日 08:30", "prompt": "诊断一下我的持仓"}
    assert "已建好" in out.getvalue() and "10-07 08:30" in out.getvalue()
    await app.handle("/tasks add 没有竖线")
    assert "用法" in out.getvalue()
    await app.handle("/tasks")
    assert "只在 WealthPilot 开着时运行" in out.getvalue()

    routes[("POST", "/api/automations")] = {"id": 2, "kind": "alert", "condition": "贵州茅台 最新价 ≤ 1350元", "current": 1258.6, "unit": "元"}
    await app.handle("/alert 茅台 price<=1350")
    assert app.backend.sent[-1][2] == {"kind": "alert", "code": "600519", "name": "贵州茅台", "metric": "price", "op": "<=", "threshold": 1350.0}
    assert "现在是 1258.6元" in out.getvalue()
    await app.handle("/alert 茅台 贵了告诉我")
    assert "price 价格" in out.getvalue()


async def test_skills_draft_is_shown_and_saved_only_on_yes():
    draft = {"content": "---\nname: my-check\n---\n# 我的方法\n", "skill": {"name": "my-check", "label": "我的方法"}, "problems": []}
    routes = {("POST", "/api/skills/draft"): draft, ("PUT", "/api/skills/my-check"): {"name": "my-check"},
              ("GET", "/api/skills/gallery"): [{"label": "银行股体检", "name": "bank-check", "description": "看银行", "installed": True}]}
    app, out = run_api(routes, answers=[""])
    await app.handle("/skills draft 买消费股前看提价能力和渠道库存")
    assert "name: my-check" in out.getvalue() and "没有保存" in out.getvalue()
    assert not any(method == "PUT" for method, _, _ in app.backend.sent)
    app, out = run_api(routes, answers=["y"])
    await app.handle("/skills draft 买消费股前看提价能力和渠道库存")
    assert app.backend.sent[-1] == ("PUT", "/api/skills/my-check", {"content": draft["content"]})
    await app.handle("/skills gallery")
    assert "银行股体检" in out.getvalue() and "已装" in out.getvalue()


async def test_help_is_grouped_and_covers_every_command():
    listed = [name for _, names in tui.HELP_GROUPS for name in names]
    assert sorted(listed) == sorted(tui.COMMANDS) and len(listed) == len(set(listed))
    app, out = run_app([])
    for name in tui.COMMANDS:
        if name not in ("/quit", "/help"):
            assert hasattr(app, f"cmd_{name[1:]}"), name
    await app.handle("/help")
    assert "自己干活" in out.getvalue() and "/rewrite" in out.getvalue()


async def test_first_run_setup_walks_model_then_holdings():
    routes = {("GET", "/api/onboarding"): {"steps": [{"key": "model", "done": False}, {"key": "data", "done": False}]},
              ("PUT", "/api/settings"): {}, ("POST", "/api/settings/test"): {"ok": True, "provider": "deepseek", "model": "deepseek-chat"},
              ("POST", "/api/sample"): {}}
    app, out = run_api(routes, answers=["1", "s"])

    async def secret(prompt):
        return "sk-test-not-a-real-key"
    app.ask_secret = secret
    await app.setup()
    assert app.backend.sent[1] == ("PUT", "/api/settings", {"ai_provider": "deepseek", "deepseek_api_key": "sk-test-not-a-real-key"})
    text = out.getvalue()
    assert "模型可用" in text and "已载入示例" in text and "问第一个问题" in text
    assert "sk-test-not-a-real-key" not in text                      # Key 不回显
    # 都配好了就不打扰
    app, out = run_api({("GET", "/api/onboarding"): {"steps": [{"key": "model", "done": True}, {"key": "data", "done": True}]}})
    await app.setup()
    assert out.getvalue() == ""


async def test_first_run_setup_offers_the_same_services_as_the_setup_command():
    from wealthpilot.services import providers
    routes = {("GET", "/api/onboarding"): {"steps": [{"key": "model", "done": False}, {"key": "data", "done": True}]},
              ("PUT", "/api/settings"): {}, ("POST", "/api/settings/test"): {"ok": False, "error": "模型账户余额不足，这次没法研究。"}}

    async def secret(prompt):
        return "zp-test-not-a-real-key"
    zhipu = str([p["key"] for p in providers.PRESETS].index("zhipu") + 1)
    app, out = run_api(routes, answers=[zhipu, ""])           # 选智谱，模型名回车用默认的
    app.ask_secret = secret
    await app.setup()
    assert app.backend.sent[1] == ("PUT", "/api/settings", {"ai_provider": "openai", "openai_api_key": "zp-test-not-a-real-key",
                                                            "openai_model": "glm-4-flash", "openai_base_url": "https://open.bigmodel.cn/api/paas/v4"})
    text = out.getvalue()
    assert all(p["label"] in text for p in providers.PRESETS) and "调不通：模型账户余额不足" in text and "zp-test" not in text
    # 自己填地址：自己机器上跑的服务通常不要 Key
    async def no_key(prompt):
        return ""
    app, out = run_api(routes, answers=[str(len(providers.PRESETS) + 1), "http://localhost:8080/v1", "my-model"])
    app.ask_secret = no_key
    await app.setup()
    assert app.backend.sent[1] == ("PUT", "/api/settings", {"ai_provider": "openai", "openai_model": "my-model", "openai_base_url": "http://localhost:8080/v1"})
    app, out = run_api(routes, answers=[str(len(providers.PRESETS) + 1), "http://localhost:8080/v1", ""])       # 没给模型名：不写
    app.ask_secret = no_key
    await app.setup()
    assert [s[0] for s in app.backend.sent] == ["GET"] and "没填全" in out.getvalue()
    ollama = str([p["key"] for p in providers.PRESETS].index("ollama") + 1)
    app, out = run_api(routes, answers=[ollama, "qwen2.5:7b"])
    app.ask_secret = no_key
    await app.setup()
    assert app.backend.sent[1] == ("PUT", "/api/settings", {"ai_provider": "openai", "openai_model": "qwen2.5:7b", "openai_base_url": "http://localhost:11434/v1"})
