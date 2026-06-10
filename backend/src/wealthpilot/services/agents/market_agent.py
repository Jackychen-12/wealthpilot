"""MarketAgent — 市场数据查询专家。"""

from anthropic import Anthropic

from wealthpilot.services.agents.base import BaseAgent
from wealthpilot.services.agents.prompts import build_market_prompt
from wealthpilot.services.agents.tools import MARKET_TOOLS


class MarketAgent(BaseAgent):
    def __init__(self, client: Anthropic, model: str):
        super().__init__(
            name="market",
            tools=MARKET_TOOLS,
            system_prompt=build_market_prompt(),
            client=client,
            model=model,
        )
