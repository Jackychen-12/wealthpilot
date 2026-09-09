"""Multi-Agent 系统单元测试（Planner / Synthesizer / 工具定义）。"""

import json

from wealthpilot.services.agents.planner_agent import Plan, PlannerAgent, Task
from wealthpilot.services.agents.synthesizer_agent import check_numeric_grounding
from wealthpilot.services.agents.base import AgentResult
from wealthpilot.services.agents.tools import MARKET_TOOLS, PORTFOLIO_TOOLS, RISK_TOOLS


class TestPlannerKeywordFallback:
    """LLM 不可用时的兜底路由，行为需与旧 Router 保持一致。"""

    def test_market_keywords(self):
        plan = PlannerAgent._keyword_fallback("帮我查一下基金净值")
        assert plan.tasks[0].agent == "market"
        assert plan.source == "fallback"

    def test_market_news(self):
        assert PlannerAgent._keyword_fallback("最新市场新闻").tasks[0].agent == "market"

    def test_portfolio_keywords(self):
        assert PlannerAgent._keyword_fallback("分析我的持仓收益").tasks[0].agent == "portfolio"

    def test_risk_keywords(self):
        assert PlannerAgent._keyword_fallback("风险评估和回撤分析").tasks[0].agent == "risk"

    def test_default_to_portfolio(self):
        assert PlannerAgent._keyword_fallback("你好").tasks[0].agent == "portfolio"

    def test_action_question_adds_risk_task(self):
        """操作类问题必须补一条 risk 任务，否则建议没有约束依据。"""
        plan = PlannerAgent._keyword_fallback("我的半导体基金要不要加仓")
        agents = [t.agent for t in plan.tasks]
        assert "risk" in agents
        assert len(plan.tasks) == 2

    def test_pure_query_stays_single_task(self):
        plan = PlannerAgent._keyword_fallback("查一下基金净值")
        assert plan.is_single


class TestPlanParsing:
    def test_parse_valid_plan(self):
        raw = json.dumps({
            "intent": "position_sizing",
            "tasks": [
                {"id": "t1", "agent": "portfolio", "goal": "当前暴露", "deps": []},
                {"id": "t2", "agent": "risk", "goal": "回撤影响", "deps": ["t1"]},
            ],
            "success_criteria": ["需要当前仓位"],
        })
        plan = PlannerAgent._parse(raw, max_tasks=4)
        assert plan is not None
        assert len(plan.tasks) == 2
        assert plan.tasks[1].deps == ["t1"]

    def test_drops_unknown_agent(self):
        raw = json.dumps({"tasks": [
            {"id": "t1", "agent": "astrology", "goal": "看星象"},
            {"id": "t2", "agent": "market", "goal": "查净值"},
        ]})
        plan = PlannerAgent._parse(raw, max_tasks=4)
        assert [t.agent for t in plan.tasks] == ["market"]

    def test_drops_dangling_deps(self):
        raw = json.dumps({"tasks": [
            {"id": "t1", "agent": "market", "goal": "a", "deps": ["nonexistent"]},
        ]})
        plan = PlannerAgent._parse(raw, max_tasks=4)
        assert plan.tasks[0].deps == []

    def test_respects_max_tasks(self):
        raw = json.dumps({"tasks": [
            {"id": f"t{i}", "agent": "market", "goal": str(i)} for i in range(10)
        ]})
        plan = PlannerAgent._parse(raw, max_tasks=3)
        assert len(plan.tasks) == 3

    def test_returns_none_on_garbage(self):
        assert PlannerAgent._parse("不是 JSON", max_tasks=4) is None


class TestPlanWaves:
    def test_independent_tasks_in_one_wave(self):
        plan = Plan("x", [
            Task("t1", "market", "a"),
            Task("t2", "risk", "b"),
        ])
        waves = plan.waves()
        assert len(waves) == 1
        assert len(waves[0]) == 2

    def test_dependency_creates_second_wave(self):
        plan = Plan("x", [
            Task("t1", "portfolio", "a"),
            Task("t2", "risk", "b", deps=["t1"]),
        ])
        waves = plan.waves()
        assert [t.id for t in waves[0]] == ["t1"]
        assert [t.id for t in waves[1]] == ["t2"]

    def test_cycle_does_not_hang(self):
        """依赖成环时必须放行而不是死循环 —— 用户等不起。"""
        plan = Plan("x", [
            Task("t1", "market", "a", deps=["t2"]),
            Task("t2", "risk", "b", deps=["t1"]),
        ])
        waves = plan.waves()
        assert sum(len(w) for w in waves) == 2


class TestNumericGrounding:
    """数值溯源：答案里的数字必须来自工具返回。"""

    @staticmethod
    def _result(output: str) -> AgentResult:
        return AgentResult("risk", "g", "", [{"tool": "t", "input": {}, "output": output}])

    def test_all_grounded(self):
        res = [self._result("最大回撤 -18.62%，恢复 47 天")]
        report = check_numeric_grounding("回撤达到 18.62%，用了 47 天修复。", res)
        assert report["ungrounded"] == []
        assert report["rate"] == 1.0

    def test_detects_invented_number(self):
        res = [self._result("最新净值 1.5983")]
        report = check_numeric_grounding("净值 1.5983，预计将涨到 1.8500。", res)
        assert "1.8500" in report["ungrounded"]
        assert report["rate"] < 1.0

    def test_sign_normalized(self):
        """工具返回 -18.62（回撤），正文写 18.62% —— 同一个数，不能算编造。"""
        res = [self._result("最大回撤 -18.62%")]
        assert check_numeric_grounding("回撤达到 18.62%", res)["ungrounded"] == []

    def test_trailing_zero_normalized(self):
        res = [self._result("净值 1.50")]
        assert check_numeric_grounding("净值 1.5", res)["ungrounded"] == []

    def test_ignores_list_indices_and_years(self):
        res = [self._result("无数据")]
        report = check_numeric_grounding("1. 第一点\n2. 第二点\n2026 年以来", res)
        assert report["total"] == 0
        assert report["rate"] == 1.0

    def test_empty_answer_is_grounded(self):
        assert check_numeric_grounding("", [])["rate"] == 1.0


class TestToolSchemas:
    def _validate_tool(self, tool: dict):
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema

    def test_market_tools(self):
        assert len(MARKET_TOOLS) == 3
        for t in MARKET_TOOLS:
            self._validate_tool(t)

    def test_portfolio_tools(self):
        assert len(PORTFOLIO_TOOLS) == 4
        for t in PORTFOLIO_TOOLS:
            self._validate_tool(t)

    def test_risk_tools(self):
        assert len(RISK_TOOLS) == 5
        for t in RISK_TOOLS:
            self._validate_tool(t)

    def test_no_duplicate_tool_names(self):
        names = [t["name"] for t in MARKET_TOOLS + PORTFOLIO_TOOLS + RISK_TOOLS]
        assert len(names) == len(set(names))
