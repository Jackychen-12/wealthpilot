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
# 测试不得打真实模型：开发者 .env 里配了 Key 时，周报等路径会真的发请求
# （花钱、变慢、结果不确定）。环境变量优先级高于 .env，这里统一清空。
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
# 同理，不读开发者本机的外部连接器配置
os.environ["ADVICE_MODE"] = "false"
os.environ["BROKER"] = "none"
os.environ["SKILLS_DIR"] = str(_TMP_DIR / "skills")   # 默认没有技能，免得示例技能的触发词影响别的测试
os.environ["WATCH_ENABLED"] = "false"
os.environ["CONNECTORS_FILE"] = str(_TMP_DIR / "connectors.json")

import pytest  # noqa: E402 — 必须在设置 DB_PATH 之后


@pytest.fixture(autouse=True)
def _no_network_security_resolution(monkeypatch):
    """编排器在规划前会解析证券（要拉全市场快照、打搜索接口）。测试里一律不联网：
    默认解析不出任何证券；需要解析结果的测试自己再覆盖这几个桩。"""
    from wealthpilot.services.agents import orchestrator
    from wealthpilot.services.agents.planner_agent import PlannerAgent

    async def nothing(*args, **kwargs):
        return []

    monkeypatch.setattr(orchestrator, "resolve_text", nothing)
    monkeypatch.setattr(orchestrator, "resolve_names", nothing)
    monkeypatch.setattr(PlannerAgent, "extract_names", lambda self, *a, **k: [])
    # 全市场快照同理：冒烟测试会扫到选股相关的接口，不能让它们去拉真实数据
    from wealthpilot.services import screener
    monkeypatch.setattr(screener, "_load_snapshot", nothing)
    # 验证点要取财报、估值、日线：默认取不到任何基准值（于是也不会多调一次模型）
    from wealthpilot.services import checkpoints

    async def no_values(code):
        return {}

    monkeypatch.setattr(checkpoints, "current_values", no_values)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_temp_db():
    yield
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
