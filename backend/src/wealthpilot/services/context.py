"""Agent 运行上下文 —— Web、CLI、MCP 三个入口共用同一套加载逻辑。"""

from __future__ import annotations

import asyncio

from sqlmodel import Session

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.assets import fetch_prices_by_type
from wealthpilot.services.deps import user_holdings
from wealthpilot.services.market_data import fetch_fund_nav


async def load_market_context(
    holdings: list[PortfolioHolding], history_days: int = 60
) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """并发取各持仓的最新价与净值历史。取不到价格时退回成本价。"""
    codes = list(dict.fromkeys(h.fund_code for h in holdings))
    prices, histories = await asyncio.gather(
        fetch_prices_by_type([(h.fund_code, h.asset_type) for h in holdings]),
        asyncio.gather(*[fetch_fund_nav(c, history_days) for c in codes], return_exceptions=True),
    )
    nav_data = {h.fund_code: prices.get(h.fund_code, h.cost_price) for h in holdings}
    nav_history = {c: hist for c, hist in zip(codes, histories, strict=True)
                   if hist and not isinstance(hist, BaseException)}
    return nav_data, nav_history


def load_local_user(
    user_id: int,
) -> tuple[list[PortfolioHolding], InvestorProfile | None]:
    """CLI / MCP 用：取本机某个用户的持仓与画像（默认匿名档 0，由 LOCAL_USER_ID 配置）。"""
    from wealthpilot.routes.profile import load_profile
    from wealthpilot.storage.db import get_engine

    with Session(get_engine()) as session:
        return user_holdings(session, user_id), load_profile(session, user_id)
