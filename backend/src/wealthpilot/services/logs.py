"""日志：后台出的事记在一个文件里，出了问题有地方查。

以前研究在后台跑挂了、推送没发出去、盯盘那一次出了错，都只是被悄悄兜住，事后无从查起。
这里把它们写进数据目录下的 logs/wealthpilot.log（单个 1 MB，留最近 3 份）。只在本机，不上传。
不记 Key、不记回答全文；提问只记开头一小段，够认出是哪一次就行。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from wealthpilot.settings import HOME

LOG_DIR = HOME / "logs"
LOG_FILE = LOG_DIR / "wealthpilot.log"
_STAMP = "%Y-%m-%d %H:%M:%S"
_SECRET_RE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{6,}|Bearer\s+\S{8,}|bot\d{6,}:[A-Za-z0-9_\-]{20,})")
_BAD = (" WARNING ", " ERROR ", " CRITICAL ")


class _Redact(logging.Filter):
    """兜底：异常文字里万一带着 Key 或令牌，写进文件之前抹掉。"""

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        clean = _SECRET_RE.sub(lambda m: m.group(1)[:3] + "…", text)
        if clean != text:
            record.msg, record.args = clean, None
        return True


def setup() -> Path:
    """接上日志文件。可以重复调用；数据目录不可写时不报错，只是没有日志。"""
    root = logging.getLogger("wealthpilot")
    if any(getattr(h, "_wealthpilot", False) for h in root.handlers):
        return LOG_FILE
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return LOG_FILE
    handler._wealthpilot = True   # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", _STAMP))
    handler.addFilter(_Redact())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False        # 不往终端打：终端是给人对话用的
    return LOG_FILE


def brief(text: str, limit: int = 30) -> str:
    """提问只记开头一小段。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _records() -> list[str]:
    """文件里的记录，旧的在前。一条记录可能有好几行（带着出错的调用栈），合在一起算一条。"""
    if not LOG_FILE.is_file():
        return []
    records: list[str] = []
    for line in LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", line) or not records:
            records.append(line)
        else:
            records[-1] += "\n" + line
    return records


def tail(count: int = 50, *, errors: bool = False) -> list[str]:
    records = [r for r in _records() if not errors or any(mark in r[:60] for mark in _BAD)]
    return records[-max(1, count):]


def recent_problems(hours: int = 24) -> int:
    """最近这段时间里有多少条警告和错误。给自检用。"""
    since = (datetime.now() - timedelta(hours=hours)).strftime(_STAMP)
    return sum(1 for r in _records() if r[:19] >= since and any(mark in r[:60] for mark in _BAD))


def follow(poll: float = 1.0, rounds: int | None = None) -> Iterator[str]:
    """从调用这一刻起新写进来的行，一直跟着（Ctrl-C 停）。rounds 只在测试里用。"""
    start = LOG_FILE.stat().st_size if LOG_FILE.is_file() else 0     # 起点在调用时就定下，不等到第一次取值

    def lines(position: int, left: int | None) -> Iterator[str]:
        while left is None or left > 0:
            if LOG_FILE.is_file():
                size = LOG_FILE.stat().st_size
                if size < position:       # 文件轮换了：从头读新的那一份
                    position = 0
                if size > position:
                    with LOG_FILE.open(encoding="utf-8", errors="replace") as f:
                        f.seek(position)
                        chunk = f.read()
                        position = f.tell()
                    yield from chunk.splitlines()
            if left is not None:
                left -= 1
            time.sleep(poll)
    return lines(start, rounds)
