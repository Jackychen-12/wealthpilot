"""聊天记录模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    role: str = Field(description="user / assistant")
    content: str = Field(description="消息内容")
    created_at: datetime = Field(default_factory=datetime.now)
