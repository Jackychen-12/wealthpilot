"""自动任务：到点跑的研究、越过条件的提醒。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from wealthpilot.services import automations
from wealthpilot.services.deps import current_user_id
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/automations", tags=["automations"])


def _guard(call):
    try:
        return call()
    except automations.AutomationError as e:
        raise HTTPException(404 if "没有这条" in str(e) else 422, str(e)) from e


@router.get("")
def list_automations(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    settings = get_settings()
    return {"items": [automations.serialize(a) for a in automations.list_all(db, user_id)],
            "metrics": [{"key": k, "label": v[0], "unit": v[1]} for k, v in automations.ALERT_METRICS.items()],
            "daily_runs_max": settings.auto_daily_runs_max, "running": settings.watch_enabled}


@router.post("/schedule/parse")
def parse_schedule(body: dict):
    """把用户写的时间读一遍给他看，确认读对了再存。"""
    schedule = automations.parse_schedule(str(body.get("text") or ""))
    if schedule is None:
        raise HTTPException(422, "没看懂时间。可以写成：每天 08:30、工作日 15:40、每周一 09:00")
    return schedule


@router.post("")
async def create_automation(body: dict, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    auto = _guard(lambda: automations.save(db, user_id, body))
    out = automations.serialize(auto)
    if auto.kind == "alert":
        # 建好就告诉用户现在是多少：离触发还有多远，一眼就知道阈值设得对不对
        out["current"] = await automations.current_value(auto.metric, auto.code)
        out["hit"] = out["current"] is not None and automations.hit(auto, out["current"])
    return out


@router.put("/{automation_id}")
def update_automation(automation_id: int, body: dict, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    return automations.serialize(_guard(lambda: automations.save(db, user_id, body, automation_id)))


@router.delete("/{automation_id}")
def delete_automation(automation_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    _guard(lambda: automations.delete(db, user_id, automation_id))
    return {"ok": True}


@router.post("/{automation_id}/run")
async def run_automation(automation_id: int, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """现在就跑一次：任务立刻研究一遍，提醒立刻判一次。"""
    auto = _guard(lambda: automations.owned(db, user_id, automation_id))
    if auto.kind == "task":
        return await automations.run_task(db, auto, manual=True)
    value = await automations.current_value(auto.metric, auto.code)
    return {**automations.serialize(auto), "current": value, "hit": value is not None and automations.hit(auto, value)}
