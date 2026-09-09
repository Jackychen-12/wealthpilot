"""MarketAgent — 市场数据查询专家。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import BaseAgent
from wealthpilot.services.agents.prompts import build_market_prompt
from wealthpilot.services.agents.tools import MARKET_TOOLS

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient


class MarketAgent(BaseAgent):
    def __init__(
        self,
        client: AIClient,
        model: str,
        profile: InvestorProfile | None = None,
    ):
        super().__init__(
            name="market",
            tools=MARKET_TOOLS,
            system_prompt=build_market_prompt(profile),
            client=client,
            model=model,
            profile=profile,
        )
