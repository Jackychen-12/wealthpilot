"""投资者记忆与审计日志。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class Memory(SQLModel, table=True):
    """用户明确说过的偏好、纪律，和对建议做过的决定。与对话记录分开存，下次研究自动带上。"""

    __tablename__ = "memories"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    kind: str = Field(default="preference", description="preference 偏好与纪律 / decision 对建议的决定 / note 手工备注")
    code: str = Field(default="", index=True, description="只和某只证券有关时填代码；空表示通用")
    content: str
    source: str = Field(default="", description="来自哪里：chat / proposal:<id> / manual")
    created_at: datetime = Field(default_factory=datetime.now)


class AuditEvent(SQLModel, table=True):
    """只追加的审计日志。每条带上一条的哈希，事后改动任何一条都会让校验对不上。"""

    __tablename__ = "audit_events"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=0, index=True)
    at: datetime = Field(default_factory=datetime.now)
    kind: str = Field(index=True, description="domain/action，如 approval/decided、order/filled")
    actor: str = Field(default="system", description="user / agent / system")
    summary: str = Field(default="")
    payload_json: str = Field(default="{}")
    prev_hash: str = Field(default="")
    hash: str = Field(default="")
