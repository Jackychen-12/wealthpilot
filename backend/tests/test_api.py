"""后端 API 集成测试。"""

import pytest
from fastapi.testclient import TestClient

from wealthpilot.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root():
    resp = client.get("/")
    data = resp.json()
    assert data["name"] == "wealthpilot"
    assert "version" in data


def test_portfolio_empty():
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_portfolio_crud():
    # Create
    resp = client.post("/api/portfolio", json={
        "fund_code": "000001",
        "fund_name": "测试基金",
        "shares": 1000.0,
        "cost_price": 1.5,
        "buy_date": "2024-01-01",
        "category": "equity",
    })
    assert resp.status_code == 201
    holding = resp.json()
    assert holding["fund_code"] == "000001"
    holding_id = holding["id"]

    # Read
    resp = client.get("/api/portfolio")
    assert any(h["id"] == holding_id for h in resp.json())

    # Update
    resp = client.put(f"/api/portfolio/{holding_id}", json={"shares": 2000.0})
    assert resp.status_code == 200
    assert resp.json()["shares"] == 2000.0

    # Delete
    resp = client.delete(f"/api/portfolio/{holding_id}")
    assert resp.status_code == 200


def test_market_indices():
    resp = client.get("/api/market/indices")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_market_news():
    resp = client.get("/api/market/news")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analysis_overview_empty():
    resp = client.get("/api/analysis/overview")
    assert resp.status_code == 200


def test_auth_register_and_login():
    # Register
    resp = client.post("/api/auth/register", json={
        "username": "testuser123",
        "password": "testpass",
        "email": "test@test.com",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == "testuser123"

    # Login
    resp = client.post("/api/auth/login", json={
        "username": "testuser123",
        "password": "testpass",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    # Me
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser123"


def test_auth_wrong_password():
    resp = client.post("/api/auth/login", json={
        "username": "testuser123",
        "password": "wrongpass",
    })
    assert resp.status_code == 401


def test_report_weekly():
    resp = client.get("/api/report/weekly")
    assert resp.status_code == 200
