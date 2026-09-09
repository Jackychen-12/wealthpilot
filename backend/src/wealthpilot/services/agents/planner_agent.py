"""PlannerAgent — 把用户问题拆解成可并行执行的任务图。

替代原来的 RouterAgent。Router 只能三选一，导致 "我半导体仓位重不重、要不要调"
这类需要同时调用持仓 + 风险 + 市场三方面证据的问题必然答不全 —— 那是架构上限，
不是 prompt 能补的。

Planner 产出一张小型 DAG：无依赖的任务并行执行，有依赖的排到下一波。
同时产出 success_criteria，交给 Critic 检查证据是否足够支撑结论。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.agents.prompts import build_planner_prompt
from wealthpilot.settings import get_settings

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

VALID_AGENTS = ("market", "portfolio", "risk")

# 关键词兜底：LLM 不可用时仍能路由，退化为旧 Router 的单任务行为
KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["基金", "净值", "新闻", "行情", "市场", "指数", "板块", "估值"], "market"),
    (["持仓", "收益", "配置", "健康", "归因", "总览", "建议", "调仓"], "portfolio"),
    (["风险", "回撤", "相关性", "预警", "对比", "波动", "亏损", "止损"], "risk"),
]

# 触发仓位/操作类意图的词 —— 这类问题必须带上风险画像约束检查
ACTION_KEYWORDS = ("加仓", "减仓", "买入", "卖出", "调仓", "止损", "仓位", "该不该", "值得")


@dataclass
class Task:
    id: str
    agent: str
    goal: str
    deps: list[str] = field(default_factory=list)


@dataclass
class Plan:
    intent: str
    tasks: list[Task]
    success_criteria: list[str] = field(default_factory=list)
    source: str = "llm"  # llm | fallback

    @property
    def is_single(self) -> bool:
        return len(self.tasks) == 1

    def waves(self) -> list[list[Task]]:
        """按依赖关系分波，同一波内的任务可以并发执行。"""
        remaining = {t.id: t for t in self.tasks}
        done: set[str] = set()
        result: list[list[Task]] = []

        while remaining:
            wave = [t for t in remaining.values() if all(d in done for d in t.deps)]
            if not wave:
                # 依赖成环或指向不存在的任务 —— 剩余任务一次性放行，不阻塞用户
                wave = list(remaining.values())
            result.append(wave)
            for t in wave:
                done.add(t.id)
                remaining.pop(t.id, None)

        return result


class PlannerAgent:
    def __init__(self, client: AIClient, model: str, profile: InvestorProfile | None = None):
        self.client = client
        self.model = model
        self.profile = profile

    def plan(self, message: str) -> Plan:
        max_tasks = get_settings().planner_max_tasks
        try:
            result = self.client.create(
                model=self.model,
                max_tokens=600,
                system=build_planner_prompt(self.profile),
                messages=[{"role": "user", "content": message}],
            )
            parsed = self._parse(result.text, max_tasks)
            if parsed:
                return parsed
        except Exception:
            pass

        return self._keyword_fallback(message)

    @staticmethod
    def _parse(text: str, max_tasks: int) -> Plan | None:
        match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

        raw_tasks = data.get("tasks") or []
        tasks: list[Task] = []
        for i, rt in enumerate(raw_tasks[:max_tasks]):
            agent = rt.get("agent")
            if agent not in VALID_AGENTS:
                continue
            tasks.append(
                Task(
                    id=str(rt.get("id") or f"t{i + 1}"),
                    agent=agent,
                    goal=str(rt.get("goal") or "").strip(),
                    deps=[str(d) for d in (rt.get("deps") or [])],
                )
            )

        if not tasks:
            return None

        known = {t.id for t in tasks}
        for t in tasks:
            t.deps = [d for d in t.deps if d in known and d != t.id]

        return Plan(
            intent=str(data.get("intent") or "general"),
            tasks=tasks,
            success_criteria=[str(c) for c in (data.get("success_criteria") or [])],
            source="llm",
        )

    @staticmethod
    def _keyword_fallback(message: str) -> Plan:
        scores = dict.fromkeys(VALID_AGENTS, 0)
        for keywords, agent in KEYWORD_RULES:
            for kw in keywords:
                if kw in message:
                    scores[agent] += 1

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            best = "portfolio"

        tasks = [Task(id="t1", agent=best, goal=message, deps=[])]

        # 操作类问题在兜底路径下也要补一条风险任务，否则会给出没有约束依据的仓位建议
        if any(kw in message for kw in ACTION_KEYWORDS) and best != "risk":
            tasks.append(Task(id="t2", agent="risk", goal=f"评估该操作的回撤与集中度影响：{message}", deps=[]))

        criteria = ["需覆盖用户问题涉及的核心指标"]
        if len(tasks) > 1:
            criteria.append("需包含操作对组合风险的影响")

        return Plan(
            intent="general",
            tasks=tasks,
            success_criteria=criteria,
            source="fallback",
        )
