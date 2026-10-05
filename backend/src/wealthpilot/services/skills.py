"""技能 —— 用户自己写的研究方法。

内置的研究模板（深度研究、对比、持仓诊断……）是写在代码里的。技能让用户用一个 Markdown 文件
把自己的方法教给 Agent：什么时候用、派哪几个 Agent、各自查什么、报告分哪几节。

文件格式与 DeepSeek Harness 的 skill 一致（`<name>.md` 或 `<name>/SKILL.md`，YAML frontmatter，
必填 name / description，可选 whenToUse），同一个文件在 dsh 里也能当普通技能加载。
WealthPilot 需要的编排信息放在 `metadata.wealthpilot` 下，dsh 会忽略它。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from wealthpilot.settings import get_settings

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONT_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
NEEDS = ("stock", "stocks", "holdings", "none")
MAX_BODY = 4000


@dataclass
class Skill:
    name: str
    description: str
    label: str = ""
    when_to_use: str = ""
    triggers: list[str] = field(default_factory=list)
    needs: str = "stock"
    agents: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)
    body: str = ""
    path: str = ""
    user_invocable: bool = True

    @property
    def key(self) -> str:
        return f"skill:{self.name}"

    def agent_goal(self, agent: str) -> str:
        """正文里 `- <agent>: ……` 这一行就是给那个 Agent 的具体做法。"""
        match = re.search(rf"^\s*[-*]\s*{re.escape(agent)}\s*[:：]\s*(.+)$", self.body, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def summary(self) -> dict:
        return {"name": self.name, "label": self.label or self.name, "description": self.description, "when_to_use": self.when_to_use,
                "triggers": self.triggers, "needs": self.needs, "agents": self.agents, "sections": self.sections,
                "criteria": self.criteria, "path": self.path}


def roots() -> list[Path]:
    return [Path(get_settings().skills_dir), Path.home() / ".wealthpilot" / "skills"]


def parse(text: str, path: str = "") -> tuple[Skill | None, list[str]]:
    """解析一个技能文件。返回（技能, 问题列表）；有问题时技能为 None，问题用人话写清楚。"""
    from wealthpilot.services.agents.registry import AGENTS

    match = _FRONT_RE.match(text.lstrip("﻿"))
    if not match:
        return None, ["文件要以 --- 包起来的 YAML frontmatter 开头"]
    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        return None, [f"frontmatter 不是合法的 YAML：{str(e).splitlines()[0]}"]
    if not isinstance(front, dict):
        return None, ["frontmatter 应该是键值对"]
    meta = ((front.get("metadata") or {}).get("wealthpilot") or {}) if isinstance(front.get("metadata"), dict) else {}
    name, description = str(front.get("name") or "").strip(), str(front.get("description") or "").strip()
    listed = lambda key: [str(x).strip() for x in (meta.get(key) or []) if str(x).strip()] if isinstance(meta.get(key), list) else []  # noqa: E731
    skill = Skill(name=name, description=description, label=str(meta.get("label") or "").strip(),
                  when_to_use=str(front.get("whenToUse") or "").strip(), triggers=listed("triggers"),
                  needs=str(meta.get("needs") or "stock"), agents=listed("agents"), sections=listed("sections"),
                  criteria=listed("criteria"), body=match.group(2).strip()[:MAX_BODY], path=path,
                  user_invocable=front.get("user-invocable", True) is not False)
    problems = []
    if not _NAME_RE.match(name):
        problems.append("name 必填，只能用小写字母、数字和连字符（如 dividend-check）")
    if not description:
        problems.append("description 必填：一句话说明这个方法做什么")
    unknown = [a for a in skill.agents if a not in AGENTS or a == "review"]
    if not skill.agents:
        problems.append("metadata.wealthpilot.agents 至少写一个：" + "、".join(a for a in AGENTS if a != "review"))
    elif unknown:
        problems.append(f"不认识的 Agent：{'、'.join(unknown)}（可用：{'、'.join(a for a in AGENTS if a != 'review')}）")
    if len(skill.agents) > 4:
        problems.append("agents 最多 4 个")
    if skill.needs not in NEEDS:
        problems.append(f"needs 只能是 {' / '.join(NEEDS)}")
    if not skill.sections:
        problems.append("metadata.wealthpilot.sections 至少写一节（报告的章节标题）")
    return (None, problems) if problems else (skill, [])


def discover() -> tuple[list[Skill], list[dict]]:
    """扫描技能目录（只看一层：`<name>.md` 或 `<name>/SKILL.md`）。每次都重新读文件，改完立即生效。"""
    found: dict[str, Skill] = {}
    invalid: list[dict] = []
    for root in roots():
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            file = entry / "SKILL.md" if entry.is_dir() else entry
            if not file.is_file() or file.suffix != ".md" or file.name.startswith("."):
                continue
            try:
                skill, problems = parse(file.read_text(encoding="utf-8"), str(file))
            except OSError as e:
                skill, problems = None, [f"读不了：{e}"]
            if skill is None:
                invalid.append({"path": str(file), "problems": problems})
            elif skill.name not in found:   # 先扫到的优先（项目目录先于用户目录）
                found[skill.name] = skill
    return list(found.values()), invalid


def get(name: str) -> Skill | None:
    return next((s for s in discover()[0] if s.name == name), None)


def match(message: str) -> Skill | None:
    """用户的话里出现了某个技能的触发词、名称或 /name，就用它。按触发词长度优先，免得短词抢了长词。"""
    best: tuple[int, Skill] | None = None
    for skill in discover()[0]:
        if not skill.user_invocable:
            continue
        words = [*skill.triggers, skill.label, f"/{skill.name}"]
        hit = max((len(w) for w in words if w and w in message), default=0)
        if hit and (best is None or hit > best[0]):
            best = (hit, skill)
    return best[1] if best else None


def save(name: str, content: str) -> Skill:
    """把一个技能写进项目技能目录。先校验，不合格不落盘。"""
    skill, problems = parse(content)
    if skill is None:
        raise ValueError("；".join(problems))
    if skill.name != name:
        raise ValueError(f"frontmatter 里的 name（{skill.name}）要和文件名（{name}）一致")
    root = roots()[0]
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(content, encoding="utf-8")
    return skill


def delete(name: str) -> bool:
    if not _NAME_RE.match(name):
        return False
    file = roots()[0] / f"{name}.md"
    if not file.is_file():
        return False
    file.unlink()
    return True
