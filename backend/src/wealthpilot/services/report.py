"""周报生成服务 — 用 LLM 生成结构化周复盘报告。"""

import json
from datetime import date, timedelta

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.ai_client import create_ai_client
from wealthpilot.services.analysis import calculate_attribution_by_fund, calculate_overview
from wealthpilot.settings import get_settings


def generate_weekly_report(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> dict:
    """用 LLM 生成本周复盘报告。"""
    settings = get_settings()

    overview = calculate_overview(holdings, nav_data, nav_history)
    attribution = calculate_attribution_by_fund(holdings, nav_data)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=4)

    try:
        client = create_ai_client(settings)
    except ValueError:
        return _fallback_report(overview, attribution, week_start, week_end)

    portfolio_summary = ""
    for h in holdings:
        nav = nav_data.get(h.fund_code, h.cost_price)
        ret = (nav - h.cost_price) / h.cost_price * 100
        portfolio_summary += f"- {h.fund_name}（{h.fund_code}）：收益率 {ret:+.2f}%\n"

    prompt = f"""基于以下持仓数据，生成一份结构化的周复盘报告（JSON 格式）。

## 本周数据
- 周期：{week_start} 至 {week_end}
- 组合周收益：{overview.get('weekly_return', 0):.0f} 元
- 组合周涨幅：{overview.get('weekly_growth_pct', 0):.2f}%
- 超额收益：{overview.get('excess_return_pct', 0):.2f}%

## 持仓表现
{portfolio_summary}

## 归因 TOP
{json.dumps(attribution[:3], ensure_ascii=False)}

请输出如下 JSON 结构（不要输出其他内容）：
{{
  "summary": "一段话总结本周表现（50字以内）",
  "key_points": [
    {{"title": "要点标题", "desc": "描述"}},
    ...（3条）
  ],
  "next_week_focus": ["关注事项1", "关注事项2", "关注事项3"],
  "risk_alert": "风险提示（如有）或null",
  "ai_insight": "一段 AI 洞察分析（100字以内）"
}}
"""

    try:
        result = client.create(
            model=settings.active_model,
            max_tokens=1000,
            system="",
            messages=[{"role": "user", "content": prompt}],
        )
        text = result.text.strip()
        # 提取 JSON
        if text.startswith("{"):
            report_data = json.loads(text)
        else:
            start = text.index("{")
            end = text.rindex("}") + 1
            report_data = json.loads(text[start:end])

        report_data["week_start"] = str(week_start)
        report_data["week_end"] = str(week_end)
        report_data["overview"] = overview
        return report_data

    except Exception as e:
        report = _fallback_report(overview, attribution, week_start, week_end)
        report["error"] = str(e)
        return report


def _fallback_report(overview: dict, attribution: list, week_start: date, week_end: date) -> dict:
    """无 API key 时的 fallback 报告。"""
    top = attribution[0] if attribution else {"name": "N/A", "value": "N/A"}
    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "summary": f"本周组合收益 {overview.get('weekly_return', 0):.0f} 元，"
                   f"涨幅 {overview.get('weekly_growth_pct', 0):.2f}%。",
        "key_points": [
            {"title": f"收益贡献最大：{top['name']}", "desc": top["value"]},
            {"title": "组合波动", "desc": overview.get("volatility_status", "数据不足")},
            {"title": "Sharpe 比率", "desc": str(overview.get("sharpe_ratio", "N/A"))},
        ],
        "next_week_focus": [
            "关注宏观政策面变化",
            "留意重仓基金的行业动态",
            "检查持仓集中度是否需要调整",
        ],
        "risk_alert": None,
        "ai_insight": "暂无 AI 洞察（需配置 ANTHROPIC_API_KEY）",
        "overview": overview,
    }
