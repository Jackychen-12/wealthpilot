"""Multi-Agent 系统单元测试。"""

import json

from wealthpilot.services.agents.router_agent import RouterAgent, KEYWORD_RULES
from wealthpilot.services.agents.tools import MARKET_TOOLS, PORTFOLIO_TOOLS, RISK_TOOLS


class TestRouterKeywordFallback:
    """测试 Router 关键词回退逻辑。"""

    def test_market_keywords(self):
        agent, _ = RouterAgent._keyword_fallback("帮我查一下基金净值")
        assert agent == "market"

    def test_market_news(self):
        agent, _ = RouterAgent._keyword_fallback("最新市场新闻")
        assert agent == "market"

    def test_portfolio_keywords(self):
        agent, _ = RouterAgent._keyword_fallback("分析我的持仓收益")
        assert agent == "portfolio"

    def test_portfolio_health(self):
        agent, _ = RouterAgent._keyword_fallback("我的组合健康度怎么样")
        assert agent == "portfolio"

    def test_risk_keywords(self):
        agent, _ = RouterAgent._keyword_fallback("风险评估和回撤分析")
        assert agent == "risk"

    def test_risk_correlation(self):
        agent, _ = RouterAgent._keyword_fallback("相关性分析和波动风险")
        assert agent == "risk"

    def test_default_to_portfolio(self):
        agent, reason = RouterAgent._keyword_fallback("你好")
        assert agent == "portfolio"
        assert "默认" in reason

    def test_mixed_keywords_highest_score(self):
        agent, _ = RouterAgent._keyword_fallback("持仓收益归因建议配置")
        assert agent == "portfolio"


class TestToolSchemas:
    """测试工具定义格式正确。"""

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
        all_tools = MARKET_TOOLS + PORTFOLIO_TOOLS + RISK_TOOLS
        names = [t["name"] for t in all_tools]
        assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"

    def test_required_fields_exist_in_properties(self):
        for tool in MARKET_TOOLS + PORTFOLIO_TOOLS + RISK_TOOLS:
            required = tool["input_schema"].get("required", [])
            properties = tool["input_schema"]["properties"]
            for field in required:
                assert field in properties, f"Tool {tool['name']}: required field '{field}' not in properties"


class TestSSEFormat:
    """测试 SSE 事件格式。"""

    def test_sse_format(self):
        from wealthpilot.services.agents.base import BaseAgent
        data = {"type": "delta", "content": "hello"}
        result = BaseAgent._sse(data)
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        parsed = json.loads(result[6:].strip())
        assert parsed == data

    def test_sse_chinese(self):
        from wealthpilot.services.agents.base import BaseAgent
        data = {"type": "delta", "content": "你好世界"}
        result = BaseAgent._sse(data)
        parsed = json.loads(result[6:].strip())
        assert parsed["content"] == "你好世界"
