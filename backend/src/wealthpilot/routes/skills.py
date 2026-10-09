"""技能：用户自己写的研究方法。读取谁都可以；写入只允许本机（它会改 Agent 的行为）。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from wealthpilot.routes.config import _local_only
from wealthpilot.services import skills
from wealthpilot.services.deps import current_user_id
from wealthpilot.storage.db import get_session

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


@router.get("/gallery")
def list_gallery():
    """随项目带的现成方法，标出哪些已经装上了。"""
    return skills.gallery()


@router.post("/gallery/{name}/install")
def install_gallery_skill(name: str, request: Request):
    _local_only(request)
    try:
        return skills.install_from_gallery(name).summary()
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


def _preview(content: str) -> dict:
    skill, problems = skills.parse(content)
    return {"content": content, "skill": skill.summary() if skill else None, "problems": problems}


@router.post("/import")
async def import_skill(body: dict, request: Request):
    """从一个链接取回别人分享的技能文件。只取回并校验，不保存 —— 这是写给 Agent 的指示，要用户自己看过再存。"""
    _local_only(request)
    try:
        url = str(body.get("url") or "")
        content, skill, problems, adapted = skills.prepare(await skills.fetch_remote(url), url)
        return {"content": content, "skill": skill.summary() if skill else None, "problems": problems, "adapted": adapted,
                "note": skills.GENERIC_NOTE.lstrip("> ") if adapted else ""}
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/draft")
async def draft_skill(body: dict, request: Request):
    """按一段描述让模型起草一个技能。同样只返回草稿，不保存。"""
    import asyncio

    from wealthpilot.services.ai_client import create_ai_client
    from wealthpilot.settings import get_settings

    _local_only(request)
    description = str(body.get("description") or "").strip()
    if len(description) < 6:
        raise HTTPException(422, "多说两句：这个方法用来看什么、重点关注哪些东西")
    settings = get_settings()
    try:
        client = create_ai_client(settings)
        content, problems = await asyncio.to_thread(skills.draft, client, settings.active_model, description, str(body.get("base") or ""))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except Exception as e:  # noqa: BLE001 — 模型那边的错误原样告诉用户
        raise HTTPException(502, f"模型没有返回可用的结果：{str(e)[:200]}") from e
    return {**_preview(content), "problems": problems}


@router.get("/suggestions")
def skill_suggestions(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """它注意到的"你老这么问"：同一种问法问过几只股票，可以存成方法。只是提议，起草和保存都要用户点。"""
    from wealthpilot.services import lessons
    return lessons.suggestions(db, user_id)


@router.post("/suggestions/{key}/dismiss")
def dismiss_suggestion(key: str, user_id: int = Depends(current_user_id)):
    from wealthpilot.services import lessons
    lessons.dismiss(user_id, key)
    return {"ok": True}


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
