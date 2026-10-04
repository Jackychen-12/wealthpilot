"""StockAgent — A 股个股 / ETF 专家：行情、走势、估值、财务、行业。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import BaseAgent
from wealthpilot.services.agents.prompts import build_stock_prompt
from wealthpilot.services.agents.tools import STOCK_TOOLS

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient


class StockAgent(BaseAgent):
    def __init__(
        self,
        client: AIClient,
        model: str,
        holdings: list[PortfolioHolding],
        nav_data: dict[str, float],
        nav_history: dict[str, list[dict]] | None = None,
        profile: InvestorProfile | None = None,
    ):
        super().__init__(
            name="stock",
            tools=STOCK_TOOLS,
            system_prompt=build_stock_prompt(holdings, nav_data, profile),
            client=client,
            model=model,
            holdings=holdings,
            nav_data=nav_data,
            nav_history=nav_history,
            profile=profile,
        )
