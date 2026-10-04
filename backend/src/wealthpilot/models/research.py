"""研究相关的本地数据：自选股、数据缓存。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class WatchItem(SQLModel, table=True):
    __tablename__ = "watchlist"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True, description="所属用户，0=未登录的匿名档")
    code: str = Field(index=True, description="证券代码")
    name: str = Field(default="")
    asset_type: str = Field(default="stock", description="stock / etf / fund")
    note: str = Field(default="", description="用户备注：为什么关注")
    created_at: datetime = Field(default_factory=datetime.now)


class DataCache(SQLModel, table=True):
    """外部数据的本地缓存。免费行情接口不稳定且慢，同一份数据没必要反复取。"""

    __tablename__ = "data_cache"

    key: str = Field(primary_key=True)
    payload: str = Field(description="JSON")
    fetched_at: float = Field(description="写入时刻（unix 秒）")
