"""投资者记忆与审计日志。

记忆：用户明确说过的偏好与纪律（"我不碰白酒""单只不超过两成"）和对建议做过的决定，与对话记录分开存；
新一轮研究开始时带给规划和各个 Agent。只记用户原话里的句子，不让模型替用户总结偏好。

审计：建议、授权、委托、同步、配置变更这些事件只追加、不修改，每条带上一条的哈希。
事件命名沿用 DeepSeek Harness 会话日志的 `domain/action` 约定（approval/asked、approval/decided …）。
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlmodel import Session, select

from wealthpilot.models.memory import AuditEvent, Memory

# 用户在表达长期偏好或纪律的说法。只在命中这些说法时记，记的是用户的原句
_PREFERENCE_RE = re.compile(
    r"记住|记一下|我不(?:买|碰|投|做|考虑|喜欢|接受)|我只(?:买|做|投|考虑|接受)|我的(?:原则|纪律|偏好|底线|风格)|"
    r"以后(?:都|请|不要|别)|不要再(?:给我)?推荐|(?:单只|单票|个股)[^，。；]{0,8}不(?:超过|高于)|我(?:是|属于)[^，。；]{0,6}(?:长线|短线|价值|成长)")
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+")
MAX_IN_PROMPT = 12


def extract_preferences(message: str) -> list[str]:
    """从用户的一句话里挑出表达长期偏好的原句。"""
    found = []
    for sentence in _SENTENCE_RE.findall(message or ""):
        text = sentence.strip(" ，,、")
        if 4 <= len(text) <= 120 and _PREFERENCE_RE.search(text) and not text.endswith(("吗", "么", "?", "？")):
            found.append(re.sub(r"^(?:请)?(?:帮我)?记(?:住|一下)[:：，,\s]*", "", text) or text)
    return found[:3]


def add(db: Session, user_id: int, content: str, *, kind: str = "preference", code: str = "", source: str = "manual") -> Memory | None:
    content = content.strip()[:300]
    if not content:
        return None
    existing = db.exec(select(Memory).where(Memory.user_id == user_id, Memory.content == content)).first()
    if existing:
        return existing
    row = Memory(user_id=user_id, kind=kind, code=code, content=content, source=source)
    db.add(row)
    db.commit()
    db.refresh(row)
    record(db, user_id, "memory/added", content[:80], {"id": row.id, "kind": kind, "code": code, "source": source},
           actor="user" if source in ("manual", "chat") else "system")
    return row


def remove(db: Session, user_id: int, memory_id: int) -> bool:
    row = db.get(Memory, memory_id)
    if row is None or row.user_id != user_id:
        return False
    record(db, user_id, "memory/removed", row.content[:80], {"id": row.id}, actor="user")
    db.delete(row)
    db.commit()
    return True


def list_memories(db: Session, user_id: int) -> list[Memory]:
    return list(db.exec(select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at.desc())).all())


def serialize(m: Memory) -> dict:
    return {"id": m.id, "kind": m.kind, "code": m.code, "content": m.content, "source": m.source, "created_at": m.created_at.isoformat()}


def note(db: Session, user_id: int, codes: list[str] | None = None) -> str:
    """带给本轮研究的记忆：通用的全带，针对某只证券的只在研究它时带。"""
    codes = set(codes or [])
    rows = [m for m in list_memories(db, user_id) if not m.code or m.code in codes][:MAX_IN_PROMPT]
    if not rows:
        return ""
    label = {"preference": "偏好", "decision": "决定", "note": "备注"}
    return ("用户此前明确说过的偏好和做过的决定（必须尊重；本次结论与其中某条冲突时要明说，不要悄悄违背）：\n"
            + "\n".join(f"- [{label.get(m.kind, m.kind)}] {m.content}" for m in rows) + "\n\n")


# ── 审计日志 ────────────────────────────────────────────

def _digest(prev_hash: str, kind: str, actor: str, summary: str, payload_json: str, at: str) -> str:
    return hashlib.sha256("\x1f".join((prev_hash, kind, actor, summary, payload_json, at)).encode()).hexdigest()


def record(db: Session, user_id: int, kind: str, summary: str = "", payload: dict | None = None, *, actor: str = "system") -> None:
    """追加一条审计事件。审计写不进去不应该让业务失败，所以这里吞掉异常。"""
    try:
        last = db.exec(select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.id.desc()).limit(1)).first()
        event = AuditEvent(user_id=user_id, kind=kind, actor=actor, summary=summary[:200],
                           payload_json=json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str),
                           prev_hash=last.hash if last else "")
        event.hash = _digest(event.prev_hash, kind, actor, event.summary, event.payload_json, event.at.isoformat())
        db.add(event)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def events(db: Session, user_id: int, limit: int = 100, kind: str = "") -> list[dict]:
    stmt = select(AuditEvent).where(AuditEvent.user_id == user_id)
    if kind:
        stmt = stmt.where(AuditEvent.kind.startswith(kind))
    rows = db.exec(stmt.order_by(AuditEvent.id.desc()).limit(max(1, min(limit, 500)))).all()
    return [{"id": e.id, "at": e.at.isoformat(), "kind": e.kind, "actor": e.actor, "summary": e.summary,
             "payload": json.loads(e.payload_json or "{}"), "hash": e.hash[:12]} for e in rows]


def verify(db: Session, user_id: int) -> dict:
    """从头重算哈希链。任何一条被改过、被删掉，都会在这里对不上。"""
    prev = ""
    count = 0
    for e in db.exec(select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.id)).all():
        count += 1
        if e.prev_hash != prev or e.hash != _digest(e.prev_hash, e.kind, e.actor, e.summary, e.payload_json, e.at.isoformat()):
            return {"ok": False, "count": count, "broken_at": e.id}
        prev = e.hash
    return {"ok": True, "count": count, "broken_at": None}
