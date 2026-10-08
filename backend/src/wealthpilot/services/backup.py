"""备份与恢复：把你的东西打成一个文件，换电脑、重装、想回到某一天的时候用。

打进去的是数据目录里属于你的部分：数据库（持仓、自选、研究记录、验证点、记忆、用量）、配置、
你自己写的研究方法、外部数据连接的配置。代码、日志、之前的备份不打进去。
配置里有模型 Key 和机器人令牌 —— 默认带上（文件权限 600，换电脑时不用重填）；要把备份交给别人或放网盘，用 keys=False 去掉。
恢复之前会先把现在的状态自动备份一份，所以恢复错了也能回去。
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from wealthpilot import __version__
from wealthpilot.settings import HOME, get_settings, reload_settings

BACKUP_DIR = HOME / "backups"
SECRET_KEYS = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "FEISHU_APP_SECRET",
               "WECOM_SECRET", "WECOM_TOKEN", "WECOM_AES_KEY", "JWT_SECRET", "WEB_SEARCH_API_KEY", "DINGTALK_CLIENT_SECRET")
_KEY_RE = re.compile(r"\s*([A-Z0-9_]+)\s*=")
_ALLOWED = re.compile(r"^(manifest\.json|env|connectors\.json|SOUL\.md|data/wealthpilot\.db|skills/[A-Za-z0-9_\-./]+)$")


def _env_file() -> Path:
    return HOME / ".env"


def _is_secret(line: str) -> bool:
    match = _KEY_RE.match(line)
    return bool(match and match.group(1) in SECRET_KEYS)


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), int(datetime.now().timestamp()), 0o600
    tar.addfile(info, io.BytesIO(data))


def _db_snapshot(db: Path) -> bytes:
    """用 SQLite 自己的在线备份取一份一致的拷贝 —— WealthPilot 正开着、正在写也没关系。"""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "copy.db"
        source, dest = sqlite3.connect(db), sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        return target.read_bytes()


def create(dest: Path | str | None = None, *, keys: bool = True, label: str = "backup") -> Path:
    settings = get_settings()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(dest).expanduser() if dest and Path(dest).expanduser().is_dir() else None if dest else BACKUP_DIR
    if folder is None:
        target = Path(dest).expanduser()          # 指定了具体的文件名：照用
    else:
        target, n = folder / f"wealthpilot-{label}-{stamp}.tar.gz", 1
        while target.exists():                    # 同一秒里打了两份（恢复时自动打的那份最容易撞上）：不能把前一份盖掉
            n += 1
            target = folder / f"wealthpilot-{label}-{stamp}-{n}.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    contents: list[str] = []
    with tarfile.open(target, "w:gz") as tar:
        db = Path(settings.db_path)
        if db.is_file():
            _add(tar, "data/wealthpilot.db", _db_snapshot(db))
            contents.append("数据库")
        env = _env_file()
        if env.is_file():
            lines = env.read_text(encoding="utf-8").splitlines()
            kept = lines if keys else [line for line in lines if not _is_secret(line)]
            _add(tar, "env", ("\n".join(kept) + "\n").encode("utf-8"))
            contents.append("配置" + ("（含 Key）" if keys and any(_is_secret(line) for line in lines) else "（不含 Key）"))
        skills_dir = Path(settings.skills_dir)
        count = 0
        for file in sorted(skills_dir.rglob("*.md")) if skills_dir.is_dir() else []:
            name = f"skills/{file.relative_to(skills_dir).as_posix()}"
            if _ALLOWED.match(name):      # 文件名不合规的本来也加载不了，不打进去，免得恢复时自己不认
                _add(tar, name, file.read_bytes())
                count += 1
        if count:
            contents.append(f"研究方法 {count} 个")
        connectors = Path(settings.connectors_file)
        if connectors.is_file():
            _add(tar, "connectors.json", connectors.read_bytes())
            contents.append("数据连接")
        soul = HOME / "SOUL.md"
        if soul.is_file():
            _add(tar, "SOUL.md", soul.read_bytes())
            contents.append("说话方式")
        manifest = {"app": "wealthpilot", "version": __version__, "created_at": datetime.now().isoformat(timespec="seconds"),
                    "with_keys": keys, "contents": contents}
        _add(tar, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    target.chmod(0o600)
    return target


def inspect(archive: Path | str) -> dict:
    """这个备份是什么时候、哪个版本打的、里面有什么。不是 WealthPilot 的备份就抛 ValueError。"""
    path = Path(archive).expanduser()
    if not path.is_file():
        raise ValueError(f"没有这个文件：{path}")
    try:
        with tarfile.open(path, "r:gz") as tar:
            names = tar.getnames()
            for name in names:   # 只认自己打进去的那几样；带 .. 或绝对路径的一律不要
                if not _ALLOWED.match(name) or ".." in Path(name).parts:
                    raise ValueError(f"备份里有不认识的内容（{name}），没有恢复")
            member = tar.extractfile("manifest.json") if "manifest.json" in names else None
            manifest = json.loads(member.read()) if member else None
    except (tarfile.TarError, OSError, json.JSONDecodeError) as e:
        raise ValueError(f"这不是 WealthPilot 的备份文件（{type(e).__name__}）") from e
    if not manifest or manifest.get("app") != "wealthpilot":
        raise ValueError("这不是 WealthPilot 的备份文件")
    return {**manifest, "path": str(path), "files": names}


def restore(archive: Path | str) -> dict:
    """把备份放回来。先把现在的状态备份一份；备份里没带 Key 的话，保留现在的 Key。"""
    from wealthpilot.storage import db as storage

    manifest = inspect(archive)
    settings = get_settings()
    settings.ensure_dirs()
    saved = create(label="before-restore")
    restored: list[str] = []
    with tarfile.open(manifest["path"], "r:gz") as tar:
        def read(name: str) -> bytes:
            return tar.extractfile(name).read()   # type: ignore[union-attr]
        if "data/wealthpilot.db" in manifest["files"]:
            if storage._engine is not None:        # 放开旧文件，免得接着往被换掉的那一份里写
                storage._engine.dispose()
                storage._engine = None
            target = Path(settings.db_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            for stale in (target.with_name(target.name + "-wal"), target.with_name(target.name + "-shm")):
                stale.unlink(missing_ok=True)
            target.write_bytes(read("data/wealthpilot.db"))
            restored.append("数据库")
        if "env" in manifest["files"]:
            lines = read("env").decode("utf-8").splitlines()
            env = _env_file()
            if not manifest.get("with_keys") and env.is_file():   # 备份里没有 Key：现在这台机器上的留着
                lines += [line for line in env.read_text(encoding="utf-8").splitlines() if _is_secret(line)]
            env.write_text("\n".join(lines) + "\n", encoding="utf-8")
            env.chmod(0o600)
            restored.append("配置")
        skill_files = [n for n in manifest["files"] if n.startswith("skills/")]
        if skill_files:
            root = Path(settings.skills_dir)
            for name in skill_files:
                target = root / name[len("skills/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read(name))
            restored.append(f"研究方法 {len(skill_files)} 个")
        if "connectors.json" in manifest["files"]:
            Path(settings.connectors_file).write_bytes(read("connectors.json"))
            restored.append("数据连接")
        if "SOUL.md" in manifest["files"]:
            (HOME / "SOUL.md").write_bytes(read("SOUL.md"))
            restored.append("说话方式")
    reload_settings()
    prune()
    return {"restored": restored, "saved_current_to": str(saved), "manifest": manifest}


def existing() -> list[dict]:
    """数据目录里已有的备份，新的在前。"""
    out = []
    for file in sorted(BACKUP_DIR.glob("wealthpilot-*.tar.gz"), reverse=True) if BACKUP_DIR.is_dir() else []:
        try:
            info = inspect(file)
        except ValueError:
            continue
        out.append({"path": str(file), "created_at": info["created_at"], "version": info["version"], "contents": info["contents"],
                    "size_kb": round(file.stat().st_size / 1024)})
    return out


def prune(keep: int = 10) -> None:
    """恢复前自动打的那些备份只留最近几份，别越攒越多。手动打的不动。"""
    for old in sorted(BACKUP_DIR.glob("wealthpilot-before-restore-*.tar.gz"))[:-keep] if BACKUP_DIR.is_dir() else []:
        old.unlink(missing_ok=True)

