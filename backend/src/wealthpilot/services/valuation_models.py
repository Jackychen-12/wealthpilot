"""反向 DCF：现在这个价钱，隐含了公司未来多高的增长。

正着算 DCF 要先猜增长率，猜出来的"内在价值"很容易变成一个看着精确的目标价。反过来算就老实得多：
市值是已知的，问的是"利润要按多少的速度涨十年，折现回来才值这个市值"。得出来的是一个可以和公司过去的增速、
和常识去比的数，不是买卖点。全部由代码计算，模型只负责转述。

口径（都写在结果里）：用归母净利润的近四个季度合计当作股东每年能分到的钱的近似 —— 没有扣资本开支，
重资产公司会被高估；银行、保险这类靠杠杆赚钱的公司不适合用这个模型，结果只作参考。
"""

from __future__ import annotations

YEARS = 10
TERMINAL_GROWTH = 0.025
DISCOUNTS = (0.08, 0.09, 0.10)
SCENARIO_GROWTHS = (0.0, 0.05, 0.10, 0.15, 0.20)


def present_value(profit: float, growth: float, discount: float, years: int = YEARS, terminal: float = TERMINAL_GROWTH) -> float:
    """利润按 growth 涨 years 年，之后按 terminal 永续，用 discount 折回今天。"""
    value, cash = 0.0, profit
    for year in range(1, years + 1):
        cash *= 1 + growth
        value += cash / (1 + discount) ** year
    return value + cash * (1 + terminal) / (discount - terminal) / (1 + discount) ** years


def implied_growth(market_cap: float, profit: float, discount: float, years: int = YEARS, terminal: float = TERMINAL_GROWTH) -> float | None:
    """解出让现值等于市值的那个增速。二分法；落在 -30% 到 +60% 之外就返回 None（模型说明不了这种价格）。"""
    if profit <= 0 or market_cap <= 0 or discount <= terminal:
        return None
    low, high = -0.30, 0.60
    if present_value(profit, low, discount, years, terminal) > market_cap or present_value(profit, high, discount, years, terminal) < market_cap:
        return None
    for _ in range(60):
        mid = (low + high) / 2
        if present_value(profit, mid, discount, years, terminal) < market_cap:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def ttm_profit(rows: list[dict]) -> tuple[float, str] | None:
    """近四个季度的归母净利润。rows 是财务指标，最新在前，利润是年初至今的累计数。"""
    by_date = {r["report_date"]: r["net_profit_yi"] for r in rows if r.get("report_date") and isinstance(r.get("net_profit_yi"), (int, float))}
    if not by_date:
        return None
    latest = max(by_date)
    if latest.endswith("12-31"):
        return by_date[latest], f"{latest[:4]} 年报"
    year = int(latest[:4])
    last_annual, same_period = by_date.get(f"{year - 1}-12-31"), by_date.get(f"{year - 1}{latest[4:]}")
    if last_annual is None or same_period is None:
        return None
    return by_date[latest] + last_annual - same_period, f"截至 {latest} 的近四个季度"


def annual_cagr(rows: list[dict], years: int = 3) -> float | None:
    # A 股的年报都截止在 12-31；港美股的财年各不相同，由数据里的 annual 标记说了算
    annual = sorted(((r["report_date"], r["net_profit_yi"]) for r in rows
                     if (r.get("annual") or str(r.get("report_date", "")).endswith("12-31")) and isinstance(r.get("net_profit_yi"), (int, float))), reverse=True)
    if len(annual) <= years or annual[years][1] <= 0 or annual[0][1] <= 0:
        return None
    return (annual[0][1] / annual[years][1]) ** (1 / years) - 1


def reverse_dcf(market_cap_yi: float, rows: list[dict], *, name: str = "", industry: str = "", pe_ttm: float | None = None, currency: str = "") -> dict:
    """market_cap_yi 总市值（亿）；rows 是财务指标。算不了就返回带 reason 的结果，不硬算。

    给了 pe_ttm 就用"市值 ÷ 市盈率"当近四个季度的利润：港美股的财年不统一、财报和股价的币种还可能不同，
    行情里的市盈率已经把这两件事对齐了，比自己拿财报去拼更不容易错。
    """
    base = {"name": name, "market_cap_yi": round(market_cap_yi, 1) if market_cap_yi else None, "currency": currency or "人民币",
            "assumptions": {"years": YEARS, "terminal_growth_pct": TERMINAL_GROWTH * 100, "profit_basis": "归母净利润（未扣资本开支）"}}
    if pe_ttm is not None:
        profit = (market_cap_yi / pe_ttm, "按滚动市盈率倒推的近四个季度") if pe_ttm and pe_ttm > 0 and market_cap_yi else (-1.0, "") if pe_ttm is not None and pe_ttm <= 0 else None
    else:
        profit = ttm_profit(rows)
    if not market_cap_yi or market_cap_yi <= 0:
        return {**base, "ok": False, "reason": "没有取到总市值"}
    if profit is None:
        return {**base, "ok": False, "reason": "财务数据不够拼出近四个季度的利润"}
    amount, basis = profit
    if amount <= 0:
        return {**base, "ok": False, "profit_ttm_yi": round(amount, 2), "reason": "近四个季度是亏损的，这个模型建立在利润为正的前提上，算不了"}
    implied = []
    for discount in DISCOUNTS:
        g = implied_growth(market_cap_yi, amount, discount)
        implied.append({"discount_pct": round(discount * 100, 1), "growth_pct": round(g * 100, 1) if g is not None else None})
    middle = DISCOUNTS[len(DISCOUNTS) // 2]
    scenarios = [{"growth_pct": round(g * 100), "value_vs_market_cap": round(present_value(amount, g, middle) / market_cap_yi, 2)} for g in SCENARIO_GROWTHS]
    past = annual_cagr(rows)
    notes = ["这是“现价隐含了什么”，不是目标价，也不是买卖建议。", "折现率越高，同样的市值需要越高的增长来支撑。"]
    if any(k in industry for k in ("银行", "保险", "证券", "多元金融")):
        notes.append("金融类公司靠杠杆赚钱，利润不等于股东能拿走的现金，这个结果只作参考。")
    mid = implied[len(implied) // 2]["growth_pct"]
    if mid is None:
        notes.append("按这套假设，利润在 -30% 到 +60% 的增速范围内都解释不了现在的市值。")
    elif past is not None:
        gap = mid - past * 100
        notes.append(f"过去三年利润的年化增速是 {past * 100:.1f}%；现价隐含的是 {mid:g}%，" + ("比过去更快，市场在为加速付钱。" if gap > 3 else "比过去慢，市场在为放缓定价。" if gap < -3 else "和过去差不多。"))
    return {**base, "ok": True, "profit_ttm_yi": round(amount, 2), "profit_period": basis, "pe_ttm": round(market_cap_yi / amount, 1),
            "implied_growth": implied, "past_profit_cagr_3y_pct": round(past * 100, 1) if past is not None else None,
            "scenarios": {"discount_pct": round(middle * 100, 1), "rows": scenarios}, "notes": notes}
