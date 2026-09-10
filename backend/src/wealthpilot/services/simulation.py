"""仓位推演与约束校验 — 把算术从 LLM 手里拿走。

此前 12 个工具全是 `get_*` 取数型，Agent 拿到 JSON 后靠模型自己算权重、
算加仓后的集中度、判断有没有越过风险画像。模型算数不可靠，而这个系统
是要给出仓位建议的 —— 算错就是硬伤。

这里把这些计算做成确定性函数，配套的工具见 agents/tools.py 的 compute_* /
check_* 组。原则：**最终答案里出现的每个数字，都应该是某个工具的返回值。**

全部为纯函数，不触网、不查库，因此可以完整单测。
"""

from __future__ import annotations

import math

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services.analysis import calculate_max_drawdown


def _value(h: PortfolioHolding, nav_data: dict[str, float]) -> float:
    return h.shares * nav_data.get(h.fund_code, h.cost_price)


def portfolio_weights(
    holdings: list[PortfolioHolding], nav_data: dict[str, float]
) -> dict[str, float]:
    """各基金市值占比（0-1）。空仓返回空字典。"""
    values = _values(holdings, nav_data)
    total = sum(values.values())
    if total <= 0:
        return {}
    return {code: v / total for code, v in values.items()}


def _values(holdings, nav_data) -> dict[str, float]:
    values: dict[str, float] = {}
    for h in holdings:
        values[h.fund_code] = values.get(h.fund_code, 0.0) + _value(h, nav_data)
    return values


def concentration_metrics(weights: dict[str, float]) -> dict:
    """集中度指标。

    HHI（赫芬达尔指数）= 各权重平方和，取值 (0, 1]，越大越集中。
    有效持仓数 = 1 / HHI —— 比"持有几只"更能反映真实分散程度：
    持有 5 只但一只占 90%，有效持仓数只有约 1.2。
    """
    if not weights:
        return {"max_weight": 0.0, "hhi": 0.0, "effective_holdings": 0.0, "count": 0}

    hhi = sum(w * w for w in weights.values())
    return {
        "max_weight": round(max(weights.values()), 4),
        "max_weight_code": max(weights, key=lambda k: weights[k]),
        "hhi": round(hhi, 4),
        "effective_holdings": round(1 / hhi, 2) if hhi > 0 else 0.0,
        "count": len(weights),
    }


def _weighted_drawdown(
    weights: dict[str, float], nav_history: dict[str, list[dict]] | None
) -> float | None:
    """按权重加权的历史最大回撤估计（正数，0.18 表示 18%）。

    这是**上界的粗略估计**，不是组合真实回撤 —— 真实回撤要用组合净值序列算，
    各基金的回撤不会同时发生。加权值会高估，作为约束校验的保守侧是可接受的，
    但不能当成预测值对外呈现。
    """
    if not weights or not nav_history:
        return None
    total = 0.0
    for code, w in weights.items():
        series = nav_history.get(code)
        if not series or len(series) < 2 or any(not math.isfinite(r["nav"]) or r["nav"] <= 0 for r in series):
            return None
        info = calculate_max_drawdown(sorted(series, key=lambda r: r["nav_date"], reverse=True))
        # 正常路径返回 max_drawdown_pct；对历史上曾用过的键名保持兼容
        dd = info.get("max_drawdown_pct", info.get("max_drawdown", 0))
        total += w * abs(float(dd)) / 100.0
    return round(total, 4)


def simulate_change(
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None,
    changes: list[dict],
) -> dict:
    """推演一组仓位变动后的组合指标。

    changes 形如 [{"fund_code": "110011", "target_pct": 42}]（目标占比，0-100）
    或 [{"fund_code": "110011", "amount": 5000}]（按金额增减，可为负）。

    返回变动前后的权重、集中度与加权回撤估计，供 Agent 直接引用，
    不需要自己做任何算术。
    """
    before_weights = portfolio_weights(holdings, nav_data)
    before_total = sum(_value(h, nav_data) for h in holdings)

    values = _values(holdings, nav_data)
    applied: list[dict] = []

    targets = [ch for ch in changes if ch.get("target_pct") is not None]
    codes = [str(ch.get("fund_code", "")).strip() for ch in changes]
    error = ""
    if not all(codes) or len(codes) != len(set(codes)):
        error = "基金代码不能为空或重复"
    elif targets and (len(targets) != len(changes) or any(ch.get("amount") is not None for ch in changes)):
        error = "目标占比与增减金额不能混用"
    elif any(not math.isfinite(float(ch.get("target_pct", ch.get("amount", 0)) or 0)) for ch in changes):
        error = "变动必须是有限数值"
    target_total = sum(float(ch["target_pct"]) / 100 for ch in targets)
    if targets and (any(not 0 <= float(ch["target_pct"]) < 100 for ch in targets) or target_total > 1 + 1e-9):
        error = "目标占比需在 0 到 100% 之间且合计不得超过 100%"
    untouched = sum(v for code, v in values.items() if code not in codes)
    if targets and not error:
        if math.isclose(target_total, 1.0) and untouched == 0:
            target_value = before_total
        elif target_total < 1 and untouched > 0:
            target_value = untouched / (1 - target_total)
        else:
            error = "目标占比与未调整持仓不相容，请给出完整配置或使用金额变动"
    if error:
        return {"error": error, "changes": [{"error": error}], "status": "invalid_input"}

    for ch in changes:
        code = str(ch.get("fund_code", "")).strip()
        if not code:
            continue
        current = values.get(code, 0.0)

        if "target_pct" in ch and ch["target_pct"] is not None:
            target_pct = float(ch["target_pct"]) / 100.0
            new_value = target_value * target_pct
            delta = new_value - current
        elif "amount" in ch and ch["amount"] is not None:
            delta = float(ch["amount"])
            new_value = max(current + delta, 0.0)
            delta = new_value - current
        else:
            applied.append({"fund_code": code, "error": "需提供 target_pct 或 amount"})
            continue

        values[code] = max(current + delta, 0.0)
        applied.append({
            "fund_code": code,
            "before_value": round(current, 2),
            "after_value": round(values[code], 2),
            "delta_amount": round(delta, 2),
        })

    after_total = sum(values.values())
    after_weights = (
        {c: v / after_total for c, v in values.items() if v > 0} if after_total > 0 else {}
    )

    return {
        "before": {
            "total_value": round(before_total, 2),
            "weights": {c: round(w, 4) for c, w in before_weights.items()},
            "concentration": concentration_metrics(before_weights),
            "weighted_max_drawdown": _weighted_drawdown(before_weights, nav_history),
        },
        "after": {
            "total_value": round(after_total, 2),
            "weights": {c: round(w, 4) for c, w in after_weights.items()},
            "concentration": concentration_metrics(after_weights),
            "weighted_max_drawdown": _weighted_drawdown(after_weights, nav_history),
        },
        "changes": applied,
        "note": "weighted_max_drawdown 为各基金历史最大回撤的加权和，是保守上界估计，不是组合真实回撤预测。",
    }


def check_constraints(
    profile: InvestorProfile | None,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None,
    changes: list[dict] | None = None,
) -> dict:
    """按风险画像逐条校验（可选：校验变动后的状态）。

    返回 {"passed": bool, "violations": [...], "checked": [...]}。
    没有画像时直接判为不通过 —— 这与产品约定一致：未测评不得给出具体仓位。
    """
    if profile is None:
        return {
            "passed": False,
            "violations": ["用户尚未完成风险测评，不得给出具体仓位比例或止损价位"],
            "checked": [],
        }

    if changes:
        sim = simulate_change(holdings, nav_data, nav_history, changes)
        if "error" in sim:
            return {"passed": False, "status": "invalid_input", "violations": [sim["error"]], "checked": []}
        state = sim["after"]
    else:
        weights = portfolio_weights(holdings, nav_data)
        state = {
            "weights": weights,
            "concentration": concentration_metrics(weights),
            "weighted_max_drawdown": _weighted_drawdown(weights, nav_history),
        }

    violations: list[str] = []
    checked: list[str] = []
    missing: list[str] = []
    if profile.is_stale():
        missing.append("风险画像已过期，请复评")
    if any(nav_data.get(code, 0) <= 0 for code in state["weights"]):
        missing.append("缺少有效的当前净值")

    # 1. 回撤容忍度
    dd = state["weighted_max_drawdown"]
    limit = profile.max_drawdown_tolerance
    checked.append(f"回撤容忍上限 {limit:.0%}")
    if dd is None:
        missing.append("缺少完整历史净值，无法校验回撤")
    elif dd > limit:
        violations.append(
            f"加权最大回撤估计 {dd:.1%} 超过容忍上限 {limit:.0%}"
        )

    # 2. 排除行业
    excluded = profile.excluded_list
    if excluded:
        by_code = {h.fund_code: h for h in holdings}
        for code, w in state["weights"].items():
            holding = by_code.get(code)
            if holding is None or not holding.industry:
                missing.append(f"缺少 {code} 的行业资料，无法校验排除行业")
            if holding and holding.industry and holding.industry in excluded and w > 0:
                violations.append(
                    f"{holding.fund_name}（{code}）属于已排除行业「{holding.industry}」，占比 {w:.1%}"
                )
        checked.append(f"排除行业检查：{'、'.join(excluded)}")

    # 3. 流动性储备
    before_total = sum(_value(h, nav_data) for h in holdings)
    added = state.get("total_value", before_total) - before_total
    cash = profile.available_cash
    if cash is None and (profile.liquidity_reserve > 0 or added > 0):
        missing.append("缺少可用现金余额，无法校验流动性储备")
    elif cash is not None:
        remaining = cash - added
        checked.append(f"变动后现金 {remaining:.2f} 元；需保留 {profile.liquidity_reserve:.2f} 元")
        if remaining < profile.liquidity_reserve:
            violations.append("变动后现金不足或侵占流动性储备")
    if changes and profile.horizon_months <= 0:
        violations.append("投资期限必须大于零")

    return {"passed": not violations and not missing,
            "status": "constraint_violation" if violations else "insufficient_data" if missing else "passed",
            "violations": violations, "missing_data": missing, "checked": checked}


def max_position_within_drawdown(
    fund_code: str,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None,
    profile: InvestorProfile | None,
    step_pct: float = 1.0,
) -> dict:
    """在不突破回撤容忍度的前提下，该基金最多能占多少比例。

    用线性扫描而不是解析解：加权回撤随权重的变化依赖各基金各自的历史回撤，
    没有干净的闭式解，而扫描 1%~95% 只有不到一百次纯计算，成本可忽略。
    """
    if profile is None:
        return {"error": "用户尚未完成风险测评，无法计算约束下的仓位上限"}
    codes = set(portfolio_weights(holdings, nav_data)) | {fund_code}
    if not math.isfinite(step_pct) or step_pct <= 0:
        return {"error": "扫描步长必须为正数"}
    if any(nav_data.get(c, 0) <= 0 or _weighted_drawdown({c: 1.0}, nav_history) is None for c in codes):
        return {"error": "缺少有效净值或历史样本，无法计算仓位上限", "status": "insufficient_data"}

    limit = profile.max_drawdown_tolerance
    best_pct = 0.0
    best_dd = 0.0
    pct = step_pct

    while pct <= 95.0:
        sim = simulate_change(
            holdings, nav_data, nav_history, [{"fund_code": fund_code, "target_pct": pct}]
        )
        if "error" in sim:
            pct += step_pct
            continue
        dd = sim["after"]["weighted_max_drawdown"]
        if dd > limit:
            pct += step_pct
            continue
        best_pct, best_dd = pct, dd
        pct += step_pct

    current = portfolio_weights(holdings, nav_data).get(fund_code, 0.0)
    return {
        "fund_code": fund_code,
        "current_pct": round(current * 100, 2),
        "max_pct_within_tolerance": round(best_pct, 2),
        "drawdown_at_max": best_dd,
        "tolerance": limit,
        "headroom_pct": round(best_pct - current * 100, 2),
        "note": "上限由加权回撤估计推出，该估计偏保守；仅为约束计算结果，不构成操作建议。",
    }
