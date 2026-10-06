"""从一篇回答里取出"结论卡"要的东西：几句话的结论，和立场。

回答动辄几千字。结论卡让人先看到结论，再决定要不要读全文；个股页的判断卡、手机推送用的也是它。
"""

from __future__ import annotations

import re

STANCES = "看多|中性偏多|中性偏空|中性|看空"
_STANCE_RE = re.compile(rf"立场[^\n]{{0,12}}?({STANCES})")
_SECTION_RE = re.compile(r"^#{1,3}[^\n]*结论[^\n]*\n(.*?)(?=^#{1,3} |\Z)", re.DOTALL | re.MULTILINE)


def conclusion(answer: str, limit: int = 320) -> str:
    """「结论」一节的正文；没有这一节就取开头的正文段落。去掉证据标记和 Markdown 符号。"""
    match = _SECTION_RE.search(answer)
    if match:
        text = match.group(1)
    else:   # 没有结论一节：跳过标题和表格，从第一段正文取
        text = "\n".join(line for line in answer.splitlines() if line.strip() and not line.lstrip().startswith(("#", "|", "---")))
    # ">" 只在行首是引用符号，句子里的"茅台 > 五粮液"要留着
    text = re.sub(r"\[E-[a-f0-9]+\]|[*`#|]|^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r" ([，。；：、）])", r"\1", text)[:limit]


def stance(answer: str, name: str = "") -> str:
    """回答里写的立场。对比研究里一行写了几只股票的立场，按名字取对应的那一个。"""
    if name:
        named = re.search(rf"立场[^\n]*?{re.escape(name)}[^\n，；。]{{0,6}}?({STANCES})", answer)
        if named:
            return named.group(1)
    match = _STANCE_RE.search(answer)
    return match.group(1) if match else ""


def card(answer: str, limit: int = 240) -> dict | None:
    """结论卡。短回答本身就是结论，不需要卡片。"""
    if len(answer) < 500:
        return None
    full = conclusion(answer, 2000)
    if not full:
        return None
    text = full[:limit]
    if len(full) > limit:
        # 停在一句话的末尾，而不是从句子中间截断
        end = max(text.rfind("。"), text.rfind("；"), text.rfind("！"), text.rfind("？"))
        text = text[:end + 1] if end >= 60 else text
    return {"conclusion": text, "stance": stance(answer), "truncated": len(full) > len(text)}
