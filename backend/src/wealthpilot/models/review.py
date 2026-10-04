"""事后验证与复盘：验证点（Checkpoint）与操作建议单（TradeProposal）。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class Checkpoint(SQLModel, table=True):
    """一条可由代码核对的判断：某只股票的某个指标，在某个时点应当满足某个条件。

    研究发布时由模型提出、代码校验后落库；到期后由代码取数判定成立还是被证伪。
    """

    __tablename__ = "checkpoints"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    message_id: int | None = Field(default=None, index=True, description="出自哪一次研究（ChatMessage.id）")
    question: str = Field(default="")
    playbook: str = Field(default="")
    code: str = Field(index=True)
    name: str = Field(default="")
    metric: str = Field(description="见 services/checkpoints.METRICS")
    op: str = Field(description=">= 或 <=")
    threshold: float
    statement: str = Field(default="", description="这条判断为什么重要（模型写的一句话）")
    baseline_value: float | None = Field(default=None, description="设定时的实际值（代码取的）")
    baseline_as_of: str = Field(default="", description="基准值的数据日期 / 报告期")
    due_date: str = Field(default="", description="到期日（估值、涨跌类）；财务类为空，等下一期财报")
    status: str = Field(default="pending", index=True, description="pending / held / broken / unverifiable")
    actual_value: float | None = Field(default=None)
    actual_as_of: str = Field(default="")
    checked_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)


class TradeProposal(SQLModel, table=True):
    """操作建议单。Agent 只能提出，必须由用户逐条授权后才会执行。"""

    __tablename__ = "trade_proposals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    message_id: int | None = Field(default=None, index=True)
    code: str = Field(index=True)
    name: str = Field(default="")
    asset_type: str = Field(default="stock")
    action: str = Field(description="buy / add / reduce / sell")
    shares: int | None = Field(default=None, description="建议数量（股）；空表示由用户决定")
    price_ref: float | None = Field(default=None, description="提出建议时的参考价")
    reason: str = Field(default="")
    invalidation: str = Field(default="", description="什么情况下这条建议不再成立")
    status: str = Field(default="proposed", index=True, description="proposed / executed / rejected")
    exec_shares: int | None = Field(default=None)
    exec_price: float | None = Field(default=None)
    decided_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
