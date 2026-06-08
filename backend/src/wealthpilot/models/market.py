"""行情数据模型。"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel


class FundNavCache(SQLModel, table=True):
    __tablename__ = "fund_nav_cache"

    id: int | None = Field(default=None, primary_key=True)
    fund_code: str = Field(index=True)
    nav_date: date = Field(index=True)
    nav: float = Field(description="单位净值")
    acc_nav: float = Field(default=0.0, description="累计净值")
    daily_return: float = Field(default=0.0, description="日涨跌幅(%)")

    class Config:
        unique_together = ("fund_code", "nav_date")


class IndexSnapshot(SQLModel, table=True):
    __tablename__ = "index_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    index_code: str = Field(index=True, description="指数代码")
    index_name: str = Field(description="指数名称")
    close: float = Field(description="收盘价")
    change_pct: float = Field(description="涨跌幅(%)")
    snapshot_date: date = Field()
    updated_at: datetime = Field(default_factory=datetime.now)
