"""情景分析路由。"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from wealthpilot.services import scenario as scenario_svc
from wealthpilot.services.assets import fetch_prices_by_type
from wealthpilot.services.deps import current_user_id, user_holdings
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/scenario", tags=["scenario"])


async def _nav_data(holdings) -> dict:
    prices = await fetch_prices_by_type(
        [(h.fund_code, getattr(h, "asset_type", "fund")) for h in holdings]
    )
    return {h.fund_code: prices.get(h.fund_code, h.cost_price) for h in holdings}


@router.get("/presets")
def presets():
    """可用的预设情景。"""
    return {
        "presets": [
            {"key": k, "label": v["label"], "description": v["description"]}
            for k, v in scenario_svc.PRESET_SCENARIOS.items()
        ]
    }


@router.get("")
async def run_all(
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """跑完所有预设情景，按损益排序 —— 回答"我的组合最怕什么"。"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"scenarios": [], "message": "暂无持仓"}
    return scenario_svc.run_all_presets(holdings, await _nav_data(holdings))


@router.get("/{scenario_key}")
async def run_one(
    scenario_key: str,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """跑单个预设情景，给出逐持仓损益。"""
    holdings = user_holdings(db, user_id)
    if not holdings:
        return {"error": "暂无持仓"}
    return scenario_svc.run_preset(holdings, await _nav_data(holdings), scenario_key)
