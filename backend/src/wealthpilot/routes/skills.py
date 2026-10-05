"""技能：用户自己写的研究方法。读取谁都可以；写入只允许本机（它会改 Agent 的行为）。"""

from fastapi import APIRouter, HTTPException, Request

from wealthpilot.routes.config import _local_only
from wealthpilot.services import skills

router = APIRouter(prefix="/skills", tags=["skills"])

TEMPLATE = """---
name: my-method
description: 一句话说明这个方法做什么
whenToUse: 什么时候该用它
user-invocable: true
metadata:
  wealthpilot:
    label: 我的方法
    triggers: [触发词一, 触发词二]
    needs: stock            # stock 一只股票 / stocks 多只 / holdings 我的持仓 / none 不需要
    agents: [fundamental, valuation]
    sections: [结论, 依据, 风险]
    criteria:
      - 必须取得的证据
---

# 我的方法

- fundamental: 让基本面 Agent 具体查什么、重点看什么
- valuation: 让估值 Agent 具体查什么

成文时的要求写在这里。
"""


@router.get("")
def list_skills():
    found, invalid = skills.discover()
    return {"skills": [s.summary() for s in found], "invalid": invalid, "dirs": [str(r) for r in skills.roots()], "template": TEMPLATE}


@router.get("/{name}")
def read_skill(name: str):
    skill = skills.get(name)
    if skill is None:
        raise HTTPException(404, "没有这个技能")
    try:
        with open(skill.path, encoding="utf-8") as f:
            return {**skill.summary(), "content": f.read()}
    except OSError as e:
        raise HTTPException(500, f"读不了技能文件：{e}") from e


@router.put("/{name}")
def save_skill(name: str, body: dict, request: Request):
    _local_only(request)
    try:
        return skills.save(name, str(body.get("content") or "")).summary()
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/{name}")
def delete_skill(name: str, request: Request):
    _local_only(request)
    if not skills.delete(name):
        raise HTTPException(404, "没有这个技能，或它不在项目技能目录里")
    return {"ok": True}
