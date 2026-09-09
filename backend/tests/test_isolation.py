"""多租户隔离回归测试。

这类缺陷的特点是"功能全都正常，只是数据串了"，正常用不会发现，所以必须有
显式的跨用户断言把它钉住。覆盖三种失效方式：

1. 读泄露   —— A 的列表里出现 B 的持仓
2. 写越权   —— A 能改 / 删 B 的持仓（IDOR）
3. 派生泄露 —— 分析、周报、预警等基于持仓计算的接口把 B 的数据算了进去
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from wealthpilot.main import app

client = TestClient(app)


def _register(username: str) -> str:
    """注册并返回 Authorization 头值。"""
    payload = {"username": username, "password": "pw-test-123", "email": f"{username}@t.com"}
    resp = client.post("/api/auth/register", json=payload)
    if resp.status_code != 200:
        resp = client.post("/api/auth/login", json={"username": username, "password": "pw-test-123"})
    return f"Bearer {resp.json()['access_token']}"


def _add_holding(auth: str, code: str, name: str) -> int:
    resp = client.post(
        "/api/portfolio",
        headers={"Authorization": auth},
        json={
            "fund_code": code,
            "fund_name": name,
            "shares": 100.0,
            "cost_price": 1.5,
            "buy_date": "2026-01-01",
            "category": "equity",
            "industry": "科技",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(scope="module")
def two_users():
    suffix = uuid.uuid4().hex[:8]
    alice = _register(f"alice_{suffix}")
    bob = _register(f"bob_{suffix}")
    alice_id = _add_holding(alice, "110011", "Alice 的基金")
    bob_id = _add_holding(bob, "007340", "Bob 的基金")
    return {"alice": alice, "bob": bob, "alice_holding": alice_id, "bob_holding": bob_id}


@pytest.fixture
def fresh_pair():
    """一对全新的用户与持仓。

    派生数据的测试不能复用 two_users —— TestWriteIsolation 里的删除用例在
    "隔离失效" 的情况下会真的把 Bob 的持仓删掉，导致后面的泄露断言无数据可查、
    静默空过。用独立数据把这个耦合切断。
    """
    suffix = uuid.uuid4().hex[:8]
    alice = _register(f"da_{suffix}")
    bob = _register(f"db_{suffix}")
    _add_holding(alice, "110011", "Alice 的基金")
    _add_holding(bob, "007340", "Bob 的基金")
    return {"alice": alice, "bob": bob}


class TestReadIsolation:
    def test_list_only_returns_own(self, two_users):
        resp = client.get("/api/portfolio", headers={"Authorization": two_users["alice"]})
        assert resp.status_code == 200
        codes = [h["fund_code"] for h in resp.json()]
        assert "110011" in codes
        assert "007340" not in codes, "Alice 的列表里出现了 Bob 的持仓"

    def test_bob_sees_only_his(self, two_users):
        resp = client.get("/api/portfolio", headers={"Authorization": two_users["bob"]})
        codes = [h["fund_code"] for h in resp.json()]
        assert codes == ["007340"]

    def test_anonymous_sees_neither(self, two_users):
        resp = client.get("/api/portfolio")
        codes = [h["fund_code"] for h in resp.json()]
        assert "110011" not in codes
        assert "007340" not in codes


class TestWriteIsolation:
    """IDOR：原实现用裸 db.get(id)，任何人改个整数就能操作他人持仓。"""

    def test_cannot_update_others_holding(self, two_users):
        resp = client.put(
            f"/api/portfolio/{two_users['bob_holding']}",
            headers={"Authorization": two_users["alice"]},
            json={"shares": 99999.0},
        )
        assert resp.status_code == 404, "Alice 改动了 Bob 的持仓"

    def test_cannot_delete_others_holding(self, two_users):
        resp = client.delete(
            f"/api/portfolio/{two_users['bob_holding']}",
            headers={"Authorization": two_users["alice"]},
        )
        assert resp.status_code == 404, "Alice 删除了 Bob 的持仓"

    def test_victim_holding_survives(self, two_users):
        resp = client.get("/api/portfolio", headers={"Authorization": two_users["bob"]})
        holdings = resp.json()
        assert len(holdings) == 1
        assert holdings[0]["shares"] == 100.0, "Bob 的持仓被改动了"

    def test_can_update_own_holding(self, two_users):
        """隔离不能把正常功能一起挡掉。"""
        resp = client.put(
            f"/api/portfolio/{two_users['alice_holding']}",
            headers={"Authorization": two_users["alice"]},
            json={"industry": "医药"},
        )
        assert resp.status_code == 200
        assert resp.json()["industry"] == "医药"


class TestDerivedDataIsolation:
    """分析类接口基于持仓计算，同样不能把别人的数据算进来。

    只挑会在响应里带出基金身份的接口。overview / health / drawdown / correlation
    返回的是纯聚合数字，不含基金代码或名称，对它们断言"不含 Bob"永远成立，
    是空断言 —— 反而会掩盖问题，所以不放进来。

    每条用例同时断言"自己的在"和"别人的不在"：前者保证这个接口确实吐出了
    可识别数据、断言不是空过，后者才是真正要防的泄露。
    """

    @pytest.mark.parametrize("path", [
        "/api/analysis/attribution?by=fund",
        "/api/analysis/suggestions",
        "/api/report/weekly",
    ])
    def test_endpoint_shows_own_and_hides_others(self, fresh_pair, path):
        resp = client.get(path, headers={"Authorization": fresh_pair["alice"]})
        assert resp.status_code == 200
        body = resp.text
        assert "Alice 的基金" in body, f"{path} 连自己的数据都没有，断言会空过"
        assert "007340" not in body, f"{path} 泄露了 Bob 的基金代码"
        assert "Bob 的基金" not in body, f"{path} 泄露了 Bob 的基金名称"


class TestProfileIsolation:
    def test_profile_is_per_user(self, two_users):
        client.put(
            "/api/profile",
            headers={"Authorization": two_users["alice"]},
            json={"risk_level": 4, "horizon_months": 60, "max_drawdown_tolerance": 0.3},
        )
        bob_profile = client.get("/api/profile", headers={"Authorization": two_users["bob"]})
        assert bob_profile.json() is None, "Bob 读到了 Alice 的风险画像"

        alice_profile = client.get("/api/profile", headers={"Authorization": two_users["alice"]})
        assert alice_profile.json()["risk_level"] == 4


class TestTokenHandling:
    """令牌异常时必须退化为匿名，而不是报错或误判成某个用户。"""

    @pytest.mark.parametrize("header", ["", "Bearer ", "Bearer garbage", "not-a-bearer-token"])
    def test_bad_token_degrades_to_anonymous(self, two_users, header):
        resp = client.get("/api/portfolio", headers={"Authorization": header} if header else {})
        assert resp.status_code == 200
        codes = [h["fund_code"] for h in resp.json()]
        assert "110011" not in codes and "007340" not in codes
