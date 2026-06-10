"""分析引擎 — 高级版：Sharpe/最大回撤/相关性/风格漂移/归因。"""

import math
from collections import defaultdict

from wealthpilot.models.portfolio import PortfolioHolding


def calculate_overview(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> dict:
    """计算持仓总览（含 Sharpe 比率）。"""
    total_cost = 0.0
    total_market_value = 0.0

    for h in holdings:
        cost = h.shares * h.cost_price
        total_cost += cost
        latest_nav = nav_data.get(h.fund_code, h.cost_price)
        total_market_value += h.shares * latest_nav

    total_return = total_market_value - total_cost
    return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0

    # 计算周收益（如有历史数据）
    weekly_return = 0.0
    if nav_history:
        for h in holdings:
            hist = nav_history.get(h.fund_code, [])
            if len(hist) >= 5:
                nav_5d_ago = hist[min(4, len(hist) - 1)]["nav"]
                nav_now = hist[0]["nav"]
                weekly_return += (nav_now - nav_5d_ago) * h.shares

    # Sharpe 比率（简化：用日收益率估算年化）
    sharpe = _calculate_sharpe(holdings, nav_history) if nav_history else None

    weekly_growth_pct = (weekly_return / total_cost * 100) if total_cost > 0 else 0
    # 超额 = 假设基准周涨 0.5%
    excess = weekly_growth_pct - 0.5

    return {
        "total_market_value": round(total_market_value, 2),
        "total_cost": round(total_cost, 2),
        "total_return": round(total_return, 2),
        "return_pct": round(return_pct, 2),
        "weekly_return": round(weekly_return, 2),
        "weekly_growth_pct": round(weekly_growth_pct, 2),
        "excess_return_pct": round(excess, 2),
        "volatility_status": _volatility_label(nav_history, holdings),
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
    }


def _calculate_sharpe(
    holdings: list[PortfolioHolding],
    nav_history: dict[str, list[dict]] | None,
    risk_free_annual: float = 0.02,
) -> float | None:
    """计算组合 Sharpe 比率。"""
    if not nav_history:
        return None

    # 计算组合每日收益率
    daily_returns: list[float] = []
    all_dates = set()
    for hist in nav_history.values():
        for item in hist:
            all_dates.add(item["nav_date"])

    dates = sorted(all_dates)
    if len(dates) < 10:
        return None

    for i in range(1, min(len(dates), 30)):
        day_return = 0.0
        total_weight = 0.0
        for h in holdings:
            hist = nav_history.get(h.fund_code, [])
            hist_by_date = {item["nav_date"]: item for item in hist}
            if dates[i] in hist_by_date and dates[i - 1] in hist_by_date:
                prev = hist_by_date[dates[i - 1]]["nav"]
                curr = hist_by_date[dates[i]]["nav"]
                weight = h.shares * prev
                day_return += weight * (curr - prev) / prev
                total_weight += weight
        if total_weight > 0:
            daily_returns.append(day_return / total_weight)

    if len(daily_returns) < 5:
        return None

    avg_return = sum(daily_returns) / len(daily_returns)
    std_return = math.sqrt(sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns))

    if std_return == 0:
        return 0.0

    daily_rf = risk_free_annual / 252
    sharpe = (avg_return - daily_rf) / std_return * math.sqrt(252)
    return sharpe


def _volatility_label(
    nav_history: dict[str, list[dict]] | None,
    holdings: list[PortfolioHolding],
) -> str:
    """波动率状态标签。"""
    if not nav_history:
        return "数据不足"
    # 简化：看持仓中权益占比
    equity_weight = sum(1 for h in holdings if h.category == "equity") / max(len(holdings), 1)
    if equity_weight > 0.7:
        return "较大波动"
    elif equity_weight > 0.4:
        return "中等波动"
    return "稳健"


def calculate_attribution_by_fund(
    holdings: list[PortfolioHolding], nav_data: dict[str, float]
) -> list[dict]:
    """按基金归因。"""
    results = []
    total_abs_return = 0.0
    fund_returns = []

    for h in holdings:
        latest = nav_data.get(h.fund_code, h.cost_price)
        ret = (latest - h.cost_price) * h.shares
        fund_returns.append((h, ret))
        total_abs_return += abs(ret)

    for h, ret in sorted(fund_returns, key=lambda x: -abs(x[1])):
        pct = abs(ret) / total_abs_return * 100 if total_abs_return > 0 else 0
        results.append({
            "name": h.fund_name,
            "value": f"{'+' if ret >= 0 else ''}{ret:.0f}元",
            "pct": round(pct),
            "positive": ret >= 0,
        })
    return results


def calculate_attribution_by_category(
    holdings: list[PortfolioHolding], nav_data: dict[str, float]
) -> list[dict]:
    """按资产类型归因。"""
    category_names = {
        "equity": "权益类基金",
        "bond": "债券类基金",
        "money": "货币基金",
        "hybrid": "混合基金",
    }
    by_cat: dict[str, float] = {}

    for h in holdings:
        latest = nav_data.get(h.fund_code, h.cost_price)
        ret = (latest - h.cost_price) * h.shares
        by_cat.setdefault(h.category, 0.0)
        by_cat[h.category] += ret

    total = sum(abs(v) for v in by_cat.values()) or 1
    results = []
    for cat, ret in sorted(by_cat.items(), key=lambda x: -abs(x[1])):
        results.append({
            "name": category_names.get(cat, cat),
            "value": f"{'+' if ret >= 0 else ''}{ret:.0f}元",
            "pct": round(abs(ret) / total * 100),
            "positive": ret >= 0,
        })
    return results


def calculate_attribution_by_industry(
    holdings: list[PortfolioHolding], nav_data: dict[str, float]
) -> list[dict]:
    """按行业归因。"""
    by_industry: dict[str, float] = {}

    for h in holdings:
        latest = nav_data.get(h.fund_code, h.cost_price)
        ret = (latest - h.cost_price) * h.shares
        industry = h.industry or "未分类"
        by_industry.setdefault(industry, 0.0)
        by_industry[industry] += ret

    total = sum(abs(v) for v in by_industry.values()) or 1
    results = []
    for ind, ret in sorted(by_industry.items(), key=lambda x: -abs(x[1])):
        results.append({
            "name": ind,
            "value": f"{'+' if ret >= 0 else ''}{ret:.0f}元",
            "pct": round(abs(ret) / total * 100),
            "positive": ret >= 0,
        })
    return results


def calculate_max_drawdown(nav_list: list[dict]) -> dict:
    """计算单只基金最大回撤 + 恢复天数。"""
    if len(nav_list) < 2:
        return {"max_drawdown": 0, "drawdown_days": 0, "recovered": True}

    navs = [item["nav"] for item in reversed(nav_list)]  # 按时间正序
    peak = navs[0]
    max_dd = 0.0
    dd_start = 0
    dd_end = 0
    current_dd_start = 0

    for i, nav in enumerate(navs):
        if nav > peak:
            peak = nav
            current_dd_start = i
        dd = (peak - nav) / peak
        if dd > max_dd:
            max_dd = dd
            dd_start = current_dd_start
            dd_end = i

    # 恢复天数
    recovery_days = 0
    if dd_end < len(navs) - 1:
        peak_at_dd = navs[dd_start]
        for i in range(dd_end + 1, len(navs)):
            if navs[i] >= peak_at_dd:
                recovery_days = i - dd_end
                break
        else:
            recovery_days = len(navs) - dd_end  # 未恢复

    return {
        "max_drawdown_pct": round(max_dd * 100, 2),
        "drawdown_days": dd_end - dd_start,
        "recovery_days": recovery_days,
        "recovered": recovery_days > 0 and (dd_end + recovery_days < len(navs)),
    }


def calculate_drawdown(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """回撤分析（含最大回撤统计）。"""
    results = []
    for h in holdings:
        latest = nav_data.get(h.fund_code, h.cost_price)
        change = (latest - h.cost_price) / h.cost_price * 100

        dd_info = {}
        if nav_history and h.fund_code in nav_history:
            dd_info = calculate_max_drawdown(nav_history[h.fund_code])

        sev = "high" if change < -5 else "medium" if change < -2 else "low"
        results.append({
            "name": h.fund_name,
            "value": f"{change:.1f}%",
            "severity": sev,
            "max_drawdown_pct": dd_info.get("max_drawdown_pct", abs(min(change, 0))),
            "recovery_days": dd_info.get("recovery_days", 0),
            "recovered": dd_info.get("recovered", change >= 0),
        })
    return sorted(results, key=lambda x: float(x["value"].replace("%", "")))


def calculate_health(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """组合健康度 5 维评分（高级版）。"""
    total_value = sum(h.shares * nav_data.get(h.fund_code, h.cost_price) for h in holdings) or 1

    # 1. 收益表现（基于真实收益率）
    returns = []
    for h in holdings:
        latest = nav_data.get(h.fund_code, h.cost_price)
        returns.append((latest - h.cost_price) / h.cost_price * 100)
    avg_return = sum(returns) / len(returns) if returns else 0
    return_score = min(100, max(0, 50 + avg_return * 5))

    # 2. 波动控制（基于日收益率标准差）
    vol_score = 70.0
    if nav_history:
        all_daily_returns = []
        for h in holdings:
            hist = nav_history.get(h.fund_code, [])
            for item in hist:
                if item.get("daily_return"):
                    all_daily_returns.append(item["daily_return"])
        if all_daily_returns:
            vol = math.sqrt(sum(r**2 for r in all_daily_returns) / len(all_daily_returns))
            vol_score = max(0, 100 - vol * 20)

    # 3. 持仓分散度（HHI 指数）
    weights = [h.shares * nav_data.get(h.fund_code, h.cost_price) / total_value for h in holdings]
    hhi = sum(w**2 for w in weights)
    diversification_score = max(0, (1 - hhi) * 100)

    # 4. 风格匹配度（分类多样性 + 行业覆盖）
    categories = set(h.category for h in holdings)
    industries = set(h.industry for h in holdings if h.industry)
    style_score = min(100, len(categories) * 25 + len(industries) * 10)

    # 5. 风险收益比（简化 Sharpe）
    sharpe = _calculate_sharpe(holdings, nav_history)
    if sharpe is not None:
        risk_reward_score = min(100, max(0, 50 + sharpe * 20))
    else:
        risk_reward_score = 50

    def severity(score: float) -> str:
        if score >= 70:
            return "low"
        elif score >= 40:
            return "medium"
        return "high"

    def status(score: float) -> str:
        if score >= 80:
            return "优秀"
        elif score >= 60:
            return "良好"
        elif score >= 40:
            return "偏低"
        return "需改善"

    return [
        {"name": "收益表现", "score": round(return_score), "status": status(return_score), "severity": severity(return_score)},
        {"name": "波动控制", "score": round(vol_score), "status": status(vol_score), "severity": severity(vol_score)},
        {"name": "持仓分散度", "score": round(diversification_score), "status": status(diversification_score), "severity": severity(diversification_score)},
        {"name": "风格匹配度", "score": round(style_score), "status": status(style_score), "severity": severity(style_score)},
        {"name": "风险收益比", "score": round(risk_reward_score), "status": status(risk_reward_score), "severity": severity(risk_reward_score)},
    ]


def calculate_correlation(nav_history: dict[str, list[dict]]) -> dict[str, dict[str, float]]:
    """计算持仓间相关性矩阵。"""
    codes = list(nav_history.keys())
    if len(codes) < 2:
        return {}

    # 提取日收益率序列
    returns_by_code: dict[str, list[float]] = {}
    for code, hist in nav_history.items():
        returns_by_code[code] = [item["daily_return"] for item in hist if item.get("daily_return")]

    matrix: dict[str, dict[str, float]] = {}
    for i, c1 in enumerate(codes):
        matrix[c1] = {}
        for j, c2 in enumerate(codes):
            if i == j:
                matrix[c1][c2] = 1.0
            elif j < i:
                matrix[c1][c2] = matrix[c2][c1]
            else:
                r1 = returns_by_code.get(c1, [])
                r2 = returns_by_code.get(c2, [])
                n = min(len(r1), len(r2))
                if n < 5:
                    matrix[c1][c2] = 0.0
                else:
                    corr = _pearson(r1[:n], r2[:n])
                    matrix[c1][c2] = round(corr, 3)
    return matrix


def _pearson(x: list[float], y: list[float]) -> float:
    """皮尔逊相关系数。"""
    n = len(x)
    if n == 0:
        return 0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0 or sy == 0:
        return 0
    return cov / (sx * sy)


def generate_suggestions(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """基于规则引擎生成投资建议。"""
    suggestions = []
    total_value = sum(h.shares * nav_data.get(h.fund_code, h.cost_price) for h in holdings)

    for h in holdings:
        weight = h.shares * nav_data.get(h.fund_code, h.cost_price) / total_value if total_value else 0
        if weight > 0.4:
            suggestions.append({
                "title": f"{h.fund_name} 仓位偏重（{weight*100:.0f}%）",
                "desc": "单只基金占比超过40%，建议关注集中度风险",
                "priority": "high",
            })

    for h in holdings:
        nav = nav_data.get(h.fund_code, h.cost_price)
        ret = (nav - h.cost_price) / h.cost_price * 100
        if ret < -10:
            suggestions.append({
                "title": f"{h.fund_name} 亏损 {ret:.1f}%",
                "desc": "亏损超过10%，建议评估是否需要止损或调仓",
                "priority": "high",
            })
        elif ret < -5:
            suggestions.append({
                "title": f"{h.fund_name} 小幅亏损 {ret:.1f}%",
                "desc": "可继续观察，关注行业动态",
                "priority": "medium",
            })

    if len(holdings) >= 2 and nav_history:
        matrix = calculate_correlation(nav_history)
        codes = list(matrix.keys())
        name_map = {h.fund_code: h.fund_name for h in holdings}
        for i, c1 in enumerate(codes):
            for c2 in codes[i+1:]:
                corr = matrix.get(c1, {}).get(c2, 0)
                if corr > 0.85:
                    suggestions.append({
                        "title": "高相关性持仓",
                        "desc": f"{name_map.get(c1, c1)} 与 {name_map.get(c2, c2)} 相关系数 {corr:.2f}，分散效果有限",
                        "priority": "medium",
                    })

    cats: dict[str, float] = {}
    for h in holdings:
        w = h.shares * nav_data.get(h.fund_code, h.cost_price)
        cats[h.category] = cats.get(h.category, 0) + w
    equity_pct = cats.get("equity", 0) / total_value * 100 if total_value else 0
    if equity_pct > 80:
        suggestions.append({
            "title": f"权益仓位过高（{equity_pct:.0f}%）",
            "desc": "建议配置部分债券基金降低组合波动",
            "priority": "medium",
        })

    if not suggestions:
        suggestions.append({
            "title": "组合状态良好",
            "desc": "当前持仓未发现明显风险点，建议继续持有观察",
            "priority": "low",
        })

    return suggestions
