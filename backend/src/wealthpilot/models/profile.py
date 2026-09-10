"""投资者画像模型 — 所有仓位与操作建议的硬约束来源。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

RISK_LABELS = {
    1: "保守型",
    2: "稳健型",
    3: "积极型",
    4: "激进型",
    5: "极进取型",
}


class InvestorProfile(SQLModel, table=True):
    """用户风险画像。

    风险测评问卷的结果落在这里，并被注入到 Planner / 各专业 Agent / Synthesizer
    的 system prompt 中。给出仓位或操作建议时，这些字段是硬约束而非参考信息。
    """

    __tablename__ = "investor_profiles"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=1, index=True)

    risk_level: int = Field(default=2, ge=1, le=5, description="风险等级 1-5")
    horizon_months: int = Field(default=12, ge=0, description="投资期限（月）")
    max_drawdown_tolerance: float = Field(
        default=0.15, ge=0.0, le=1.0, description="可承受的最大回撤，0.15 = 15%"
    )
    liquidity_reserve: float = Field(
        default=0.0, ge=0.0, description="半年内需要动用的资金（元），不可占用"
    )
    experience_years: float = Field(default=1.0, ge=0.0)
    available_cash: float | None = Field(default=None, ge=0.0, description="未投资的可用现金余额（元）；未知时不得校验通过")
    excluded_industries: str = Field(default="", description="逗号分隔，不接受配置的行业")

    raw_score: int = Field(default=0, description="问卷原始总分，用于回溯")
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def risk_label(self) -> str:
        return RISK_LABELS.get(self.risk_level, "未知")

    @property
    def excluded_list(self) -> list[str]:
        return [s.strip() for s in self.excluded_industries.split(",") if s.strip()]

    def is_stale(self, days: int = 180) -> bool:
        """画像也会过期 —— 超过半年未更新的画像不应再作为硬约束使用。"""
        return (datetime.now() - self.updated_at).days > days
