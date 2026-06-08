"""持仓数据模型。"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class PortfolioHolding(SQLModel, table=True):
    __tablename__ = "portfolio_holdings"

    id: int | None = Field(default=None, primary_key=True)
    fund_code: str = Field(index=True, description="基金代码")
    fund_name: str = Field(description="基金名称")
    shares: float = Field(description="持有份额")
    cost_price: float = Field(description="成本净值")
    buy_date: date = Field(description="买入日期")
    category: str = Field(default="equity", description="equity/bond/money/hybrid")
    industry: str = Field(default="", description="行业标签")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
