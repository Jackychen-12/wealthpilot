"""外部 MCP 连接器：只读约束、配置加载、凭据不外泄，以及一次真实的 stdio 连通。"""

import json
import os
import sys

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
    assert "缺少环境变量 BROKER_TOKEN" in TestClient(app).get("/api/connectors").json()["connectors"][0]["auth"]


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
    assert len(tools) == 58 and all(t["allowed"] for t in tools if t["name"].startswith("get_"))

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
