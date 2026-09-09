"""SQLite 引擎初始化 + 轻量列迁移。"""

from pathlib import Path

from sqlalchemy import DateTime, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from wealthpilot.models.chat import ChatMessage  # noqa: F401 — register table
from wealthpilot.models.profile import InvestorProfile  # noqa: F401 — register table

# 显式注册其余表，避免依赖 import 顺序
from wealthpilot.models.market import FundNavCache, IndexSnapshot  # noqa: F401
from wealthpilot.models.portfolio import PortfolioHolding  # noqa: F401
from wealthpilot.models.user import User  # noqa: F401
from wealthpilot.settings import get_settings

_engine = None


def _literal_default(column) -> str | None:
    """把模型上的标量默认值翻成 SQL 常量字面量。

    只返回**常量** —— SQLite 的 `ALTER TABLE ADD COLUMN` 不接受非常量默认值
    （`CURRENT_TIMESTAMP` 会报 "Cannot add a column with non-constant default"）。
    datetime 用的是 default_factory（Python 可调用对象），这里返回 None，
    改由 `_backfill_expr` 在建好列之后用 UPDATE 回填。
    """
    default = getattr(column, "default", None)
    if default is None or callable(getattr(default, "arg", None)):
        return None

    value = default.arg
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def _backfill_expr(column) -> str | None:
    """已有行的回填表达式。UPDATE 允许非常量，所以这里可以用 CURRENT_TIMESTAMP。"""
    if isinstance(column.type, DateTime):
        return "CURRENT_TIMESTAMP"
    return _literal_default(column)


def _ensure_columns(engine) -> list[str]:
    """给已存在的表补上模型里新增、但库里还没有的列。

    `SQLModel.metadata.create_all()` 只建缺失的**表**，从不改已有表的结构。
    项目没有 Alembic，于是模型加了字段之后，旧的 SQLite 文件会一直缺列，
    读取时直接 `no such column` 报 500 —— 而且只在老库上出现，新建库看不到。
    这里在启动时做一次补列，让本地库自愈。

    只新增可空列（SQLite 不允许直接加 NOT NULL 列），不改类型、不删列。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []

    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all 会建它

            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue

                col_type = column.type.compile(engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                default = _literal_default(column)
                if default is not None:
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))

                # 已有行回填。新列默认是 NULL，而模型侧多为非可空字段，
                # 不回填的话读出来仍会在校验层报错。
                fill = _backfill_expr(column)
                if fill is not None:
                    conn.execute(
                        text(
                            f'UPDATE "{table.name}" SET "{column.name}" = {fill} '
                            f'WHERE "{column.name}" IS NULL'
                        )
                    )

                applied.append(f"{table.name}.{column.name}")

    return applied


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
        migrated = _ensure_columns(_engine)
        if migrated:
            print(f"🔧 补齐缺失列：{', '.join(migrated)}")
    return _engine


def get_session():
    with Session(get_engine()) as session:
        yield session
