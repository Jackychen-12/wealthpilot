"""全端点冒烟测试。

写这个文件的直接原因：多租户改造给 13 处查询加 user_id 过滤时，
alerts.py 的多行函数签名没被匹配到 —— 函数体用了 user_id，签名里却没有，
`/api/alerts` 直接 500。而当时 168 个测试全绿，因为没有一条碰过这个端点。

所以这里不针对具体业务断言，只做一件事：**把每个无路径参数的 GET 端点都调一遍，
断言不是 5xx**。这类"改了签名忘了改调用"的错误，一条冒烟测试就能全兜住。
"""

import pytest
from fastapi.testclient import TestClient

from wealthpilot.main import app

client = TestClient(app, raise_server_exceptions=False)


def _parameterless_get_paths() -> list[str]:
    """枚举所有不含路径参数的 GET 路由。"""
    paths = []
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        if "GET" not in methods or "{" in path:
            continue
        paths.append(path)
    return sorted(set(paths))


ALL_GET_PATHS = _parameterless_get_paths()


def test_route_enumeration_is_not_empty():
    """如果枚举逻辑失效，下面的参数化会静默变成零条用例。"""
    assert len(ALL_GET_PATHS) >= 15, f"只枚举到 {len(ALL_GET_PATHS)} 个 GET 端点，疑似枚举失效"


@pytest.mark.parametrize("path", ALL_GET_PATHS)
def test_get_endpoint_does_not_500(path):
    resp = client.get(path)
    assert resp.status_code < 500, f"{path} → {resp.status_code}\n{resp.text[:300]}"


@pytest.mark.parametrize("path", ALL_GET_PATHS)
def test_get_endpoint_does_not_500_when_authenticated(path):
    """带上合法令牌再跑一遍 —— 匿名路径与登录路径的代码分支不同。"""
    reg = client.post(
        "/api/auth/register",
        json={"username": "smoke_user", "password": "pw-smoke-123", "email": "s@t.com"},
    )
    if reg.status_code != 200:
        reg = client.post(
            "/api/auth/login", json={"username": "smoke_user", "password": "pw-smoke-123"}
        )
    token = reg.json().get("access_token", "")
    resp = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code < 500, f"{path} (authed) → {resp.status_code}\n{resp.text[:300]}"


def test_alerts_endpoint_specifically():
    """回归：user_id 缺参那次的直接受害者。"""
    assert client.get("/api/alerts").status_code == 200
    assert client.get("/api/alerts?threshold=-5").status_code == 200


class TestInsufficientDataPaths:
    """有持仓、但历史样本不足时的路径。

    calculate_overview 在样本不足时返回 None（而非假装是 0），而多处格式化用的是
    `overview.get(k, 0):.2f` —— 默认值只在键不存在时生效，键存在值为 None 时
    照样把 None 传给 format()。这类崩溃只在"有持仓 + 无历史"的组合下出现，
    空组合和完整数据都测不到。
    """

    @staticmethod
    def _user_with_historyless_holding() -> dict:
        import uuid

        u = f"nd_{uuid.uuid4().hex[:8]}"
        reg = client.post(
            "/api/auth/register",
            json={"username": u, "password": "pw-nd-123", "email": f"{u}@t.com"},
        )
        headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
        # 个股没有场外净值序列，nav_history 必然为空
        client.post("/api/portfolio", headers=headers, json={
            "asset_type": "stock", "fund_code": "600519", "fund_name": "贵州茅台",
            "shares": 10, "cost_price": 1000, "buy_date": "2026-01-01",
            "category": "equity",
        })
        return headers

    def test_overview_survives_missing_history(self):
        headers = self._user_with_historyless_holding()
        resp = client.get("/api/analysis/overview", headers=headers)
        assert resp.status_code == 200, resp.text[:300]
        assert "description" in resp.json()

    def test_weekly_report_survives_missing_history(self):
        headers = self._user_with_historyless_holding()
        resp = client.get("/api/report/weekly", headers=headers)
        assert resp.status_code == 200, resp.text[:300]

    def test_pdf_survives_missing_history(self):
        headers = self._user_with_historyless_holding()
        resp = client.get("/api/report/pdf", headers=headers)
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF-")

    def test_unknown_metrics_reported_as_unknown_not_zero(self):
        """"不知道"必须显示成不知道 —— 强转成 0 会让用户误以为超额收益真的是 0。"""
        headers = self._user_with_historyless_holding()
        body = client.get("/api/analysis/overview", headers=headers).json()
        assert body.get("excess_return_pct") is None
        assert body.get("benchmark_status") == "insufficient_data"
        assert "数据不足" in body["description"]
