"""RouterAgent — 意图分类，将用户消息路由到对应专业 Agent。"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from wealthpilot.services.agents.prompts import build_router_prompt

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient


KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["基金", "净值", "新闻", "行情", "市场", "指数", "板块", "估值"], "market"),
    (["持仓", "收益", "配置", "健康", "归因", "总览", "建议", "调仓"], "portfolio"),
    (["风险", "回撤", "相关性", "预警", "对比", "波动", "亏损", "止损"], "risk"),
]


class RouterAgent:
    def __init__(self, client: AIClient, model: str):
        self.client = client
        self.model = model

    def route(self, message: str) -> tuple[str, str]:
        """返回 (agent_name, reason)。"""
        try:
            result = self.client.create(
                model=self.model,
                max_tokens=200,
                system=build_router_prompt(),
                messages=[{"role": "user", "content": message}],
            )
            text = result.text.strip()
            match = re.search(r'\{[^}]+\}', text)
            if match:
                data = json.loads(match.group())
                agent = data.get("agent", "")
                reason = data.get("reason", "")
                if agent in ("market", "portfolio", "risk"):
                    return agent, reason
        except Exception:
            pass

        return self._keyword_fallback(message)

    @staticmethod
    def _keyword_fallback(message: str) -> tuple[str, str]:
        scores: dict[str, int] = {"market": 0, "portfolio": 0, "risk": 0}
        for keywords, agent in KEYWORD_RULES:
            for kw in keywords:
                if kw in message:
                    scores[agent] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            return best, f"关键词匹配: {best}"
        return "portfolio", "默认路由到持仓分析"
