"""RiskAgent — 风险管理专家。"""

from anthropic import Anthropic

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.base import BaseAgent
from wealthpilot.services.agents.prompts import build_risk_prompt
from wealthpilot.services.agents.tools import RISK_TOOLS


class RiskAgent(BaseAgent):
    def __init__(
        self,
        client: Anthropic,
        model: str,
        holdings: list[PortfolioHolding],
        nav_data: dict[str, float],
        nav_history: dict[str, list[dict]] | None = None,
    ):
        super().__init__(
            name="risk",
            tools=RISK_TOOLS,
            system_prompt=build_risk_prompt(holdings, nav_data),
            client=client,
            model=model,
            holdings=holdings,
            nav_data=nav_data,
            nav_history=nav_history,
        )
