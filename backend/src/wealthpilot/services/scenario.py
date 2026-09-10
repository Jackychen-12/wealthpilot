"""情景分析 — 在假设冲击下推演组合损益。

回测回答"这条规则过去表现如何"，情景分析回答"如果某件事发生，我会亏多少"。
两者互补：一个看历史，一个看假设。

冲击可以叠加，按优先级从细到粗匹配：
    个股级（穿透后）→ 行业级 → 资产类别级 → 全市场
同一持仓只应用最细的那一档，不重复叠加。

**这不是预测**：冲击幅度由用户或预设情景给定，输出是"给定这个假设下的
算术结果"。返回值带 assumption 字段说明这一点。
"""

from __future__ import annotations

from wealthpilot.models.portfolio import PortfolioHolding

# 预设情景。幅度取自常见压力测试口径，不代表对未来的判断。
PRESET_SCENARIOS: dict[str, dict] = {
    "market_crash_10": {
        "label": "全市场下跌 10%",
        "market_pct": -10.0,
        "description": "权益类普跌 10%，债券与货币不受影响",
        "category_pct": {"bond": -1.0, "money": 0.0},
    },
    "market_crash_20": {
        "label": "全市场下跌 20%",
        "market_pct": -20.0,
        "description": "系统性下跌，债券小幅承压",
        "category_pct": {"bond": -3.0, "money": 0.0},
    },
    "rate_hike": {
        "label": "利率上行",
        "market_pct": -5.0,
        "description": "利率上行压制估值，债券价格下跌更明显",
        "category_pct": {"bond": -6.0, "money": 0.0},
    },
    "sector_shock_20": {
        "label": "单一行业重挫 20%",
        "market_pct": 0.0,
        "description": "指定行业下跌 20%，其余不变（需配合 industry_pct 指定行业）",
        "category_pct": {},
    },
    "crypto_crash_40": {
        "label": "加密货币下跌 40%",
        "market_pct": 0.0,
        "description": "加密资产大幅回撤，传统资产不受影响",
        "category_pct": {"crypto": -40.0},
    },
}


def _shock_for(
    holding: PortfolioHolding,
    market_pct: float,
    category_pct: dict[str, float],
    industry_pct: dict[str, float],
    asset_pct: dict[str, float],
) -> tuple[float, str]:
    """返回 (冲击百分比, 命中的档位)。从细到粗，只取最细的一档。"""
    if holding.fund_code in asset_pct:
        return asset_pct[holding.fund_code], "asset"
    if holding.industry and holding.industry in industry_pct:
        return industry_pct[holding.industry], "industry"
    asset_type = getattr(holding, "asset_type", "") or ""
    if asset_type in category_pct:
        return category_pct[asset_type], "asset_type"
    if holding.category in category_pct:
        return category_pct[holding.category], "category"
    return market_pct, "market"


def run_scenario(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    *,
    market_pct: float = 0.0,
    category_pct: dict[str, float] | None = None,
    industry_pct: dict[str, float] | None = None,
    asset_pct: dict[str, float] | None = None,
    label: str = "自定义情景",
) -> dict:
    """在给定冲击下推演组合损益。"""
    if not holdings:
        return {"error": "当前没有持仓，无法做情景分析"}

    category_pct = category_pct or {}
    industry_pct = industry_pct or {}
    asset_pct = asset_pct or {}

    total_before = 0.0
    total_after = 0.0
    per_holding = []

    for h in holdings:
        price = nav_data.get(h.fund_code, h.cost_price)
        value = h.shares * price
        shock, level = _shock_for(h, market_pct, category_pct, industry_pct, asset_pct)
        value_after = value * (1 + shock / 100)

        total_before += value
        total_after += value_after
        per_holding.append({
            "fund_code": h.fund_code,
            "fund_name": h.fund_name,
            "category": h.category,
            "industry": h.industry or "",
            "value_before": round(value, 2),
            "value_after": round(value_after, 2),
            "pnl": round(value_after - value, 2),
            "shock_pct": shock,
            "matched_level": level,
        })

    per_holding.sort(key=lambda x: x["pnl"])
    pnl = total_after - total_before

    return {
        "label": label,
        "total_before": round(total_before, 2),
        "total_after": round(total_after, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / total_before * 100, 2) if total_before else 0.0,
        "worst_contributors": per_holding[:5],
        "holdings": per_holding,
        "assumption": (
            "冲击幅度由情景给定，输出是该假设下的算术结果，不是对未来的预测。"
            "同一持仓只应用最细粒度的一档冲击（个股 > 行业 > 资产类别 > 全市场），不叠加。"
        ),
    }


def run_preset(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    scenario_key: str,
    industry_pct: dict[str, float] | None = None,
) -> dict:
    """跑一个预设情景。"""
    preset = PRESET_SCENARIOS.get(scenario_key)
    if not preset:
        return {
            "error": f"未知情景 {scenario_key}",
            "available": sorted(PRESET_SCENARIOS),
        }
    out = run_scenario(
        holdings, nav_data,
        market_pct=preset["market_pct"],
        category_pct=preset["category_pct"],
        industry_pct=industry_pct,
        label=preset["label"],
    )
    if "error" not in out:
        out["scenario_key"] = scenario_key
        out["description"] = preset["description"]
    return out


def run_all_presets(
    holdings: list[PortfolioHolding], nav_data: dict[str, float]
) -> dict:
    """一次跑完所有预设情景，给出损益排序。用于"我的组合最怕什么"。"""
    results = []
    for key in PRESET_SCENARIOS:
        out = run_preset(holdings, nav_data, key)
        if "error" in out:
            continue
        results.append({
            "scenario_key": key,
            "label": out["label"],
            "pnl": out["pnl"],
            "pnl_pct": out["pnl_pct"],
        })
    results.sort(key=lambda x: x["pnl"])
    return {
        "scenarios": results,
        "most_damaging": results[0] if results else None,
        "assumption": "各情景相互独立，不代表同时发生；幅度为预设口径，非预测。",
    }
