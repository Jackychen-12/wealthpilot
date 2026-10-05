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
    agent_max_tokens: int = Field(default=16000)
    agent_max_parallel: int = Field(default=3, description="同一波内并发执行的 Agent 上限")
    planner_max_tasks: int = Field(default=4, description="Planner 单次拆解的任务数上限")
    critic_enabled: bool = Field(default=True, description="是否启用 Critic 双闸门校验")
    critic_max_replans: int = Field(default=1, description="证据不足时最多补充规划几轮")
    critic_max_rewrites: int = Field(default=2, description="输出不合规时最多重写几次")
    critic_min_grounding_rate: float = Field(
        default=0.9, ge=0.0, le=1.0,
        description="重写用尽后，数字溯源率不低于此值的草稿带标注发布；设为 1 则一律拒答")
    tool_timeout_seconds: float = Field(default=30, gt=0)
    run_timeout_seconds: float = Field(default=180, gt=0)
    run_max_tool_calls: int = Field(default=24, ge=1)
    ai_timeout_seconds: float = Field(default=60, gt=0)

    skills_dir: Path = Field(default=Path("./skills"), description="技能目录：用户自己写的研究方法（Markdown）")
    light_model: str = Field(default="", description="提取证券名、审核证据、提出验证点等轻活用的模型；留空则与主模型相同")
    checkpoints_enabled: bool = Field(default=True, description="研究发布后提出可事后核对的验证点")
    advice_mode: bool = Field(
        default=False,
        description="个人模式：允许给出明确的买卖立场与操作建议（仍须逐条授权才执行），并用涨跌类验证点事后打分")

    broker: str = Field(default="none", description="下单通道：none=授权只记账；paper=内置模拟盘（按最新价成交，不动真钱）")
    paper_initial_cash: float = Field(default=1_000_000, gt=0, description="模拟盘初始资金")
    watch_enabled: bool = Field(default=True, description="后端运行时，交易日收盘后自动跑一次盯盘")
    watch_time: str = Field(default="15:30", pattern=r"^\d{2}:\d{2}$", description="每日盯盘时间（本机时区）")
    watch_move_pct: float = Field(default=5.0, gt=0, description="当日涨跌幅超过多少算异动")

    local_user_id: int = Field(default=0, description="CLI / MCP 使用哪个用户的持仓与画像，0=匿名档")

    connectors_file: Path = Field(default=Path("./connectors.json"), description="外部 MCP 连接器配置文件")

    alert_webhook_url: str = Field(default="", description="预警 webhook 推送地址，留空则不推送")

    db_path: Path = Field(default=Path("./data/wealthpilot.db"))
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5180"

    @property
    def active_model(self) -> str:
        if self.ai_provider == "deepseek":
            return self.deepseek_model
        return self.anthropic_model

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def reload_settings() -> Settings:
    """丢掉缓存重新读取 .env —— 在网页上改完配置后调用，不用重启。"""
    global _settings
    _settings = None
    return get_settings()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
