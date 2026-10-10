"""外部 MCP 连接器：只读约束、配置加载、凭据不外泄，以及一次真实的 stdio 连通。"""

import json
import os
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from wealthpilot.main import app
from wealthpilot.services import connectors as svc


@pytest.mark.parametrize("name", [
    "place_order", "cancel_order", "submit_trade", "buy_stock", "sell", "transfer_funds",
    "withdraw_cash", "modify_order", "get_and_place_order", "order", "下单", "撤单", "trade",
])
def test_trading_and_fund_movement_tools_are_blocked(name):
    assert svc.classify_tool(name)[0] is False


@pytest.mark.parametrize("name", [
    "get_positions", "get_order_history", "query_trades", "list_orders", "get_account_balance",
    "search_news", "get_quote", "查询持仓",
])
def test_read_only_queries_are_allowed(name):
    assert svc.classify_tool(name)[0] is True


def test_server_declared_write_tool_is_blocked_even_with_innocent_name():
    assert svc.classify_tool("sync_account", read_only_hint=False)[0] is False
    assert svc.classify_tool("rebalance", "按目标权重自动下单调仓")[0] is False


async def test_blocked_tool_cannot_be_called_directly():
    with pytest.raises(PermissionError):
        await svc.call_tool(svc.Connector(name="x", label="x"), "place_order", {})


@pytest.fixture
def config(monkeypatch, tmp_path):
    path = tmp_path / "connectors.json"
    monkeypatch.setattr(svc, "config_path", lambda: path)
    svc._tool_cache.clear()

    def write(items):
        path.write_text(json.dumps({"connectors": items}), encoding="utf-8")
    return write


def test_public_view_never_exposes_token_or_command(config, monkeypatch):
    monkeypatch.setenv("BROKER_TOKEN", "super-secret-value")
    config([{"name": "broker", "label": "券商", "kind": "broker", "url": "https://b.example/mcp", "auth_env": "BROKER_TOKEN"},
            {"name": "local", "label": "本机", "transport": "stdio", "command": "/usr/bin/secret-tool", "args": ["--key", "abc"]},
            {"name": "bad name!", "label": "非法名字会被忽略"}])
    body = TestClient(app).get("/api/connectors").text
    assert "super-secret-value" not in body and "secret-tool" not in body and "abc" not in body
    listed = json.loads(body)["connectors"]
    assert [c["name"] for c in listed] == ["broker", "local"]
    assert listed[0]["auth"] == "已配置"


def test_missing_token_is_reported_not_hidden(config, monkeypatch):
    monkeypatch.delenv("BROKER_TOKEN", raising=False)
    config([{"name": "broker", "label": "券商", "url": "https://b.example/mcp", "auth_env": "BROKER_TOKEN"}])
    assert "还没填令牌（BROKER_TOKEN）" in TestClient(app).get("/api/connectors").json()["connectors"][0]["auth"]


def test_no_api_to_create_or_edit_connectors():
    client = TestClient(app)
    assert client.post("/api/connectors", json={"name": "x"}).status_code == 405
    assert client.put("/api/connectors/x", json={}).status_code in (404, 405)


def test_unreachable_connector_reports_failure(config):
    config([{"name": "dead", "label": "连不上", "transport": "stdio", "command": "/nonexistent/binary"}])
    result = TestClient(app).post("/api/connectors/dead/test").json()
    assert result["ok"] is False and result["tools"] == []


async def test_real_stdio_connection_lists_tools_and_feeds_the_agent(config):
    """把本项目自己的 MCP Server 当外部服务连一次 —— 整条链路的真实验证。"""
    # 子进程不继承这边的环境变量（MCP 的 stdio 客户端只给一份最小环境），得显式把数据目录指到测试用的临时目录，
    # 否则它读的是开发者自己的 backend/.env，日志也会写到真实的数据目录里
    config([{"name": "self", "label": "自测", "transport": "stdio", "command": "/usr/bin/env",
             "args": [f"WEALTHPILOT_HOME={os.environ['WEALTHPILOT_HOME']}", f"DB_PATH={os.environ['DB_PATH']}", sys.executable, "-m", "wealthpilot", "mcp"]}])
    connector = svc.load_connectors()[0]
    tools = await svc.list_tools(connector)
    assert len(tools) == 59 and all(t["allowed"] for t in tools if t["name"].startswith("get_"))

    definitions, index = await svc.agent_tools()
    assert "ext_self_get_stock_quote" in index
    exposed = next(d for d in definitions if d["name"] == "ext_self_get_stock_quote")
    assert exposed["description"].startswith("[外部数据源：自测]")


async def test_agent_routes_external_tool_calls_to_the_connector(monkeypatch):
    from wealthpilot.services.agents import base

    seen = {}

    async def fake_call(connector, tool, arguments):
        seen.update(connector=connector.name, tool=tool, arguments=arguments)
        return '{"positions": []}'

    monkeypatch.setattr(base, "call_external", fake_call)
    agent = base.BaseAgent("stock", [{"name": "ext_broker_get_positions"}], "", None, "m")
    agent.external = {"ext_broker_get_positions": (svc.Connector(name="broker", label="券商"), "get_positions")}
    assert await agent._run_tool("ext_broker_get_positions", {"account": "1"}) == '{"positions": []}'
    assert seen == {"connector": "broker", "tool": "get_positions", "arguments": {"account": "1"}}


# ── 现成的服务、命令行接入、令牌从哪读 ─────────────────────────────

def test_tools_that_add_remove_or_manage_things_are_blocked_too():
    for name in ("mx_self_select_manage", "add_watchlist", "remove_alert", "update_position_note", "set_price_alert", "删除自选股"):
        assert svc.classify_tool(name)[0] is False, name
    assert svc.classify_tool("portfolio_helper", "添加一只股票到自选")[0] is False            # 名字看不出来，说明里写了
    for name in ("mx_data_query", "finance_news_search", "get_address_book", "diagnose_stock", "hotspot_discovery"):
        assert svc.classify_tool(name)[0] is True, name                                       # address 里的 add 不算


def test_a_token_written_to_the_env_file_is_actually_found(monkeypatch):
    from wealthpilot.routes.config import ENV_FILE
    monkeypatch.delenv("DEMO_MCP_TOKEN", raising=False)
    c = svc.Connector(name="demo", label="演示", url="https://x.example.com/mcp", auth_env="DEMO_MCP_TOKEN")
    assert svc.token_for(c) == "" and "还没填令牌" in c.public()["auth"]
    before = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else None
    try:
        ENV_FILE.write_text('OTHER=1\nDEMO_MCP_TOKEN="tok-from-file"\n', encoding="utf-8")
        assert svc.token_for(c) == "tok-from-file" and c.public()["auth"] == "已配置"          # 以前只看进程环境变量，写进 .env 读不到
        monkeypatch.setenv("DEMO_MCP_TOKEN", "tok-from-env")
        assert svc.token_for(c) == "tok-from-env"
        assert "tok-from" not in json.dumps(c.public(), ensure_ascii=False)                    # 令牌本身不往外给
    finally:
        ENV_FILE.unlink(missing_ok=True) if before is None else ENV_FILE.write_text(before, encoding="utf-8")


def test_ready_made_services_can_be_added_tested_and_removed_from_the_command_line(monkeypatch):
    import argparse

    from wealthpilot import cli
    from wealthpilot.routes.config import ENV_FILE
    from wealthpilot.services.connector_presets import PRESETS

    def run(*words, **flags):
        out: list[str] = []
        args = argparse.Namespace(action=words[0] if words else None, name=words[1] if len(words) > 1 else None,
                                  url=flags.get("url"), token=flags.get("token"), rename=flags.get("rename"))
        return cli.cmd_connectors(args, out=out.append), "\n".join(out)
    path = svc.config_path()
    saved = path.read_text(encoding="utf-8") if path.exists() else None
    env = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else None
    monkeypatch.delenv("MX_MCP_TOKEN", raising=False)
    try:
        path.unlink(missing_ok=True)
        assert "还没有接" in run()[1]
        code, text = run("gallery")
        assert code == 0 and all(p["label"] in text for p in PRESETS) and "没有一家实际连过" in text and "社区" in text and "官方" in text
        code, text = run("add", "longbridge")
        assert code == 1 and "现在接不了" in text and "已经内置" in text                         # 接不了的如实说，并告诉用户不接也行
        code, text = run("add", "ifind")
        assert code == 2 and "--url" in text
        assert run("add", "ifind", url="ftp://x")[0] == 1 and run("add", "nope")[0] == 2
        code, text = run("add", "mx", token="auth-token-0000")
        assert code == 0 and "只读" in text and "auth-token" not in text and "connectors test mx" in text
        mx = svc.load_connectors()[0]
        assert (mx.name, mx.url, mx.enabled) == ("mx", "http://localhost:9000/mcp", True) and svc.token_for(mx) == "auth-token-0000"
        run("add", "custom", url="https://data.example.com/mcp", rename="broker_ro")
        assert [c.name for c in svc.load_connectors()] == ["mx", "broker_ro"] and "broker_ro" in run()[1]

        async def tools(connector, refresh=False):
            return [{"name": "mx_data_query", "allowed": True, "reason": "只读查询"}, {"name": "mx_self_select_manage", "allowed": False, "reason": "交易 / 资金类工具，已屏蔽"}]
        monkeypatch.setattr(svc, "list_tools", tools)
        code, text = run("test", "mx")
        assert code == 0 and "1 个工具可以给 AI 用，1 个被屏蔽" in text and "✗ mx_self_select_manage" in text

        async def down(connector, refresh=False):
            raise ExceptionGroup("unhandled errors in a TaskGroup", [httpx.ConnectError("All connection attempts failed")])
        monkeypatch.setattr(svc, "list_tools", down)
        code, text = run("test", "mx")
        assert code == 1 and "服务没有开着，或者地址不对" in text and "TaskGroup" not in text      # 不把库的内部报错甩给用户
        assert run("remove", "mx")[0] == 0 and [c.name for c in svc.load_connectors()] == ["broker_ro"] and "没有接过" in run("remove", "mx")[1]
        listed = TestClient(app).get("/api/connectors/presets").json()
        assert [p["key"] for p in listed] == [p["key"] for p in PRESETS] and listed[0]["status_label"] == "可以接" and "connector" not in listed[0]
    finally:
        path.unlink(missing_ok=True) if saved is None else path.write_text(saved, encoding="utf-8")
        ENV_FILE.unlink(missing_ok=True) if env is None else ENV_FILE.write_text(env, encoding="utf-8")
