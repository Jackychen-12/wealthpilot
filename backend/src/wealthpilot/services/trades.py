"""交易记录体检：从你自己的成交记录里，找出反复出现的毛病。

研究写得再好，钱是在买卖的那一下亏掉的。这里不评价你选的股票，只看行为：
是不是总在大涨之后才买（追高）、是不是买卖得太勤、是不是越跌越买、是不是赚一点就跑而亏的一直拿着。
全部由成交记录和行情数据计算，不调用模型。成交记录只在这次计算里用，不存进数据库。

口径：按先进先出把卖出和之前的买入配成一笔一笔的"来回"；盈亏不含手续费和分红；
追高看的是买入那天之前的涨幅，用的是前复权日线。
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
from datetime import date, datetime
from statistics import mean, median

from wealthpilot.services.stocks import fetch_stock_kline

_HEADERS = {
    "date": ("成交日期", "日期", "交易日期", "发生日期", "date", "委托日期"),
    "code": ("证券代码", "代码", "股票代码", "code"),
    "name": ("证券名称", "名称", "股票名称", "name"),
    "side": ("操作", "买卖标志", "买卖方向", "委托方向", "方向", "交易类型", "业务名称", "side", "摘要"),
    "price": ("成交均价", "成交价格", "成交价", "价格", "price"),
    "shares": ("成交数量", "数量", "成交股数", "shares", "发生数量"),
}
CHASE_PCT = 15.0        # 买入前 5 个交易日涨了这么多，算追高
SHORT_HOLD_DAYS = 5
MAX_ROWS = 5000


def _date(text: str) -> str | None:
    digits = re.sub(r"\D", "", str(text or ""))[:8]
    try:
        return datetime.strptime(digits, "%Y%m%d").date().isoformat() if len(digits) == 8 else None
    except ValueError:
        return None


def _number(text) -> float | None:
    try:
        return abs(float(str(text).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def _side(text: str) -> str:
    text = str(text or "")
    if any(w in text for w in ("卖", "sell", "Sell", "SELL")) or text.strip().upper() == "S":
        return "sell"
    if any(w in text for w in ("买", "buy", "Buy", "BUY")) or text.strip().upper() == "B":
        return "buy"
    return ""


def parse(text: str) -> dict:
    """认出成交记录。支持券商导出的表（带表头，逗号或制表符分隔），也支持手写的"日期 代码 买/卖 价格 数量"。"""
    text = (text or "").lstrip("﻿").strip()
    rows, problems = [], []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {"trades": [], "problems": ["没有内容"]}
    delimiter = "\t" if "\t" in lines[0] else "," if "," in lines[0] else None
    header = [h.strip().strip('"') for h in (lines[0].split(delimiter) if delimiter else lines[0].split())]
    columns = {key: next((i for i, h in enumerate(header) if h in names), None) for key, names in _HEADERS.items()}
    if delimiter and all(columns[k] is not None for k in ("date", "code", "side", "price", "shares")):
        for n, cells in enumerate(csv.reader(io.StringIO("\n".join(lines[1:MAX_ROWS + 1])), delimiter=delimiter), 2):
            def cell(key, cells=cells):
                i = columns[key]
                return cells[i].strip() if i is not None and i < len(cells) else ""
            day, side, price, shares = _date(cell("date")), _side(cell("side")), _number(cell("price")), _number(cell("shares"))
            code = re.sub(r"\D", "", cell("code"))[-6:]
            if not side:
                continue                      # 分红、申购、利息这些不是买卖，跳过不算毛病
            if not (day and len(code) == 6 and price and shares):
                problems.append(f"第 {n} 行没认出来：{','.join(cells)[:60]}")
                continue
            rows.append({"date": day, "code": code, "name": cell("name") or code, "side": side, "price": price, "shares": shares})
    else:
        for n, line in enumerate(lines[:MAX_ROWS], 1):
            parts = re.split(r"[\s,，;；]+", line.strip())
            day = next((d for d in map(_date, parts) if d), None)
            code = next((p for p in parts if re.fullmatch(r"\d{6}", p)), None)
            side = next((s for s in map(_side, parts) if s), "")
            numbers = [v for p in parts if (v := _number(p)) is not None and not re.fullmatch(r"\d{6}|\d{8}", p) and not _date(p)]
            if not (day and code and side and len(numbers) >= 2):
                if n == 1 and not day:
                    continue                  # 多半是表头
                problems.append(f"第 {n} 行没认出来：{line[:60]}")
                continue
            rows.append({"date": day, "code": code, "name": code, "side": side, "price": numbers[0], "shares": numbers[1]})
    return {"trades": sorted(rows, key=lambda r: (r["date"], r["side"] == "sell")), "problems": problems[:20]}


def round_trips(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """先进先出配对。返回（已经了结的来回, 加仓记录）。加仓记录里带着加仓时持仓成本和这次的买价。"""
    lots: dict[str, list[dict]] = {}
    closed, adds = [], []
    for t in trades:
        book = lots.setdefault(t["code"], [])
        if t["side"] == "buy":
            held = sum(lot["shares"] for lot in book)
            if held > 0:
                cost = sum(lot["shares"] * lot["price"] for lot in book) / held
                adds.append({"code": t["code"], "name": t["name"], "date": t["date"], "price": t["price"], "cost_before": round(cost, 3),
                             "below_cost_pct": round((t["price"] / cost - 1) * 100, 2)})
            book.append({"date": t["date"], "price": t["price"], "shares": t["shares"]})
            continue
        left = t["shares"]
        while left > 1e-9 and book:
            lot = book[0]
            used = min(left, lot["shares"])
            days = (date.fromisoformat(t["date"]) - date.fromisoformat(lot["date"])).days
            closed.append({"code": t["code"], "name": t["name"], "bought": lot["date"], "sold": t["date"], "days": days, "shares": used,
                           "buy_price": lot["price"], "sell_price": t["price"], "return_pct": round((t["price"] / lot["price"] - 1) * 100, 2),
                           "pnl": round((t["price"] - lot["price"]) * used, 2)})
            lot["shares"] -= used
            left -= used
            if lot["shares"] <= 1e-9:
                book.pop(0)
    return closed, adds


def _run_up(closes: list[tuple[str, float]], day: str, window: int) -> float | None:
    """买入那天之前 window 个交易日的涨幅（不含买入当天的涨跌）。"""
    index = next((i for i, (d, _) in enumerate(closes) if d >= day), None)
    if index is None or index - 1 - window < 0:
        return None
    before, base = closes[index - 1][1], closes[index - 1 - window][1]
    return (before / base - 1) * 100 if base else None


def _after(closes: list[tuple[str, float]], day: str, window: int) -> float | None:
    index = next((i for i, (d, _) in enumerate(closes) if d >= day), None)
    if index is None or index + window >= len(closes) or not closes[index][1]:
        return None
    return (closes[index + window][1] / closes[index][1] - 1) * 100


async def check(text: str, *, kline=fetch_stock_kline, today: date | None = None) -> dict:
    parsed = parse(text)
    trades = parsed["trades"]
    if len(trades) < 4:
        return {"ok": False, "reason": "认出来的成交不到 4 笔，看不出规律。" + ("没认出来的行见下面。" if parsed["problems"] else ""), "problems": parsed["problems"], "trades": len(trades)}
    closed, adds = round_trips(trades)
    buys, sells = [t for t in trades if t["side"] == "buy"], [t for t in trades if t["side"] == "sell"]
    first, last = trades[0]["date"], trades[-1]["date"]
    months = max(1.0, (date.fromisoformat(last) - date.fromisoformat(first)).days / 30.4)
    span = int(((today or date.today()) - date.fromisoformat(first)).days * 0.75) + 40
    codes = sorted({t["code"] for t in trades})[:60]
    fetched = await asyncio.gather(*(kline(code, min(span, 1200)) for code in codes), return_exceptions=True)
    closes = {code: sorted((r["nav_date"], r["nav"]) for r in rows if r.get("nav")) if isinstance(rows, list) else [] for code, rows in zip(codes, fetched, strict=True)}

    findings: list[dict] = []
    # 追高
    run_ups = [(t, v) for t in buys if (v := _run_up(closes.get(t["code"]) or [], t["date"], 5)) is not None]
    chased = [(t, v) for t, v in run_ups if v >= CHASE_PCT]
    if run_ups:
        share = len(chased) / len(run_ups) * 100
        findings.append({"key": "chasing", "label": "追高", "flag": share >= 30,
                         "text": f"{len(run_ups)} 次买入里有 {len(chased)} 次（{share:.0f}%）是在此前 5 个交易日已经涨了 {CHASE_PCT:g}% 以上之后买的；"
                                 f"所有买入前 5 日涨幅的中位数是 {median(v for _, v in run_ups):+.1f}%。",
                         "examples": [f"{t['date']} {t['name']} 买入前 5 日 {v:+.1f}%" for t, v in sorted(chased, key=lambda x: -x[1])[:3]]})
    # 过度交易
    if closed:
        holds = [c["days"] for c in closed]
        short = sum(1 for d in holds if d <= SHORT_HOLD_DAYS)
        per_month = len(trades) / months
        findings.append({"key": "overtrading", "label": "交易频率", "flag": per_month >= 20 or short / len(holds) >= 0.5,
                         "text": f"{first} 到 {last} 一共 {len(trades)} 笔成交，平均每月 {per_month:.1f} 笔；了结的 {len(closed)} 笔里持有天数的中位数是 {median(holds):g} 天，"
                                 f"{short} 笔（{short / len(holds) * 100:.0f}%）持有不到 {SHORT_HOLD_DAYS} 天。", "examples": []})
    # 亏损加仓
    if adds:
        down = [a for a in adds if a["below_cost_pct"] <= -5]
        findings.append({"key": "averaging_down", "label": "越跌越买", "flag": len(down) >= 3 and len(down) / len(adds) >= 0.4,
                         "text": f"{len(adds)} 次加仓里有 {len(down)} 次是在比持仓成本低 5% 以上的位置补的。",
                         "examples": [f"{a['date']} {a['name']} 买在成本下方 {abs(a['below_cost_pct']):.1f}%" for a in sorted(down, key=lambda a: a["below_cost_pct"])[:3]]})
    # 处置效应、盈亏比
    wins, losses = [c for c in closed if c["pnl"] > 0], [c for c in closed if c["pnl"] < 0]
    if wins and losses:
        win_days, loss_days = median(c["days"] for c in wins), median(c["days"] for c in losses)
        avg_win, avg_loss = mean(c["return_pct"] for c in wins), mean(c["return_pct"] for c in losses)
        findings.append({"key": "disposition", "label": "赚的跑得快、亏的拿得久", "flag": loss_days >= win_days * 1.5 and loss_days - win_days >= 3,
                         "text": f"赚钱的 {len(wins)} 笔持有天数的中位数是 {win_days:g} 天，亏钱的 {len(losses)} 笔是 {loss_days:g} 天。", "examples": []})
        findings.append({"key": "payoff", "label": "胜率和盈亏比", "flag": abs(avg_loss) > avg_win and len(wins) / len(closed) < 0.6,
                         "text": f"了结的 {len(closed)} 笔里 {len(wins)} 笔赚钱（胜率 {len(wins) / len(closed) * 100:.0f}%）；赚的平均 {avg_win:+.1f}%，亏的平均 {avg_loss:+.1f}%，"
                                 f"盈亏比 {avg_win / abs(avg_loss):.2f}。合计盈亏 {sum(c['pnl'] for c in closed):+,.0f} 元（不含手续费）。", "examples": []})
    # 卖出之后
    after = [(t, v) for t in sells if (v := _after(closes.get(t["code"]) or [], t["date"], 20)) is not None]
    if len(after) >= 3:
        rose = [(t, v) for t, v in after if v >= 10]
        findings.append({"key": "sold_early", "label": "卖出之后", "flag": len(rose) / len(after) >= 0.4,
                         "text": f"{len(after)} 次卖出之后的 20 个交易日，股价中位数变动 {median(v for _, v in after):+.1f}%；其中 {len(rose)} 次卖出后又涨了 10% 以上。",
                         "examples": [f"{t['date']} 卖出 {t['name']}，之后 20 日 {v:+.1f}%" for t, v in sorted(rose, key=lambda x: -x[1])[:3]]})
    # 亏在哪
    by_stock: dict[str, float] = {}
    for c in closed:
        by_stock[c["name"]] = by_stock.get(c["name"], 0) + c["pnl"]
    worst = sorted(by_stock.items(), key=lambda kv: kv[1])[:3]
    flagged = [f for f in findings if f["flag"]]
    return {"ok": True, "period": {"from": first, "to": last}, "trades": len(trades), "stocks": len(codes), "closed": len(closed),
            "findings": findings, "flagged": [f["label"] for f in flagged],
            "worst_stocks": [{"name": n, "pnl": round(v, 2)} for n, v in worst if v < 0], "problems": parsed["problems"],
            "missing_prices": [c for c in codes if not closes.get(c)],
            "note": "只看行为，不评价你选的股票。盈亏按先进先出配对，不含手续费和分红；追高和卖出之后用的是前复权日线。"}


def text(report: dict) -> str:
    if not report.get("ok"):
        return report.get("reason", "没有看出什么。") + "".join(f"\n  {p}" for p in report.get("problems") or [])
    lines = [f"{report['period']['from']} 到 {report['period']['to']}：{report['trades']} 笔成交，{report['stocks']} 只股票，了结 {report['closed']} 笔"]
    lines.append("值得留意：" + "、".join(report["flagged"]) if report["flagged"] else "没有发现明显反复出现的毛病。")
    for f in report["findings"]:
        lines.append(f"{'!' if f['flag'] else '·'} {f['label']}：{f['text']}")
        lines += [f"    {e}" for e in f["examples"]]
    if report["worst_stocks"]:
        lines.append("亏得最多的：" + "，".join(f"{w['name']} {w['pnl']:+,.0f} 元" for w in report["worst_stocks"]))
    if report["missing_prices"]:
        lines.append(f"这些代码没取到行情，追高和卖出之后两项没算上它们：{'、'.join(report['missing_prices'][:8])}")
    lines.append(report["note"])
    return "\n".join(lines)
