"""模型用量流水：每次调用模型的一轮（研究、改写、起草……）记一笔。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class UsageLog(SQLModel, table=True):
    __tablename__ = "usage_log"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    at: datetime = Field(default_factory=datetime.now, index=True)
    kind: str = Field(default="research", description="research / quick / rewrite / reuse / task")
    model: str = Field(default="")
    calls: int = Field(default=0)
    input_tokens: int = Field(default=0)
    cached_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
