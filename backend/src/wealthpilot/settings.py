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
    anthropic_model: str = Field(default="claude-sonnet-4-6")

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")

    alpha_vantage_key: str = Field(default="")

    jwt_secret: str = Field(default="wealthpilot-dev-secret-change-me")

    # Agent configuration
    agent_max_tool_rounds: int = Field(default=3)
    agent_max_tokens: int = Field(default=4000)

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
