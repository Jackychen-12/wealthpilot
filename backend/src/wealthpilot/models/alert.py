"""预警记录模型。

此前 /api/alerts 是纯即时计算：每次请求重新算一遍，不留痕。
"推送通知"至少需要三件事 —— 记录下来、知道哪些没读过、能主动送出去。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)

    kind: str = Field(default="drawdown", description="drawdown / concentration / constraint")
    fund_code: str = Field(default="", index=True)
    fund_name: str = Field(default="")
    severity: str = Field(default="medium", description="low / medium / high")
    message: str = Field(default="")
    value: float = Field(default=0.0, description="触发时的指标值，如收益率 -5.2")
    threshold: float = Field(default=0.0)

    read_at: datetime | None = Field(default=None)
    delivered_at: datetime | None = Field(default=None, description="webhook 送达时间")
    created_at: datetime = Field(default_factory=datetime.now, index=True)

    # 去重键：同一用户、同一标的、同一类型在冷却期内只记一条
    dedup_key: str = Field(default="", index=True)
