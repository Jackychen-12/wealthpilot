"""环境变量配置。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI provider
    ai_provider: str = Field(default="anthropic", description="anthropic or deepseek")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = Field(default="claude-sonnet-5")

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")

    alpha_vantage_key: str = Field(default="")

    jwt_secret: str = Field(default="wealthpilot-dev-secret-change-me")

    # Agent configuration
    agent_max_tool_rounds: int = Field(default=3)
    agent_max_tokens: int = Field(default=4000)
    agent_max_parallel: int = Field(default=3, description="同一波内并发执行的 Agent 上限")
    planner_max_tasks: int = Field(default=4, description="Planner 单次拆解的任务数上限")
    critic_enabled: bool = Field(default=True, description="是否启用 Critic 双闸门校验")
    critic_max_replans: int = Field(default=1, description="证据不足时最多补充规划几轮")
    critic_max_rewrites: int = Field(default=2, description="输出不合规时最多重写几次")

    alert_webhook_url: str = Field(default="", description="预警 webhook 推送地址，留空则不推送")

    db_path: Path = Field(default=Path("./data/wealthpilot.db"))
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5173"

    @property
    def active_model(self) -> str:
        if self.ai_provider == "deepseek":
            return self.deepseek_model
        return self.anthropic_model

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
