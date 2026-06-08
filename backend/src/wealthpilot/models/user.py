"""用户模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(default="")
    hashed_password: str = Field()
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True)
