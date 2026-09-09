"""数据库补列迁移测试。

`create_all()` 只建缺失的表、从不改已有表结构，所以模型加字段之后旧库会缺列。
这几条用例覆盖 `_ensure_columns` 的自愈行为。
"""

import sqlite3

from sqlalchemy import inspect
from sqlmodel import create_engine

from wealthpilot.storage.db import _backfill_expr, _ensure_columns, _literal_default


def _cols(db_path: str, table: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


class TestEnsureColumns:
    def test_adds_missing_column(self, tmp_path):
        """模拟旧库：portfolio_holdings 缺 user_id（真实发生过的情况）。"""
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE portfolio_holdings (
                id INTEGER PRIMARY KEY,
                fund_code VARCHAR,
                fund_name VARCHAR,
                shares FLOAT,
                cost_price FLOAT,
                buy_date DATE
            )
        """)
        conn.commit()
        conn.close()

        assert "user_id" not in _cols(str(db), "portfolio_holdings")

        engine = create_engine(f"sqlite:///{db}")
        applied = _ensure_columns(engine)

        assert "portfolio_holdings.user_id" in applied
        assert "user_id" in _cols(str(db), "portfolio_holdings")

    def test_backfills_scalar_default(self, tmp_path):
        """已有行必须拿到默认值，而不是 NULL —— 否则读出来还是会炸。"""
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, role VARCHAR, content VARCHAR)")
        conn.execute("INSERT INTO chat_messages (role, content) VALUES ('user', '历史消息')")
        conn.commit()
        conn.close()

        _ensure_columns(create_engine(f"sqlite:///{db}"))

        conn = sqlite3.connect(db)
        row = conn.execute("SELECT conversation_id, metadata_json FROM chat_messages").fetchone()
        conn.close()
        assert row == ("", "")

    def test_idempotent(self, tmp_path):
        """重复启动不应重复 ALTER。"""
        db = tmp_path / "fresh.db"
        engine = create_engine(f"sqlite:///{db}")
        from sqlmodel import SQLModel

        SQLModel.metadata.create_all(engine)

        assert _ensure_columns(engine) == []
        assert _ensure_columns(engine) == []

    def test_skips_missing_tables(self, tmp_path):
        """空库交给 create_all，补列逻辑不该报错。"""
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        assert _ensure_columns(engine) == []

    def test_preserves_existing_data(self, tmp_path):
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, hashed_password VARCHAR)")
        conn.execute("INSERT INTO users (username, hashed_password) VALUES ('alice', 'x')")
        conn.commit()
        conn.close()

        _ensure_columns(create_engine(f"sqlite:///{db}"))

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT username FROM users").fetchone()[0] == "alice"
        conn.close()

    def test_investor_profiles_created_on_old_db(self, tmp_path):
        """新表走 create_all，补列不影响它。"""
        db = tmp_path / "old.db"
        engine = create_engine(f"sqlite:///{db}")
        from sqlmodel import SQLModel

        SQLModel.metadata.create_all(engine)
        assert "investor_profiles" in inspect(engine).get_table_names()


class TestLiteralDefault:
    def test_string_default_quoted(self):
        from wealthpilot.models.chat import ChatMessage

        col = ChatMessage.__table__.columns["conversation_id"]
        assert _literal_default(col) == "''"

    def test_int_default(self):
        from wealthpilot.models.portfolio import PortfolioHolding

        col = PortfolioHolding.__table__.columns["user_id"]
        assert _literal_default(col) == "0"

    def test_datetime_not_a_ddl_default(self):
        """SQLite 不接受非常量 DDL 默认值，datetime 必须走回填而不是 DEFAULT。"""
        from wealthpilot.models.portfolio import PortfolioHolding

        col = PortfolioHolding.__table__.columns["created_at"]
        assert _literal_default(col) is None
        assert _backfill_expr(col) == "CURRENT_TIMESTAMP"

    def test_quote_escaping(self):
        """带单引号的默认值不能拼出可注入的 DDL。"""
        from sqlalchemy import Column, String

        col = Column("x", String, default="it's")
        assert _literal_default(col) == "'it''s'"
