"""备份与恢复：打得出来、放得回去、恢复错了能回头，而且不会被一个乱七八糟的压缩包骗。"""

import argparse
import io
import tarfile
from datetime import date
from pathlib import Path

import pytest
from sqlmodel import Session, select

from wealthpilot import cli
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.routes.config import ENV_FILE
from wealthpilot.services import backup
from wealthpilot.settings import get_settings, reload_settings
from wealthpilot.storage.db import get_engine

CODE = "688981"


@pytest.fixture(autouse=True)
def _own_state(monkeypatch):
    assert "wealthpilot-test-" in str(backup.BACKUP_DIR)
    for name in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    ENV_FILE.write_text("AI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-test-backup-key-1111\nWATCH_TIME=15:10\n", encoding="utf-8")
    reload_settings()
    skills = Path(get_settings().skills_dir)
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "my-check.md").write_text("---\nname: my-check\ndescription: 我自己的检查\n---\n正文\n", encoding="utf-8")
    _holding(100)
    yield
    _holding(None)
    (skills / "my-check.md").unlink(missing_ok=True)
    ENV_FILE.unlink(missing_ok=True)
    reload_settings()
    for file in backup.BACKUP_DIR.glob("*.tar.gz"):
        file.unlink()


def _holding(shares: float | None) -> float | None:
    """设成这么多股（None 表示删掉），返回改之前有多少。"""
    with Session(get_engine()) as db:
        row = db.exec(select(PortfolioHolding).where(PortfolioHolding.fund_code == CODE, PortfolioHolding.user_id == 0)).first()
        before = row.shares if row else None
        if row is not None:
            db.delete(row)
            db.commit()
        if shares is not None:
            db.add(PortfolioHolding(user_id=0, fund_code=CODE, fund_name="中芯国际", shares=shares, cost_price=50, asset_type="stock", buy_date=date(2026, 1, 5)))
            db.commit()
    return before


def _shares() -> float | None:
    with Session(get_engine()) as db:
        row = db.exec(select(PortfolioHolding).where(PortfolioHolding.fund_code == CODE, PortfolioHolding.user_id == 0)).first()
        return row.shares if row else None


def _env(archive: Path) -> str:
    with tarfile.open(archive) as tar:
        return tar.extractfile("env").read().decode()


def test_backup_then_restore_brings_everything_back():
    archive = backup.create()
    info = backup.inspect(archive)
    assert oct(archive.stat().st_mode)[-3:] == "600" and info["with_keys"] is True
    assert info["contents"][0] == "数据库" and "配置（含 Key）" in info["contents"] and any(c.startswith("研究方法") for c in info["contents"])
    # 之后把东西改乱
    _holding(None)
    ENV_FILE.write_text("AI_PROVIDER=anthropic\n", encoding="utf-8")
    (Path(get_settings().skills_dir) / "my-check.md").unlink()
    reload_settings()
    done = backup.restore(archive)
    assert _shares() == 100 and get_settings().ai_provider == "deepseek" and get_settings().deepseek_api_key == "sk-test-backup-key-1111"
    assert (Path(get_settings().skills_dir) / "my-check.md").is_file() and get_settings().watch_time == "15:10"
    # 恢复错了能回头：恢复之前的状态（没有那只股票）也留了一份
    before = Path(done["saved_current_to"])
    assert before.is_file() and "before-restore" in before.name
    backup.restore(before)
    assert _shares() is None and get_settings().ai_provider == "anthropic"


def test_a_backup_without_keys_can_be_shared_and_keeps_your_keys_on_restore():
    archive = backup.create(keys=False)
    assert "sk-test-backup-key" not in _env(archive) and "WATCH_TIME=15:10" in _env(archive)
    assert backup.inspect(archive)["with_keys"] is False and "配置（不含 Key）" in backup.inspect(archive)["contents"]
    ENV_FILE.write_text("AI_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-test-the-new-key-2222\nWATCH_TIME=09:00\n", encoding="utf-8")
    reload_settings()
    backup.restore(archive)
    assert get_settings().watch_time == "15:10" and get_settings().deepseek_api_key == "sk-test-the-new-key-2222"     # 配置回来了，这台机器上的 Key 没丢


def test_a_file_that_is_not_ours_is_refused_and_nothing_is_touched(tmp_path):
    junk = tmp_path / "notes.tar.gz"
    junk.write_bytes(b"not a tarball")
    with pytest.raises(ValueError, match="不是 WealthPilot 的备份"):
        backup.inspect(junk)
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:        # 伪造的清单 + 一个想写到数据目录外面去的文件
        for name, data in (("manifest.json", b'{"app": "wealthpilot", "version": "0", "created_at": "x", "contents": []}'), ("skills/../../evil.md", b"x")):
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="不认识的内容"):
        backup.restore(evil)
    assert _shares() == 100 and not list(backup.BACKUP_DIR.glob("*before-restore*"))      # 没恢复，也没白打一份备份
    with pytest.raises(ValueError, match="没有这个文件"):
        backup.inspect(tmp_path / "missing.tar.gz")


def test_the_commands(tmp_path):
    def run(fn, **kw):
        out: list[str] = []
        code = fn(argparse.Namespace(**kw), out=out.append) if fn is cli.cmd_backup else fn(argparse.Namespace(**kw), ask=lambda p: "n", out=out.append)
        return code, "\n".join(out)
    assert "还没有备份" in run(cli.cmd_backup, dest=None, no_keys=False, list=True)[1]
    code, text = run(cli.cmd_backup, dest=str(tmp_path), no_keys=True, list=False)
    archive = next(tmp_path.glob("wealthpilot-backup-*.tar.gz"))
    assert code == 0 and str(archive) in text and "没有带 Key" in text and "sk-test" not in text
    code, text = run(cli.cmd_backup, dest=None, no_keys=False, list=False)
    assert "带着模型 Key" in text and "数据库" in run(cli.cmd_backup, dest=None, no_keys=False, list=True)[1]
    _holding(None)
    code, text = run(cli.cmd_restore, file=str(archive), yes=False)          # 问了，答 n：什么都不动
    assert code == 1 and "已取消" in text and _shares() is None
    code, text = run(cli.cmd_restore, file=str(archive), yes=True)
    assert code == 0 and "已恢复：数据库" in text and _shares() == 100 and "原有的 Key 保留着" in text
    assert run(cli.cmd_restore, file=str(tmp_path / "nope.tar.gz"), yes=True)[0] == 1
