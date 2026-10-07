"""从自己的对错里学：判断落空就记一条经验，反复出现的问法提议存成方法。

两件事都尽量不花钱：
- 记经验由代码完成 —— 哪条判断、当时怎么想的、实际是多少，照实写下来，下次研究同一只股票时带上；
- 发现"你老这么问"也是代码完成 —— 把问题里的股票名去掉后比对，同一种问法问过三次、涉及两只以上的股票，才提议；
只有用户点了"让它总结一下"或"起草成方法"，才调用一次模型。
"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher

from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.memory import Memory
from wealthpilot.models.review import Checkpoint
from wealthpilot.services import cache, memory
from wealthpilot.services.ai_client import json_mode

_FOREVER = 3650 * cache.DAY


# ── 判断落空：记一条经验 ────────────────────────────────

def from_broken(db: Session, cp: Checkpoint) -> Memory | None:
    """一条验证点被证伪时记下来。只陈述发生了什么，不替它找理由。"""
    from wealthpilot.services.checkpoints import METRICS

    label = METRICS.get(cp.metric, (cp.metric,))[0]
    unit = "%"   # 这里的指标（同比、利润率、负债率、估值分位、涨跌幅）单位都是百分比
    was = f"当时认为{label}会{'不低于' if cp.op == '>=' else '不高于'} {cp.threshold:g}{unit}"
    happened = f"实际是 {cp.actual_value:g}{unit}（{cp.actual_as_of}）" if cp.actual_value is not None else "实际没有达到"
    why = f"当时的理由：{cp.statement}" if cp.statement else ""
    text = f"{cp.name}：{cp.created_at:%Y-%m-%d} 的研究{was}，{happened}，判断落空。{why}".strip()
    return memory.add(db, cp.user_id, text, kind="lesson", code=cp.code, source="checkpoint")


def list_lessons(db: Session, user_id: int) -> list[Memory]:
    return [m for m in memory.list_memories(db, user_id) if m.kind == "lesson"]


# ── 让模型把零散的经验归纳成规律（用户点了才跑） ────────

_REFLECT_SYSTEM = """你在帮一个投研助手复盘它自己过去的判断。下面每一条是它当时设下的一个可核对的判断，以及事后核对的结果。

找出跨股票的规律：它在哪一类判断上反复出错（或一贯靠谱），以后该怎么调整。规则：
1. 最多 3 条，每条一句大白话，不超过 70 个字，写成给它自己的提醒（"对……的判断要……"）。
2. 每条必须有至少两条记录支撑，在 based_on 里列出这些记录的编号。只有一条记录的现象不算规律，不要写。
3. 不要复述单条记录，不要编造记录里没有的事。找不出规律就返回空列表。
只返回 JSON：{"lessons":[{"text":"……","based_on":[1,3]}]}"""


def reflect(db: Session, user_id: int, client, model: str) -> list[Memory]:
    """把已核对的判断交给模型归纳一次。返回新记下的经验。记录太少时不调用模型。"""
    from wealthpilot.services.checkpoints import _describe

    rows = db.exec(select(Checkpoint).where(Checkpoint.user_id == user_id, Checkpoint.status.in_(("held", "broken")))
                   .order_by(Checkpoint.checked_at.desc()).limit(24)).all()
    if len(rows) < 4:
        raise ValueError(f"已核对的判断只有 {len(rows)} 条，太少了，总结不出规律。等核对满 4 条再来。")
    listing = "\n".join(f"{i}. {_describe(cp)}" + (f"；当时的理由：{cp.statement}" if cp.statement else "") for i, cp in enumerate(rows, 1))
    result = client.create(model=model, max_tokens=1500, system=_REFLECT_SYSTEM, messages=[{"role": "user", "content": listing}], **json_mode(client))
    match = re.search(r"\{.*\}", result.text or "", re.DOTALL)
    try:
        items = json.loads(match.group()).get("lessons") if match else []
    except ValueError:
        items = []
    saved = []
    for item in items[:3] if isinstance(items, list) else []:
        text = str((item or {}).get("text") or "").strip()
        based = [i for i in (item or {}).get("based_on") or [] if isinstance(i, int) and 1 <= i <= len(rows)]
        if len(text) < 8 or len(set(based)) < 2:      # 没有两条记录支撑的"规律"不收
            continue
        row = memory.add(db, user_id, text[:120], kind="lesson", source="reflection")
        if row is not None:
            saved.append(row)
    return saved


# ── 反复出现的问法：提议存成方法 ────────────────────────

_FILLER_RE = re.compile(r"帮我|请|麻烦|一下|深度|分析|研究|看看|看下|看一看|怎么样|如何|现在|最近|目前|这只|股票|公司|××|[的吗呢吧啊，,。.？?！!、\s（）()]")
MIN_TIMES, MIN_STOCKS, SIMILAR = 3, 2, 0.72


def _mask(question: str, securities: list[dict]) -> str:
    """把问题里的股票名和代码换成 ××。用户常写简称（"茅台"），所以也去掉和全称重合的那一段。"""
    text = question
    for s in securities or []:
        name, code = str(s.get("name") or ""), str(s.get("code") or "")
        if code:
            text = text.replace(code, "××")
        if name and name in text:
            text = text.replace(name, "××")
        elif name:
            m = SequenceMatcher(None, text, name).find_longest_match(0, len(text), 0, len(name))
            if m.size >= 2:
                text = text[:m.a] + "××" + text[m.a + m.size:]
    return re.sub(r"(××[（(]?××[)）]?)+", "××", text)


def _focus(masked: str) -> str:
    """去掉客套话和占位之后剩下的，才是这句话真正在问的东西。"""
    return _FILLER_RE.sub("", masked)


def suggestions(db: Session, user_id: int) -> list[dict]:
    """找出同一种问法问过好几只股票的情况。已经有方法能接住的、用户说过不要的，不再提。"""
    from wealthpilot.services import skills

    dismissed = set(cache.read(f"skillsuggest:dismissed:{user_id}", _FOREVER) or [])
    answers = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant",
                                                ChatMessage.conversation_id != "").order_by(ChatMessage.id.desc()).limit(120)).all()
    asked: list[dict] = []
    for a in answers:
        try:
            meta = json.loads(a.metadata_json) if a.metadata_json else {}
        except ValueError:
            continue
        stocks = [s for s in meta.get("securities") or [] if s.get("asset_type") in ("stock", "etf")]
        if meta.get("status") not in ("passed", "partial") or not stocks or meta.get("playbook") == "rewrite" or str(meta.get("playbook", "")).startswith("skill:"):
            continue
        q = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "user", ChatMessage.conversation_id == a.conversation_id,
                                              ChatMessage.id < a.id).order_by(ChatMessage.id.desc()).limit(1)).first()
        if q is None or skills.match(q.content) is not None:
            continue
        masked = _mask(q.content, stocks)
        focus = _focus(masked)
        if len(focus) >= 4:      # "帮我分析一下××"去掉客套话就没东西了：那是通用问法，不是一个方法
            asked.append({"question": q.content, "masked": masked, "focus": focus, "code": stocks[0]["code"], "name": stocks[0]["name"]})

    clusters: list[list[dict]] = []
    for item in asked:
        for cluster in clusters:
            if SequenceMatcher(None, cluster[0]["focus"], item["focus"]).ratio() >= SIMILAR:
                cluster.append(item)
                break
        else:
            clusters.append([item])

    out = []
    for cluster in clusters:
        codes = {i["code"] for i in cluster}
        key = hashlib.md5(cluster[0]["focus"].encode()).hexdigest()[:10]
        if len(cluster) < MIN_TIMES or len(codes) < MIN_STOCKS or key in dismissed:
            continue
        examples = [{"question": i["question"], "name": i["name"]} for i in cluster[:4]]
        out.append({
            "key": key, "pattern": cluster[0]["masked"], "times": len(cluster), "stocks": sorted({i["name"] for i in cluster})[:6], "examples": examples,
            # 交给起草环节的描述：照用户自己的原话，不替他概括
            "description": "我经常对不同的股票问同一类问题，想把它固定成一个方法。我是这样问的：" + "；".join(f"「{e['question']}」" for e in examples)
                           + "。请按这些问法里共同关心的东西来写，不要加我没问过的内容。",
        })
    return sorted(out, key=lambda s: -s["times"])


def dismiss(user_id: int, key: str) -> None:
    kept = set(cache.read(f"skillsuggest:dismissed:{user_id}", _FOREVER) or [])
    cache.write(f"skillsuggest:dismissed:{user_id}", sorted(kept | {key}))
