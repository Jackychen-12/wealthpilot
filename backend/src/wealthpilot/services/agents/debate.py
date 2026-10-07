"""多空辩论：同一批证据，交给看多和看空两方各打各的。

一个模型写报告时倾向于把话说圆——优点缺点各列几条，最后"中性偏多"。让两方分别只为一边说话，
能把各自最硬的理由逼出来；撰写环节再判哪一方的证据更站得住。

两方只能用已经取到的证据：每条理由必须挂证据编号，里面的数字过和正文一样的溯源检查，对不上的整条丢掉。
"""

from __future__ import annotations

import asyncio
import json
import re

from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.synthesizer_agent import SynthesizerAgent, check_numeric_grounding
from wealthpilot.services.ai_client import json_mode, raise_if_unavailable

SIDES = {
    "bull": ("看多方", "这只股票现在值得看好"),
    "bear": ("看空方", "这只股票现在需要警惕"),
}
MAX_POINTS = 3
_ID_RE = re.compile(r"E-[a-f0-9]{12}")

_SYSTEM = """你是一场投资辩论里的{side}。研究员已经为「{subject}」取好了证据，你只能用这些证据，论证“{claim}”。

规则：
1. 给出最有力的理由，最多 {limit} 条。每条一句大白话，不超过 60 个字，像在跟朋友讲道理，不要写成报告。
2. 每条必须建立在具体证据上，并列出它依据的证据编号（形如 E-xxxxxxxxxxxx）。数字照抄证据里的原数，不换算、不估算、不凑整。
3. 你只替这一方说话，不需要平衡；但证据里没有的事不能编。找不到够硬的理由就少写，一条都没有就返回空列表。
4. 最后用一句话写出你这一方最大的软肋：对方最可能拿哪个事实来反驳你（weakness）。

只返回 JSON，不要解释：
{{"points":[{{"text":"……","evidence":["E-xxxxxxxxxxxx"]}}],"weakness":"……"}}"""


def _parse(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group()) if match else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def validate(raw: dict, results: list[AgentResult]) -> dict:
    """一方的发言过一遍代码检查：证据编号必须真实存在，数字必须能在证据里找到。不合格的理由直接丢，不修补。"""
    known = {e["id"] for r in results for e in r.evidence if e.get("status", "ok") == "ok"}
    points = []
    for item in (raw.get("points") or [])[:MAX_POINTS + 2]:
        if not isinstance(item, dict):
            continue
        text = _ID_RE.sub("", str(item.get("text") or "")).replace("[]", "").strip()
        cited = [e for e in (item.get("evidence") or []) if isinstance(e, str) and e in known]
        if not text or not cited or check_numeric_grounding(text, results)["ungrounded"]:
            continue
        points.append({"text": text[:120], "evidence": cited[:3]})
    weakness = str(raw.get("weakness") or "").strip()[:120]
    if weakness and check_numeric_grounding(weakness, results)["ungrounded"]:
        weakness = ""
    return {"points": points[:MAX_POINTS], "weakness": weakness}


def _speak(client, model: str, side: str, subject: str, evidence_block: str) -> dict:
    label, claim = SIDES[side]
    result = client.create(model=model, max_tokens=900, **json_mode(client),
                           system=_SYSTEM.format(side=label, subject=subject, claim=claim, limit=MAX_POINTS),
                           messages=[{"role": "user", "content": evidence_block}])
    return _parse(result.text or "")


async def run(client, model: str, subject: str, question: str, results: list[AgentResult]) -> dict | None:
    """两方同时发言。任何一方调用失败、或两方都拿不出站得住的理由，就当没有这场辩论（返回 None），不影响研究照常发布。"""
    block = SynthesizerAgent._build_evidence_block(question, results, budget=500)
    spoken = await asyncio.gather(*[asyncio.to_thread(_speak, client, model, side, subject, block) for side in SIDES],
                                  return_exceptions=True)
    for failure in (s for s in spoken if isinstance(s, Exception)):
        raise_if_unavailable(failure)
    if any(isinstance(s, Exception) for s in spoken):
        return None
    debate = {side: validate(raw, results) for side, raw in zip(SIDES, spoken, strict=True)}
    return debate if debate["bull"]["points"] or debate["bear"]["points"] else None


def brief(debate: dict) -> str:
    """交给撰写环节的那一段：两方说了什么，以及「多空」一节该怎么写。"""
    lines = ["## 多空辩论的结果（两位辩手基于同一批证据，各自只替一方说话）"]
    for side, (label, _) in SIDES.items():
        lines.append(f"{label}：")
        lines += [f"- {p['text']} " + " ".join(f"[{e}]" for e in p["evidence"]) for p in debate[side]["points"]] or ["- （没有拿出站得住的理由）"]
        if debate[side]["weakness"]:
            lines.append(f"  自认的软肋：{debate[side]['weakness']}")
    lines.append("「多空」一节这样写：先各用一两句话转述双方最硬的那条理由（保留证据引用），然后明确说哪一方的证据更站得住、为什么；"
                 "再点出分歧到底取决于哪个现在还不知道的事。不要各打五十大板。结论一节的判断要和这里一致。")
    return "\n".join(lines)
