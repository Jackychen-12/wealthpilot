"""测试环境隔离。

在导入任何 wealthpilot 模块之前，把 DB_PATH 指向临时库。

否则测试会直接读写 `data/wealthpilot.db`（开发库）：注册用户、写入持仓都会留在
库里，于是整套测试只在全新库上是绿的，第二次跑 `make test` 就会因为
"用户已存在" 而失败。conftest 由 pytest 在测试模块之前导入，是设这个环境
变量的唯一可靠时机。
"""

import os
import shutil
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="wealthpilot-test-"))
os.environ["DB_PATH"] = str(_TMP_DIR / "test.db")

import pytest  # noqa: E402 — 必须在设置 DB_PATH 之后


@pytest.fixture(scope="session", autouse=True)
def _cleanup_temp_db():
    yield
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
