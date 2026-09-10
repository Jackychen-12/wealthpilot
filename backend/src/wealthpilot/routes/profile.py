"""投资者画像路由 — 风险测评结果的落库与读取。"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from wealthpilot.models.profile import RISK_LABELS, InvestorProfile
from wealthpilot.models.schemas import ProfileResponse, ProfileUpsert
from wealthpilot.services.deps import ANONYMOUS_USER_ID, current_user_id
from wealthpilot.storage.db import get_session

router = APIRouter(prefix="/profile", tags=["profile"])

def load_profile(db: Session, user_id: int = ANONYMOUS_USER_ID) -> InvestorProfile | None:
    """供 chat 路由复用：取指定用户的画像，没有就返回 None。"""
    return db.exec(
        select(InvestorProfile).where(InvestorProfile.user_id == user_id)
    ).first()


def _to_response(p: InvestorProfile) -> ProfileResponse:
    return ProfileResponse(
        risk_level=p.risk_level,
        risk_label=p.risk_label,
        horizon_months=p.horizon_months,
        max_drawdown_tolerance=p.max_drawdown_tolerance,
        liquidity_reserve=p.liquidity_reserve,
        experience_years=p.experience_years,
        available_cash=p.available_cash,
        excluded_industries=p.excluded_list,
        raw_score=p.raw_score,
        updated_at=p.updated_at.isoformat(),
        is_stale=p.is_stale(),
    )


@router.get("", response_model=ProfileResponse | None)
def get_profile(
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """获取当前风险画像。未测评返回 null。"""
    p = load_profile(db, user_id)
    return _to_response(p) if p else None


@router.put("", response_model=ProfileResponse)
def upsert_profile(
    req: ProfileUpsert,
    db: Session = Depends(get_session),
    user_id: int = Depends(current_user_id),
):
    """提交/更新风险测评结果。"""
    p = load_profile(db, user_id)
    if p is None:
        p = InvestorProfile(user_id=user_id)
        db.add(p)

    p.risk_level = req.risk_level
    p.horizon_months = req.horizon_months
    p.max_drawdown_tolerance = req.max_drawdown_tolerance
    p.liquidity_reserve = req.liquidity_reserve
    p.experience_years = req.experience_years
    p.available_cash = req.available_cash
    p.excluded_industries = ",".join(req.excluded_industries)
    p.raw_score = req.raw_score
    p.updated_at = datetime.now()

    db.commit()
    db.refresh(p)
    return _to_response(p)


@router.get("/labels")
def get_labels():
    """风险等级字典，供前端展示。"""
    return {"levels": [{"level": k, "label": v} for k, v in sorted(RISK_LABELS.items())]}
