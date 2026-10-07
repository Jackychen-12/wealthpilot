"""环境变量配置。"""

import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _home() -> Path:
    """配置、数据库、技能这些文件放在哪。

    以前都是相对当前目录找的，所以命令只能在 backend/ 下运行。现在固定到一个"家目录"：
    WEALTHPILOT_HOME 指定的位置；没指定时用源码所在的 backend/（从仓库安装时就是这种情况）；都不是才退回当前目录。
    """
    env = os.environ.get("WEALTHPILOT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    backend = Path(__file__).resolve().parents[2]
    return backend if (backend / "pyproject.toml").exists() else Path.cwd()


HOME = _home()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(HOME / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI provider
    ai_provider: str = Field(default="anthropic", description="anthropic / deepseek / openai（任何兼容 OpenAI 接口的服务，含本机模型）")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    anthropic_model: str = Field(default="claude-sonnet-5")

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")

    # 任何兼容 OpenAI 接口的服务：硅基流动、智谱、Moonshot、通义、火山方舟、OpenRouter、本机 Ollama……
    openai_api_key: str = Field(default="", description="兼容服务的 API Key；本机模型可以留空")
    openai_model: str = Field(default="", description="模型名，照服务商文档里的写")
    openai_base_url: str = Field(default="", description="接口地址，如 https://api.siliconflow.cn/v1、http://localhost:11434/v1")
    openai_json_mode: bool = Field(default=False, description="服务支持 response_format=json_object 时打开，规划和审核的 JSON 更稳")
    openai_max_tokens: int = Field(default=4096, ge=256, description="单次输出的 token 上限；超过服务商限制会直接报错，拿不准就用 4096")

    alpha_vantage_key: str = Field(default="")

    jwt_secret: str = Field(default="wealthpilot-dev-secret-change-me")

    # Agent configuration
    agent_max_tool_rounds: int = Field(default=3)
    agent_max_tokens: int = Field(default=16000)
    agent_max_parallel: int = Field(default=6, description="同一波内并发执行的 Agent 上限")
    planner_max_tasks: int = Field(default=4, description="Planner 单次拆解的任务数上限")
    critic_enabled: bool = Field(default=True, description="是否启用 Critic 双闸门校验")
    critic_max_replans: int = Field(default=1, description="证据不足时最多补充规划几轮")
    critic_max_rewrites: int = Field(default=2, description="输出不合规时最多重写几次")
    critic_min_grounding_rate: float = Field(
        default=0.9, ge=0.0, le=1.0,
        description="重写用尽后，数字溯源率不低于此值的草稿带标注发布；设为 1 则一律拒答")
    tool_timeout_seconds: float = Field(default=30, gt=0)
    run_timeout_seconds: float = Field(default=180, gt=0)
    run_max_tool_calls: int = Field(default=40, ge=1)
    ai_timeout_seconds: float = Field(default=60, gt=0)

    skills_dir: Path = Field(default=Path("./skills"), description="技能目录：用户自己写的研究方法（Markdown）")
    light_model: str = Field(default="", description="提取证券名、审核证据、提出验证点等轻活用的模型；留空则与主模型相同")
    checkpoints_enabled: bool = Field(default=True, description="研究发布后提出可事后核对的验证点")
    debate_enabled: bool = Field(default=True, description="个股深度研究时，撰写前先让看多、看空两方就同一批证据各自陈述")
    advice_mode: bool = Field(
        default=False,
        description="个人模式：允许给出明确的买卖立场与操作建议（仍须逐条授权才执行），并用涨跌类验证点事后打分")

    broker: str = Field(default="none", description="下单通道：none=授权只记账；paper=内置模拟盘（按最新价成交，不动真钱）")
    paper_initial_cash: float = Field(default=1_000_000, gt=0, description="模拟盘初始资金")
    watch_enabled: bool = Field(default=True, description="后端运行时，交易日收盘后自动跑一次盯盘")
    watch_time: str = Field(default="15:30", pattern=r"^\d{2}:\d{2}$", description="每日盯盘时间（本机时区）")
    watch_move_pct: float = Field(default=5.0, gt=0, description="当日涨跌幅超过多少算异动")
    auto_daily_runs_max: int = Field(default=6, ge=0, description="定时任务每天最多自动跑几次研究（会调用模型）；手动点“现在跑”不受限")
    # 用量与预算
    daily_token_budget: int = Field(default=0, ge=0, description="每天最多用多少 token（输入加输出），到了就不再调模型；0 = 不限")
    token_price_input: float = Field(default=0, ge=0, description="输入单价，元 / 百万 token；填了才会把用量折成钱")
    token_price_output: float = Field(default=0, ge=0, description="输出单价，元 / 百万 token")
    research_reuse_hours: float = Field(default=4, ge=0, description="几小时内对同一只股票再做深度研究时，沿用上一次取到的数据而不是重新取数；0 = 每次都重新取")
    update_check: bool = Field(default=True, description="启动时看一眼有没有新版本（只读取本仓库的远端，不上传任何东西）")

    # 手机触达：Telegram 机器人。令牌在网页「设置」里填；绑定哪个聊天由配对码决定，存在数据库里
    telegram_bot_token: str = Field(default="", description="Telegram 机器人令牌（@BotFather 给的）")
    telegram_api_base: str = Field(default="https://api.telegram.org", description="Telegram 接口地址；需要走中转时改这里")

    # 飞书：企业自建应用，事件订阅选"长连接"。不需要公网地址
    feishu_app_id: str = Field(default="", description="飞书应用的 App ID")
    feishu_app_secret: str = Field(default="", description="飞书应用的 App Secret")
    feishu_api_base: str = Field(default="https://open.feishu.cn", description="飞书接口地址；海外版 Lark 用 https://open.larksuite.com")
    # 企业微信：自建应用，接收消息要填回调地址（需要公网能访问）
    wecom_corp_id: str = Field(default="", description="企业 ID")
    wecom_agent_id: str = Field(default="", description="应用的 AgentId")
    wecom_secret: str = Field(default="", description="应用的 Secret")
    wecom_token: str = Field(default="", description="接收消息设置里的 Token")
    wecom_aes_key: str = Field(default="", description="接收消息设置里的 EncodingAESKey（43 位）")

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
        if self.ai_provider == "openai":
            return self.openai_model
        return self.anthropic_model

    @model_validator(mode="after")
    def _anchor_paths(self):
        # 相对路径一律相对家目录，而不是相对"命令是在哪个目录下敲的"
        for name in ("db_path", "skills_dir", "connectors_file"):
            value = getattr(self, name)
            if not value.is_absolute():
                object.__setattr__(self, name, HOME / value)
        return self

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
