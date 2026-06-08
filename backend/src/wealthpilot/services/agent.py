"""AI Chat Agent — Claude API + tool_use 工具调用。

Agent 拥有 5 个工具，可以在对话中主动调用获取实时数据：
1. get_fund_info - 查询基金基本信息
2. get_nav_history - 查询净值历史
3. calculate_return - 计算区间收益率
4. compare_funds - 多基金对比
5. search_market_news - 搜索市场新闻
"""

import json
from collections.abc import Generator

from anthropic import Anthropic

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.market_data import (
    fetch_fund_info,
    fetch_fund_nav,
    fetch_market_news,
    get_comprehensive_fund_info,
    get_macro_data_akshare,
)
from wealthpilot.settings import get_settings

TOOLS = [
    {
        "name": "get_fund_info",
        "description": "查询某只基金的基本信息（名称、最新净值、估值、类型等）。当用户问某只基金的情况时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {
                    "type": "string",
                    "description": "基金代码，如 007340、110011",
                }
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "get_nav_history",
        "description": "查询某只基金近 N 天的净值历史数据（日期、净值、日涨跌幅）。用于分析走势和计算收益。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "查询天数，默认30", "default": 30},
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "calculate_return",
        "description": "计算某只基金在指定天数内的累计收益率。用于回答'近1周/1月/3月表现如何'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "计算区间天数（7=近1周, 30=近1月, 90=近3月）"},
            },
            "required": ["fund_code", "days"],
        },
    },
    {
        "name": "compare_funds",
        "description": "对比多只基金的近期表现（净值、涨跌幅）。用于回答'哪只基金更好'类问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要对比的基金代码列表（2-5只）",
                }
            },
            "required": ["fund_codes"],
        },
    },
    {
        "name": "search_market_news",
        "description": "获取最新财经要闻。用于回答市场动态相关问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词（可选）", "default": ""},
            },
        },
    },
]


async def _execute_tool(name: str, input_data: dict) -> str:
    """执行工具调用，返回结果字符串。"""
    if name == "get_fund_info":
        info = await get_comprehensive_fund_info(input_data["fund_code"])
        if info and info.get("name"):
            return json.dumps(info, ensure_ascii=False)
        return f"未找到基金 {input_data['fund_code']} 的信息"

    elif name == "get_nav_history":
        nav_list = await fetch_fund_nav(input_data["fund_code"], input_data.get("days", 30))
        if nav_list:
            summary = f"基金 {input_data['fund_code']} 近 {len(nav_list)} 个交易日净值数据：\n"
            for item in nav_list[:5]:
                summary += f"  {item['nav_date']}: 净值{item['nav']}, 涨跌{item['daily_return']}%\n"
            if len(nav_list) > 5:
                first = nav_list[-1]
                last = nav_list[0]
                period_return = (last["nav"] - first["nav"]) / first["nav"] * 100
                summary += f"  ...（共{len(nav_list)}条）\n"
                summary += f"  区间收益率: {period_return:+.2f}%"
            return summary
        return f"未获取到基金 {input_data['fund_code']} 的净值数据"

    elif name == "calculate_return":
        nav_list = await fetch_fund_nav(input_data["fund_code"], input_data["days"])
        if nav_list and len(nav_list) >= 2:
            first_nav = nav_list[-1]["nav"]
            last_nav = nav_list[0]["nav"]
            ret = (last_nav - first_nav) / first_nav * 100
            return (
                f"基金 {input_data['fund_code']} 近 {input_data['days']} 天收益率: {ret:+.2f}%\n"
                f"起始净值: {first_nav}（{nav_list[-1]['nav_date']}）\n"
                f"最新净值: {last_nav}（{nav_list[0]['nav_date']}）"
            )
        return "数据不足，无法计算"

    elif name == "compare_funds":
        codes = input_data["fund_codes"][:5]
        results = []
        for code in codes:
            info = await fetch_fund_info(code)
            if info:
                results.append(f"  {info['name']}（{code}）: 净值{info['nav']}, 估值涨跌{info.get('estimated_change', 'N/A')}%")
            else:
                results.append(f"  {code}: 信息获取失败")
        return "基金对比结果：\n" + "\n".join(results)

    elif name == "search_market_news":
        news = await fetch_market_news()
        if news:
            return "最新财经要闻：\n" + "\n".join(f"  [{n['tag']}] {n['text']}" for n in news[:5])
        return "暂无最新新闻"

    return f"未知工具: {name}"


def _build_system_prompt(holdings: list[PortfolioHolding], nav_data: dict[str, float]) -> str:
    """构建包含用户持仓上下文的 system prompt。"""
    portfolio_text = ""
    total_value = 0.0
    for h in holdings:
        nav = nav_data.get(h.fund_code, h.cost_price)
        value = h.shares * nav
        ret = (nav - h.cost_price) / h.cost_price * 100
        total_value += value
        portfolio_text += (
            f"- {h.fund_name}（{h.fund_code}）：{h.shares:.2f}份，"
            f"成本{h.cost_price:.4f}，最新{nav:.4f}，"
            f"市值{value:.0f}元，收益率{ret:+.2f}%，类型={h.category}，行业={h.industry or '未标注'}\n"
        )

    return f"""你是 WealthPilot AI，一个专业的智能投顾分析助手。你拥有实时工具可以查询基金数据、计算收益、对比基金。

## 用户当前持仓（总市值约 {total_value:.0f} 元）

{portfolio_text if portfolio_text else "用户暂未添加持仓。请建议用户先在持仓管理中添加基金。"}

## 能力
你可以使用工具实时查询：
- 任意基金的最新净值和估值
- 基金历史净值走势
- 计算任意区间收益率
- 多基金横向对比
- 最新市场新闻

## 角色规则
1. 主动使用工具获取实时数据，不要用过期的训练知识回答数据类问题
2. 基于用户持仓数据进行个性化分析
3. 提供分析框架和多角度思考，不直接给出"买入"或"卖出"建议
4. 每个回答末尾给出 2-3 个追问方向
5. 涉及投资决策时加 "⚠️ 以上仅为分析视角，不构成投资建议"
6. 回答专业但通俗易懂
7. 用中文回答
8. 数据引用时标注来源和日期
"""


def chat_stream(
    message: str,
    history: list[dict[str, str]],
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
) -> Generator[str, None, None]:
    """Streaming chat with Claude + tool_use. Yields SSE-formatted strings."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        yield f"data: {json.dumps({'type': 'error', 'content': '未配置 ANTHROPIC_API_KEY，请在 backend/.env 中设置'})}\n\n"
        return

    client = Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = _build_system_prompt(holdings, nav_data)

    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    try:
        # 第一轮调用（可能触发 tool_use）
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )

        # 处理 tool_use 循环（最多 3 轮工具调用）
        import asyncio
        loop = asyncio.new_event_loop()

        tool_rounds = 0
        while response.stop_reason == "tool_use" and tool_rounds < 3:
            tool_rounds += 1
            # 收集所有 tool_use blocks
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': block.name, 'input': block.input})}\n\n"
                    result = loop.run_until_complete(_execute_tool(block.name, block.input))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # 把工具结果发回 Claude
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4000,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS,
                messages=messages,
            )

        loop.close()

        # 最终文本响应 — streaming 输出
        final_text = ""
        for block in response.content:
            if block.type == "text":
                final_text += block.text

        # 逐段发送（模拟 streaming 体验）
        chunk_size = 20
        for i in range(0, len(final_text), chunk_size):
            chunk = final_text[i:i + chunk_size]
            yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"

        follow_ups = _generate_follow_ups(final_text, message, holdings)
        yield f"data: {json.dumps({'type': 'done', 'content': final_text, 'follow_ups': follow_ups})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'AI 服务异常: {e}'})}\n\n"


def chat_stream_full(
    message: str,
    history: list[dict[str, str]],
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
) -> Generator[str, None, None]:
    """真正的 streaming（无 tool_use 时使用，速度更快）。"""
    settings = get_settings()
    if not settings.anthropic_api_key:
        yield f"data: {json.dumps({'type': 'error', 'content': '未配置 ANTHROPIC_API_KEY'})}\n\n"
        return

    client = Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = _build_system_prompt(holdings, nav_data)

    messages = []
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    try:
        with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=4000,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        ) as stream:
            full_text = ""
            for text in stream.text_stream:
                full_text += text
                yield f"data: {json.dumps({'type': 'delta', 'content': text})}\n\n"

            follow_ups = _generate_follow_ups(full_text, message, holdings)
            yield f"data: {json.dumps({'type': 'done', 'content': full_text, 'follow_ups': follow_ups})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'AI 服务异常: {e}'})}\n\n"


def _generate_follow_ups(
    response: str, question: str, holdings: list[PortfolioHolding]
) -> list[str]:
    """基于回答和持仓生成智能追问建议。"""
    follow_ups = []

    if any(h.category == "equity" for h in holdings):
        if "风险" in response or "回撤" in response:
            follow_ups.append("我的权益仓位是否过重？")
        if "半导体" in response or "科技" in response:
            follow_ups.append("半导体板块还能继续持有吗？")

    if any(h.category == "bond" for h in holdings):
        if "利率" in response:
            follow_ups.append("利率变化对我的债基影响多大？")

    if "医疗" in response or "医药" in response:
        follow_ups.append("医疗基金什么时候适合加仓？")

    if "集中" in response or "仓位" in response:
        follow_ups.append("帮我设计一个调仓方案")

    if len(follow_ups) < 2:
        follow_ups.extend([
            "帮我分析当前持仓的风险收益比",
            "本周市场有什么需要关注的？",
            "推荐关注哪些板块机会？",
        ])

    return follow_ups[:3]
