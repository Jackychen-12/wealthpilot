"""工具直调路由：工作台功能页与 Agent 共用同一批工具。"""

from fastapi.testclient import TestClient

from wealthpilot.main import app
from wealthpilot.routes import tools as tools_route

client = TestClient(app)


def test_lists_all_agent_tools_by_group():
    listed = client.get("/api/tools").json()
    assert len(listed) == 37
    assert {t["group"] for t in listed} == {"fundamental", "valuation", "price", "industry", "screener", "portfolio", "fund", "review"}


def test_unknown_tool_is_404_and_missing_argument_is_422():
    assert client.post("/api/tools/delete_everything", json={}).status_code == 404
    resp = client.post("/api/tools/backtest_rule", json={"fund_code": "110011"})
    assert resp.status_code == 422 and "triggers" in resp.json()["detail"]


def test_json_output_is_parsed_and_empty_result_is_not_ok(monkeypatch):
    async def fake(name, *args, **kwargs):
        return '{"hhi": 0.5}' if name == "compute_concentration" else "当前没有持仓，无法穿透。"

    monkeypatch.setattr(tools_route, "execute_tool", fake)
    good = client.post("/api/tools/compute_concentration", json={}).json()
    assert good["ok"] is True and good["data"] == {"hhi": 0.5}
    # 工具"没取到数据"时返回的是一句话，不能当成功
    empty = client.post("/api/tools/lookthrough_portfolio", json={}).json()
    assert empty["ok"] is False and "没有持仓" in empty["data"]


def test_tool_runs_only_on_the_callers_own_holdings(monkeypatch):
    seen = {}

    async def fake(name, inputs, holdings, *args, **kwargs):
        seen["user_ids"] = {h.user_id for h in holdings}
        return "{}"

    monkeypatch.setattr(tools_route, "execute_tool", fake)
    client.post("/api/tools/get_portfolio_overview", json={})  # 匿名
    assert seen["user_ids"] <= {0}
