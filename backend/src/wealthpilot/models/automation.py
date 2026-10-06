"""自动任务：到点自己跑的研究，和到了条件就提醒的盯价。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class Automation(SQLModel, table=True):
    """一条自动任务。

    kind=task：按 schedule 到点跑一次研究（prompt），把结论推到手机、记进当日简报。
    kind=alert：某只股票的某个指标越过阈值时提醒一次。代码取数判定，不调用模型。
    只在 WealthPilot 开着的时候运行；错过的任务下次打开时补跑一次。
    """

    __tablename__ = "automations"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    kind: str = Field(description="task / alert")
    title: str = Field(default="")
    enabled: bool = Field(default=True)

    schedule: str = Field(default="", description="task：什么时候跑，如“工作日 08:30”")
    prompt: str = Field(default="", description="task：到点问 Agent 的那句话")
    depth: str = Field(default="auto")

    code: str = Field(default="", index=True, description="alert：盯哪只")
    name: str = Field(default="")
    metric: str = Field(default="", description="alert：见 services/automations.ALERT_METRICS")
    op: str = Field(default="", description=">= 或 <=")
    threshold: float | None = Field(default=None)
    repeat: bool = Field(default=False, description="alert：触发后继续盯（每天最多提醒一次）；否则提醒一次就停")

    last_run_at: datetime | None = Field(default=None)
    last_status: str = Field(default="", description="ok / failed / skipped / fired")
    last_result: str = Field(default="")
    last_message_id: int | None = Field(default=None, description="task：最近一次跑出来的研究")
    created_at: datetime = Field(default_factory=datetime.now)
