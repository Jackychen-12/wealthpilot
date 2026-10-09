"""买卖理由：每次动手时记一句为什么、消息从哪来。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class Decision(SQLModel, table=True):
    __tablename__ = "decisions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    code: str = Field(index=True)
    name: str = Field(default="")
    action: str = Field(default="buy", description="buy / sell")
    day: str = Field(default="", description="动手的日期 YYYY-MM-DD")
    price: float | None = Field(default=None)
    reason: str = Field(default="", description="当时为什么买 / 卖，一两句话")
    source_kind: str = Field(default="自己研究", description="消息或想法从哪来")
    source_name: str = Field(default="", description="具体是谁 / 哪里，比如某位博主的名字")
    created_at: datetime = Field(default_factory=datetime.now)
