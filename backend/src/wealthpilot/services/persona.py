"""说话方式：用户自己写的一段话，告诉 Agent 怎么跟自己说话。

放在数据目录下的 SOUL.md（名字沿用 OpenClaw / Hermes 的叫法，方便用过它们的人找到）。
它只管语气、措辞和详略：写进每个 Agent 和最后执笔的那一步的系统提示里，并且明说与规则冲突时以规则为准 ——
证据引用、数字溯源、必须有的章节、风险提示这些不会因为一句"说短点"就被省掉。
文件不存在或是空的，就和以前完全一样。
"""

from __future__ import annotations

import re

from wealthpilot.settings import HOME

FILE = HOME / "SOUL.md"
MAX_CHARS = 1200

PRESETS: dict[str, tuple[str, str]] = {
    "friend": ("懂行的朋友", """像一个懂行的朋友在跟我聊，不是在写报告。
- 先用一两句大白话把结论说出来，再说为什么。
- 少用“综上所述”“值得注意的是”“总体而言”这类套话，也不用每一段都再总结一遍。
- 术语第一次出现时顺口解释一句。
- 拿不准的地方直接说“这个我拿不准”，并说缺什么数据。
- 风险该提醒的地方说一次就够，不用每段都重复。"""),
    "brief": ("只要要点", """我时间少。
- 每一节只留最要紧的一两句话和一个数字。
- 能用一张小表说清的就不用文字。
- 不要铺垫、客套和过渡句。"""),
    "novice": ("讲给新手", """我是新手。
- 少用术语；用了就用一句话解释它是什么、是高了好还是低了好。
- 多打生活里的比方。
- 告诉我这个数字在同类公司里算什么水平。"""),
    "skeptic": ("多泼冷水", """多给我泼冷水，我容易上头。
- 每个看好的理由后面，跟一句它可能错在哪。
- 把最可能让我亏钱的那件事放进结论里说，不要藏在最后。
- 我要是问得很急（“现在能不能买”），先提醒我慢一点，再回答。"""),
}


def read() -> str:
    """现在的说话方式。去掉 HTML 注释（模板里的说明）和首尾空白；太长就截断。"""
    try:
        text = FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()
    return text[:MAX_CHARS]


def write(text: str) -> str:
    text = (text or "").strip()
    if len(text) > MAX_CHARS:
        raise ValueError(f"太长了（{len(text)} 字）。这段话每次研究都会带给模型，控制在 {MAX_CHARS} 字以内")
    if not text:
        FILE.unlink(missing_ok=True)
        return ""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(text + "\n", encoding="utf-8")
    return text


def use(name: str) -> str:
    key = (name or "").strip().lower()
    key = next((k for k, (label, _) in PRESETS.items() if label == name.strip()), key)
    if key not in PRESETS:
        raise ValueError(f"没有「{name}」这个预设。可选：{'、'.join(f'{k}（{label}）' for k, (label, _) in PRESETS.items())}")
    return write(PRESETS[key][1])


def block() -> str:
    """拼进系统提示的那一段。没写就是空串。"""
    text = read()
    if not text:
        return ""
    return ("\n## 用户希望你这样跟他说话\n"
            "下面是用户自己写的，只管语气、措辞和详略。与上面的规则冲突时以规则为准："
            "事实、数字、证据引用、要求的章节和必要的风险提示都不能因此省掉或改动。\n"
            f"<<<\n{text}\n>>>\n")
