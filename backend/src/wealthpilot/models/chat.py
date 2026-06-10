"""聊天记录模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(default="", description="会话 ID")
    role: str = Field(description="user / assistant")
    content: str = Field(description="消息内容")
    metadata_json: str = Field(default="", description="Agent 路由等元数据 JSON")
    created_at: datetime = Field(default_factory=datetime.now)
