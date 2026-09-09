"""QuantAgent — 穿透与回测专家。

与其他三个 Agent 的分工：market/portfolio/risk 回答"是什么"和"如果……会怎样"，
QuantAgent 回答"这个判断经不经得起历史检验"，以及"表面之下真实持有的是什么"。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.base import BaseAgent
from wealthpilot.services.agents.prompts import build_quant_prompt
from wealthpilot.services.agents.tools import COMPUTE_TOOLS, QUANT_TOOLS

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient


class QuantAgent(BaseAgent):
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
            name="quant",
            tools=[*QUANT_TOOLS, *COMPUTE_TOOLS],
            system_prompt=build_quant_prompt(holdings, nav_data, profile),
            client=client,
            model=model,
            holdings=holdings,
            nav_data=nav_data,
            nav_history=nav_history,
            profile=profile,
        )
