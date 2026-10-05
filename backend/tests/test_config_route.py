"""网页端配置：写 .env、立即生效、Key 只写不读、只允许本机。"""

from fastapi.testclient import TestClient

from wealthpilot.main import app
from wealthpilot.routes import config
from wealthpilot.settings import reload_settings


def test_settings_roundtrip_masks_keys_and_validates(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# 注释保留\nAI_PROVIDER=anthropic\nDEEPSEEK_API_KEY=sk-old-secret-1234\n")
    monkeypatch.setattr(config, "ENV_FILE", env)
    with TestClient(app) as client:
        view = client.get("/api/settings").json()
        assert "deepseek_api_key" not in view["values"] and "advice_mode" in view["overridden"]   # 测试环境用环境变量钉住了它

        body = {"ai_provider": "deepseek", "deepseek_api_key": "", "watch_time": "16:05", "paper_initial_cash": 500000,
                "jwt_secret": "hack", "advice_mode": True}
        assert client.put("/api/settings", json=body).status_code == 200
        text = env.read_text()
        assert "# 注释保留" in text and "AI_PROVIDER=deepseek" in text and "WATCH_TIME=16:05" in text and "ADVICE_MODE=true" in text
        assert "DEEPSEEK_API_KEY=sk-old-secret-1234" in text      # Key 留空 = 不改
        assert "JWT_SECRET" not in text and "hack" not in text     # 白名单之外的项改不了
        assert oct(env.stat().st_mode)[-3:] == "600"

        client.put("/api/settings", json={"deepseek_api_key": "sk-new-secret-abcd9876"})
        assert "sk-new-secret-abcd9876" in env.read_text()
        assert "sk-new" not in client.get("/api/settings").text    # 读取时绝不回显 Key

        assert client.put("/api/settings", json={"watch_time": "25点"}).status_code == 422
        assert client.put("/api/settings", json={"broker": "real"}).status_code == 422
        assert client.put("/api/settings", json={"deepseek_model": "a\nJWT_SECRET=x"}).status_code == 422
        assert "WATCH_TIME=16:05" in env.read_text()

    monkeypatch.setattr(config, "_LOCAL", set())
    with TestClient(app) as client:
        assert client.get("/api/settings").status_code == 403
        assert client.put("/api/settings", json={"broker": "paper"}).status_code == 403
    reload_settings()
