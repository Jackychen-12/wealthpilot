"""升级：现在是哪一版、有没有新的、怎么升。

WealthPilot 从源码仓库运行，所以“升级”就是把仓库拉到最新、装好依赖、重新构建网页版。
这里把这几步收成一条命令，并且先备份数据库、发现本地改动就停下来问，而不是覆盖。
检查更新只读取本仓库的远端（git fetch），不上传任何东西；可以在设置里关掉。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from wealthpilot import __version__
from wealthpilot.services import cache
from wealthpilot.settings import get_settings

REPO = Path(__file__).resolve().parents[4]
BRANCH = "main"
KEEP_BACKUPS = 5


_DOCKER_HOW = "这是打包好的镜像，没有源码仓库。升级：docker compose pull（或重新构建）后 docker compose up -d，数据在卷里不受影响。"


def _git(*args: str, timeout: float = 20) -> tuple[int, str]:
    try:
        # 不让 git 停下来等人输入账号密码：没有终端的后台进程里那会一直挂到超时
        out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout,
                             env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, stdin=subprocess.DEVNULL)
        # 只去掉结尾的换行：git status --porcelain 每行开头的空格是有意义的
        return out.returncode, out.stdout.rstrip() if out.stdout.strip() else out.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, type(e).__name__


def is_checkout() -> bool:
    return (REPO / ".git").exists() and shutil.which("git") is not None


def current() -> dict:
    out = {"version": __version__, "git": is_checkout(), "commit": "", "branch": "", "dirty": []}
    if out["git"]:
        out["commit"] = _git("rev-parse", "--short", "HEAD")[1]
        out["branch"] = _git("rev-parse", "--abbrev-ref", "HEAD")[1]
        out["dirty"] = [line[3:] for line in _git("status", "--porcelain", "--untracked-files=no")[1].splitlines() if len(line) > 3]
    return out


def release_notes(changelog: str, newer_than: str = "") -> list[dict]:
    """从 CHANGELOG 里取出各版本的条目；给了 newer_than 就只要比它新的。"""
    notes: list[dict] = []
    for block in re.split(r"^## ", changelog, flags=re.MULTILINE)[1:]:
        head, _, body = block.partition("\n")
        match = re.match(r"\[?v?(\d+\.\d+\.\d+)\]?(?:\s*[-—–]\s*(\S+))?", head.strip())
        if not match:
            continue
        if newer_than and _key(match.group(1)) <= _key(newer_than):
            break
        items = [re.sub(r"^[-*]\s+", "", line.strip()) for line in body.splitlines() if re.match(r"\s*[-*]\s+\S", line)]
        notes.append({"version": match.group(1), "date": match.group(2) or "", "items": items})
    return notes


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def status() -> dict:
    """现在的版本，加上最近一次检查的结果。只读缓存、不联网 —— 页面一打开就要用，不能等网络。"""
    info = current()
    if not info["git"]:
        return {**info, "checked": False, "behind": 0, "notes": [], "how": _DOCKER_HOW}
    hit = cache.read("upgrade:check", 7 * cache.DAY)
    if hit and hit.get("commit") == info["commit"]:
        return {**info, **hit, "cached": True}
    return {**info, "checked": False, "behind": 0, "notes": [], "how": "还没有检查过更新"}


def check(*, force: bool = False) -> dict:
    """看远端有没有新提交（会联网）。结果缓存 12 小时；没有 git、没有网络都返回“不知道”，不报错。"""
    info = current()
    if not info["git"]:
        return {**info, "checked": False, "behind": 0, "notes": [], "how": _DOCKER_HOW}
    hit = None if force else cache.read("upgrade:check", 12 * cache.HOUR)
    if hit and hit.get("commit") == info["commit"]:
        return {**info, **hit, "cached": True}
    code, _ = _git("fetch", "--quiet", "origin", BRANCH, timeout=10)
    if code != 0:
        return {**info, "checked": False, "behind": 0, "notes": [], "how": "没能连上远端仓库，稍后再试"}
    behind = int(_git("rev-list", "--count", f"HEAD..origin/{BRANCH}")[1] or 0)
    code, changelog = _git("show", f"origin/{BRANCH}:CHANGELOG.md")
    notes = release_notes(changelog, __version__) if code == 0 else []
    result = {"checked": True, "behind": behind, "notes": notes, "latest_version": notes[0]["version"] if notes else __version__,
              "commit": info["commit"], "checked_at": datetime.now().isoformat(timespec="seconds"),
              "how": "在终端里运行：wealthpilot update" if behind else ""}
    cache.write("upgrade:check", result)
    return {**info, **result}


def notice() -> str:
    """启动时用的一句话提示。只读缓存，不联网，不拖慢启动；没有新版本返回空串。"""
    if not get_settings().update_check:
        return ""
    hit = status()
    if not hit.get("behind"):
        return ""
    latest = hit.get("latest_version") or ""
    what = f"新版本 {latest}" if latest and _key(latest) > _key(__version__) else f"{hit['behind']} 处更新"
    return f"有{what}可用，运行 wealthpilot update 升级"


def backup_db() -> Path | None:
    """升级前把数据库拷一份。只留最近几份。"""
    db = Path(get_settings().db_path)
    if not db.is_file():
        return None
    folder = db.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{db.stem}-v{__version__}-{datetime.now():%Y%m%d-%H%M%S}{db.suffix}"
    shutil.copy2(db, target)
    for old in sorted(folder.glob(f"{db.stem}-v*{db.suffix}"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return target


def update(say=print) -> bool:
    """把仓库升到最新。任何一步不对就停下并说明，不强行覆盖用户的改动。"""
    info = current()
    if not info["git"]:
        say(check()["how"])
        return False
    if info["branch"] != BRANCH:
        say(f"当前在分支 {info['branch']}，不是 {BRANCH}。升级只在 {BRANCH} 上做：先 git switch {BRANCH}，再运行 wealthpilot update。")
        return False
    if info["dirty"]:
        say("仓库里有没提交的改动，升级会和它们冲突，先处理掉（提交、或 git stash）：")
        for path in info["dirty"][:10]:
            say(f"  {path}")
        return False
    say("检查更新…")
    status = check(force=True)
    if not status["checked"]:
        say(status["how"])
        return False
    if not status["behind"]:
        say(f"已经是最新（v{__version__} · {info['commit']}）。")
        return True
    saved = backup_db()
    if saved:
        say(f"数据库已备份到 {saved}")
    say(f"拉取 {status['behind']} 处更新…")
    code, out = _git("pull", "--ff-only", "origin", BRANCH, timeout=120)
    if code != 0:
        say(f"拉取失败：{out[:300]}")
        return False
    steps = [("安装依赖", ["uv", "sync", "--inexact", "--extra", "feishu"], REPO / "backend"),
             ("安装网页版依赖", ["npm", "install", "--no-audit", "--no-fund"], REPO / "workbench"),
             ("构建网页版", ["npm", "run", "build", "--", "--outDir", "dist-app", "--emptyOutDir"], REPO / "workbench")]
    for label, command, cwd in steps:
        if shutil.which(command[0]) is None:
            say(f"跳过「{label}」：找不到 {command[0]}。之后在仓库目录运行 make setup 补上。")
            continue
        say(f"{label}…")
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        if done.returncode != 0:
            say(f"「{label}」失败：{(done.stderr or done.stdout).strip()[-400:]}")
            say("代码已经更新。在仓库目录运行 make setup 把剩下的步骤补上。")
            return False
    for note in status["notes"]:
        say(f"\nv{note['version']} {note['date']}")
        for item in note["items"]:
            say(f"  · {item}")
    say("\n升级完成。重新运行 wealthpilot 生效；数据库的新字段会在启动时自动补上。")
    return True
