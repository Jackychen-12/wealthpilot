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
