"""模拟盘账户、持仓、委托，以及每日简报。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class PaperAccount(SQLModel, table=True):
    __tablename__ = "paper_accounts"

    user_id: int = Field(primary_key=True)
    cash: float
    initial_cash: float
    created_at: datetime = Field(default_factory=datetime.now)


class PaperPosition(SQLModel, table=True):
    __tablename__ = "paper_positions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    code: str = Field(index=True)
    name: str = Field(default="")
    asset_type: str = Field(default="stock")
    shares: int
    cost_price: float = Field(description="持仓均价（不含费用）")
    updated_at: datetime = Field(default_factory=datetime.now)


class Order(SQLModel, table=True):
    """委托记录。只有用户本人点了确认才会产生，Agent 没有下单工具。"""

    __tablename__ = "orders"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    broker: str = Field(default="paper")
    code: str = Field(index=True)
    name: str = Field(default="")
    side: str = Field(description="buy / sell")
    shares: int
    price: float | None = Field(default=None, description="成交价")
    amount: float = Field(default=0)
    fee: float = Field(default=0)
    status: str = Field(default="filled", description="filled / rejected")
    reason: str = Field(default="", description="被拒原因")
    proposal_id: int | None = Field(default=None, description="出自哪条操作建议单")
    created_at: datetime = Field(default_factory=datetime.now)


class Digest(SQLModel, table=True):
    """每日盯盘简报：一个用户一天一份。"""

    __tablename__ = "digests"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    day: str = Field(index=True)
    events_json: str = Field(default="[]")
    summary: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
