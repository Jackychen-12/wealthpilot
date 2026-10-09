"""持仓数据模型。"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class PortfolioHolding(SQLModel, table=True):
    __tablename__ = "portfolio_holdings"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True, description="所属用户ID，0=公共/未登录")
    asset_type: str = Field(default="fund", index=True, description="fund/stock/etf/crypto")
    fund_code: str = Field(index=True, description="标的代码（基金/股票/ETF/加密货币）")
    fund_name: str = Field(description="基金名称")
    shares: float = Field(description="持有份额")
    cost_price: float = Field(description="成本价（人民币）。港股美股是按买入日汇率折算后的数")
    currency: str = Field(default="CNY", description="这只证券的计价货币：CNY / HKD / USD")
    cost_native: float | None = Field(default=None, description="港股美股：用户填的原币种成本价")
    cost_fx: float | None = Field(default=None, description="港股美股：入账时用的汇率（1 外币 = 多少人民币）")
    buy_date: date = Field(description="买入日期")
    category: str = Field(default="equity", description="equity/bond/money/hybrid")
    industry: str = Field(default="", description="行业标签")
    source: str = Field(default="", description="来源：空=手工录入，broker=由模拟盘 / 券商持仓同步")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
