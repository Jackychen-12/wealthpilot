"""SQLite 引擎初始化。"""

from pathlib import Path

from sqlmodel import SQLModel, create_engine, Session

from wealthpilot.settings import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_path = Path(settings.db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(_engine)
    return _engine


def get_session():
    with Session(get_engine()) as session:
        yield session
