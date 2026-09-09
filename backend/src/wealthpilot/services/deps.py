"""共享依赖 — 当前用户身份与按用户隔离的数据访问。

背景：模型上一直有 `user_id` 字段、JWT 认证也做了，但所有持仓查询写的都是
裸 `select(PortfolioHolding)`，没有任何过滤；更新与删除则直接 `db.get(id)`，
不校验归属。结果是任何登录用户都能读到、甚至改删其他人的持仓。

这里把"当前用户是谁"和"取这个用户的持仓"收敛成两个函数，路由层不再自己拼查询，
避免以后新增接口时又漏掉过滤。

匿名访问返回 user_id = 0 —— 与模型上 `0=公共/未登录` 的约定一致，这样
"不登录也能试用演示数据"这条产品能力不受影响。
"""

from __future__ import annotations

from fastapi import Depends, Header
from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.auth import decode_token

ANONYMOUS_USER_ID = 0


def current_user_id(authorization: str = Header(default="")) -> int:
    """从 Authorization 头解析用户 id。

    未登录、令牌缺失、过期或非法一律返回 ANONYMOUS_USER_ID，而不是抛 401 ——
    这些接口对匿名用户开放（演示模式），隔离靠的是"匿名用户只能看到匿名数据"。
    """
    if not authorization:
        return ANONYMOUS_USER_ID

    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    payload = decode_token(token)
    if not payload:
        return ANONYMOUS_USER_ID

    try:
        return int(payload.get("sub", ANONYMOUS_USER_ID))
    except (TypeError, ValueError):
        return ANONYMOUS_USER_ID


CurrentUserId = Depends(current_user_id)


def user_holdings(db: Session, user_id: int) -> list[PortfolioHolding]:
    """取指定用户的持仓。所有读取路径都必须走这里，不要自己拼 select。"""
    stmt = (
        select(PortfolioHolding)
        .where(PortfolioHolding.user_id == user_id)
        .order_by(PortfolioHolding.created_at)
    )
    return list(db.exec(stmt).all())


def owned_holding(db: Session, holding_id: int, user_id: int) -> PortfolioHolding | None:
    """按 id 取持仓，但仅当它属于该用户。

    刻意不区分"不存在"与"不属于你"—— 两种情况都返回 None，由调用方统一报 404，
    避免通过响应差异枚举出别人有哪些持仓 id。
    """
    holding = db.get(PortfolioHolding, holding_id)
    if holding is None or holding.user_id != user_id:
        return None
    return holding
