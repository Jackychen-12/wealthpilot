"""规则回测 — 把"回调 X% 加仓 Y%"从话术变成可验证的策略。

系统会给出规则型的分批建议，但此前没有任何机制回答"这个规则过去跑出来
什么效果"。没有回测的规则建议，本质上和拍脑袋没有区别。

这里做一个轻量的单标的回测器：给定触发条件与动作，在历史净值序列上逐日
推进，并与两个基线对比 —— 一次性买入、等额定投。基线很重要：一个策略
"赚了 12%" 毫无意义，除非知道同期一次性买入赚了多少。

**局限**（返回值里也会带上）：单标的、不计申赎费与冲击成本、
按日频净值撮合，样本区间取决于能拿到多少历史净值。
"""

from __future__ import annotations

import math


def _ascending(nav_list: list[dict]) -> list[dict]:
    """统一成时间正序。数据源普遍是最新在前。"""
    return sorted(nav_list, key=lambda r: r.get("nav_date", ""))


def _max_drawdown(values: list[float]) -> float:
    """资产曲线的最大回撤（正数百分比）。"""
    peak, worst = values[0] if values else 0.0, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return round(worst * 100, 2)


def _annualized(total_return_pct: float, days: int) -> float:
    if days <= 0:
        return 0.0
    years = days / 252.0
    if years <= 0:
        return 0.0
    growth = 1 + total_return_pct / 100
    if growth <= 0:
        return -100.0
    return round(((growth ** (1 / years)) - 1) * 100, 2)


def backtest_rule(
    nav_list: list[dict],
    triggers: list[dict],
    capital: float = 100000.0,
    max_position_pct: float = 100.0,
    stop_loss_pct: float | None = None,
    fee_pct: float = 0.0,
    execution_lag: int = 0,
) -> dict:
    """在历史净值上回测一条分批建仓规则。

    Args:
        nav_list: 净值序列，元素含 nav_date / nav，顺序不限。
        triggers: 触发档位，如
            [{"drawdown_pct": 5, "add_pct": 20}, {"drawdown_pct": 8, "add_pct": 20}]
            含义：自区间高点回调达到 drawdown_pct 时，投入 add_pct%(占总资金) 建仓。
            每档只触发一次。
        capital: 可投入总资金。
        max_position_pct: 累计投入占总资金的上限。
        stop_loss_pct: 相对持仓成本跌破该比例则清仓（None 表示不设）。

    Returns:
        策略与两个基线的收益、回撤、触发明细。
    """
    series = _ascending(nav_list)
    if len(series) < 2:
        return {"error": "净值数据不足，至少需要 2 个交易日"}

    navs = [float(x["nav"]) for x in series]
    dates = [str(x.get("nav_date", "")) for x in series]
    if (not math.isfinite(capital) or capital <= 0 or
            any(not math.isfinite(v) or v <= 0 for v in navs) or
            len(set(dates)) != len(dates) or not all(dates) or
            not 0 <= fee_pct < 100 or not 0 < max_position_pct <= 100):
        return {"error": "净值、日期、资金或费率无效"}
    if stop_loss_pct is not None and not 0 < stop_loss_pct < 100:
        return {"error": "止损比例必须在 0 到 100% 之间"}
    if any(not 0 <= float(t.get("drawdown_pct", -1)) < 100 or
           not 0 < float(t.get("add_pct", 0)) <= 100 for t in triggers):
        return {"error": "触发阈值或投入比例无效"}
    fee = fee_pct / 100

    tiers = sorted(
        [t for t in triggers if t.get("drawdown_pct") is not None],
        key=lambda t: float(t["drawdown_pct"]),
    )
    fired = [False] * len(tiers)

    cash, shares, invested = capital, 0.0, 0.0
    peak = navs[0]
    events: list[dict] = []
    equity: list[float] = []

    for i, nav in enumerate(navs):
        # execution_lag=1 表示信号在下一观察日净值成交；默认 0 保留历史 API 口径。
        if i < execution_lag:
            equity.append(capital)
            continue
        signal_index = i - execution_lag
        signal_nav = navs[signal_index]
        peak = max(peak, signal_nav)
        drawdown = (peak - signal_nav) / peak * 100
        if stop_loss_pct is not None and shares > 0 and invested > 0:
            if signal_nav <= invested / shares * (1 - stop_loss_pct / 100):
                proceeds = shares * nav * (1 - fee)
                cash += proceeds
                events.append({"date": dates[i], "signal_date": dates[signal_index],
                               "action": "stop_loss", "nav": round(nav, 4), "amount": round(proceeds, 2)})
                shares, invested = 0.0, 0.0
                equity.append(cash)
                continue

        for idx, tier in enumerate(tiers):
            if fired[idx] or drawdown < float(tier["drawdown_pct"]):
                continue
            add_pct = float(tier.get("add_pct", 0))
            budget = min(capital * add_pct / 100, cash,
                         capital * max_position_pct / 100 - invested)
            if budget <= 0:
                fired[idx] = True
                continue
            bought = budget * (1 - fee) / nav
            shares += bought
            cash -= budget
            invested += budget
            fired[idx] = True
            events.append({
                "date": dates[i], "action": "buy", "nav": round(nav, 4),
                "signal_date": dates[signal_index],
                "drawdown_pct": round(drawdown, 2), "amount": round(budget, 2),
            })

        equity.append(cash + shares * nav)

    final = equity[-1]
    strategy_return = (final - capital) / capital * 100

    # ── 基线 1：期初一次性买入 ──
    lump_equity = [capital * (1 - fee) / navs[0] * nav for nav in navs]
    lump_return = (lump_equity[-1] - capital) / capital * 100

    # ── 基线 2：等额定投（每 20 个交易日投一次，共 5 次）──
    dca_points = [i for i in range(0, len(navs), 20)][:5] or [0]
    per = capital / len(dca_points)
    dca_shares, dca_cash = 0.0, capital
    dca_equity = []
    for i, nav in enumerate(navs):
        if i in dca_points:
            dca_shares += per * (1 - fee) / nav
            dca_cash -= per
        dca_equity.append(dca_cash + dca_shares * nav)
    dca_return = (dca_equity[-1] - capital) / capital * 100

    days = len(navs)
    return {
        "period": {"start": dates[0], "end": dates[-1], "trading_days": days},
        "assumptions": {"execution": "next_observation_nav", "fee_pct": fee_pct,
                        "annualization": "252_trading_days", "execution_lag": execution_lag, "cash_interest": 0,
                        "price_basis": "unit_nav_unadjusted"},
        "strategy": {
            "total_return_pct": round(strategy_return, 2),
            "annualized_pct": _annualized(strategy_return, days - 1),
            "max_drawdown_pct": _max_drawdown(equity),
            "trigger_count": len([e for e in events if e["action"] == "buy"]),
            "deployed_pct": round(invested / capital * 100, 2),
            "events": events,
        },
        "baseline_lump_sum": {
            "total_return_pct": round(lump_return, 2),
            "annualized_pct": _annualized(lump_return, days - 1),
            "max_drawdown_pct": _max_drawdown(lump_equity),
        },
        "baseline_dca": {
            "total_return_pct": round(dca_return, 2),
            "annualized_pct": _annualized(dca_return, days - 1),
            "max_drawdown_pct": _max_drawdown(dca_equity),
            "installments": len(dca_points),
        },
        "excess_vs_lump_sum_pct": round(strategy_return - lump_return, 2),
        "excess_vs_dca_pct": round(strategy_return - dca_return, 2),
        "limitations": (
            f"单标的回测，单边费率 {fee_pct}%（零费率时不计申赎费），不计冲击成本；"
            "信号在下一观察日净值成交；单位净值未调整分红拆分，不是账户实际收益；"
            f"样本区间仅 {days} 个交易日（{dates[0]} 至 {dates[-1]}），"
            "未必覆盖完整市场周期，历史表现不代表未来。"
        ),
    }
