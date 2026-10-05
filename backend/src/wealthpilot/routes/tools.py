"""工具直调路由 —— 把 Agent 用的全部工具原样暴露给工作台。

Agent 的每项能力（穿透、回测、仓位推演……）背后都是一个确定性工具。工作台的
功能页直接调这些工具，和 AI 研究里看到的证据出自同一份实现，不会出现
"页面上一个数、AI 说另一个数"。
"""

import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session

from wealthpilot.routes.profile import load_profile
from wealthpilot.services.agents.tools import AGENT_TOOLS, execute_tool
from wealthpilot.services.checkpoints import ACTIVE_USER
from wealthpilot.services.context import load_market_context
from wealthpilot.services.deps import current_user_id, user_holdings
from wealthpilot.services.evidence import record_evidence
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/tools", tags=["tools"])

# 一个工具可能被多个 Agent 共用；清单里按它首次出现的 Agent 归组
_TOOLS: dict[str, tuple[str, dict]] = {}
for _group, _tools in AGENT_TOOLS.items():
    for _tool in _tools:
        _TOOLS.setdefault(_tool["name"], (_group, _tool))
# 需要用户持仓才能算的工具；其余只查公开数据，不必为它们去拉整个组合的行情
_NEEDS_HOLDINGS = {t["name"] for t in AGENT_TOOLS["portfolio"]} | {"calculate_return", "get_max_drawdown", "backtest_rule"}


@router.get("")
def list_tools():
    """全部工具及其入参说明，按 Agent 分组。"""
    return [
        {"name": name, "group": group, "description": tool["description"],
         "input_schema": tool["input_schema"]}
        for name, (group, tool) in _TOOLS.items()
    ]


@router.post("/{name}")
async def run_tool(
    name: str,
    inputs: dict = Body(default_factory=dict),
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """执行一个工具。返回 {ok, data, as_of}；data 是工具输出（JSON 则已解析）。"""
    if name not in _TOOLS:
        raise HTTPException(404, f"未知工具：{name}")
    missing = [k for k in _TOOLS[name][1]["input_schema"].get("required", []) if k not in inputs]
    if missing:
        raise HTTPException(422, f"缺少参数：{'、'.join(missing)}")

    ACTIVE_USER.set(user_id)
    holdings = user_holdings(db, user_id) if name in _NEEDS_HOLDINGS else []
    nav_data, nav_history = await load_market_context(holdings) if holdings else ({}, {})
    try:
        output = await execute_tool(name, inputs, holdings, nav_data, nav_history, load_profile(db, user_id))
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"参数有误：{e}") from e

    # 与 Agent 走同一套判定：工具"没取到数据"时不能当成功返回
    evidence = record_evidence(name, inputs, output, nav_history)
    try:
        data = json.loads(output)
    except ValueError:
        data = output
    return {"ok": evidence["status"] == "ok", "data": data, "as_of": evidence["provenance"]["as_of"]}
