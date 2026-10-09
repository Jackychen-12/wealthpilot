"""立场成绩单：当时说看多、看空的那些，后来相对大盘怎么样。

验证点核对的是"我说的那个条件成立没有"；这里看的是更直接的一件事 —— 立场本身对不对。
每次给过立场的个股研究，从那天的收盘价起，看 5 / 20 / 60 个交易日之后它比沪深 300 多涨还是少涨了多少。
看多的要跑赢、看空的要跑输才算对；中性的要求和大盘的差距在 5 个百分点以内。
全部由行情数据计算，不调用模型；还没到日子的那一档写"未到期"，不提前下结论。
"""

from __future__ import annotations

import asyncio
import bisect
import json
from datetime import date, datetime

from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.services.stocks import fetch_stock_kline

HORIZONS = (5, 20, 60)
BENCHMARK = "sh000300"
NEUTRAL_BAND = 5.0
STANCES = ("看多", "中性", "看空")


def _closes(records: list[dict]) -> list[tuple[str, float]]:
    return sorted((r["nav_date"], r["nav"]) for r in records if r.get("nav_date") and isinstance(r.get("nav"), (int, float)))


def settle(stance: str, asked: str, stock: list[tuple[str, float]], bench: list[tuple[str, float]]) -> dict[int, dict]:
    """一条立场在各个期限上的结果。asked 是 YYYY-MM-DD；从当天（休市则下一个交易日）的收盘价算起。"""
    out: dict[int, dict] = {}
    bench_days = [day for day, _ in bench]

    def bench_on(day: str) -> float | None:
        """大盘在这一天的收盘价；这一天 A 股休市（港股、美股的交易日历不一样）就用之前最近的一个交易日。"""
        at = bisect.bisect_right(bench_days, day) - 1
        return bench[at][1] if at >= 0 else None
    start = next((i for i, (day, _) in enumerate(stock) if day >= asked), None)
    for horizon in HORIZONS:
        if start is None or start + horizon >= len(stock):
            out[horizon] = {"settled": False}
            continue
        (day0, p0), (day1, p1) = stock[start], stock[start + horizon]
        b0, b1 = bench_on(day0), bench_on(day1)
        if not p0 or not b0 or not b1:
            out[horizon] = {"settled": False}
            continue
        move, market = (p1 / p0 - 1) * 100, (b1 / b0 - 1) * 100
        excess = move - market
        right = excess > 0 if stance == "看多" else excess < 0 if stance == "看空" else abs(excess) <= NEUTRAL_BAND
        out[horizon] = {"settled": True, "from": day0, "to": day1, "return_pct": round(move, 2), "benchmark_pct": round(market, 2),
                        "excess_pct": round(excess, 2), "right": right}
    return out


def calls(db: Session, user_id: int, limit: int = 200) -> list[dict]:
    """给过立场的个股研究。同一只股票同一天问了几次，只算最后一次。"""
    rows = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant")
                   .order_by(ChatMessage.id.desc()).limit(1500)).all()
    seen: dict[tuple[str, str], dict] = {}
    for row in rows:
        try:
            meta = json.loads(row.metadata_json or "{}")
        except ValueError:
            continue
        stance = ((meta.get("summary") or {}).get("stance") or "").strip()
        stocks = [s for s in meta.get("securities") or [] if s.get("asset_type", "stock") == "stock"]
        if stance not in STANCES or len(stocks) != 1 or meta.get("status") not in ("passed", "partial"):
            continue
        day = row.created_at.date().isoformat()
        seen.setdefault((stocks[0]["code"], day), {"message_id": row.id, "code": stocks[0]["code"], "name": stocks[0].get("name") or stocks[0]["code"],
                                                    "stance": stance, "asked": day})
    return sorted(seen.values(), key=lambda c: c["asked"], reverse=True)[:limit]


def summarize(settled_calls: list[dict]) -> dict:
    by_horizon = {}
    for horizon in HORIZONS:
        done = [c for c in settled_calls if c["results"][horizon]["settled"]]
        directional = [c for c in done if c["stance"] != "中性"]
        item = {"settled": len(done), "pending": len(settled_calls) - len(done),
                "right": sum(1 for c in done if c["results"][horizon]["right"]),
                "hit_rate_pct": round(sum(1 for c in done if c["results"][horizon]["right"]) / len(done) * 100, 1) if done else None}
        for stance in ("看多", "看空"):
            group = [c["results"][horizon]["excess_pct"] for c in directional if c["stance"] == stance]
            item[f"{stance}_count"] = len(group)
            item[f"{stance}_avg_excess_pct"] = round(sum(group) / len(group), 2) if group else None
        by_horizon[horizon] = item
    total = len(settled_calls)
    note = ("还没有给过立场的个股研究。打开个人模式（设置里的「给出立场与操作建议」）之后，研究才会写立场。" if not total
            else "已结算不到 10 条，样本太少，胜率不具统计意义。" if max(v["settled"] for v in by_horizon.values()) < 10 else "")
    return {"total": total, "horizons": by_horizon, "note": note, "benchmark": "沪深 300", "neutral_band_pct": NEUTRAL_BAND}


async def scorecard(db: Session, user_id: int, *, today: date | None = None, kline=fetch_stock_kline) -> dict:
    found = calls(db, user_id)
    if not found:
        return {"calls": [], **summarize([])}
    oldest = min(c["asked"] for c in found)
    span = max(30, int((datetime.combine(today or date.today(), datetime.min.time()) - datetime.fromisoformat(oldest)).days * 0.75) + 15)
    codes = sorted({c["code"] for c in found})
    fetched = await asyncio.gather(kline(BENCHMARK, span), *(kline(code, span) for code in codes), return_exceptions=True)
    bench = _closes(fetched[0]) if isinstance(fetched[0], list) else []
    by_code = {code: _closes(rows) if isinstance(rows, list) else [] for code, rows in zip(codes, fetched[1:], strict=True)}
    for call in found:
        call["results"] = settle(call["stance"], call["asked"], by_code.get(call["code"]) or [], bench)
    return {"calls": found, **summarize(found)}


def text(card: dict) -> str:
    if not card["total"]:
        return card["note"]
    lines = [f"立场回溯（对比{card['benchmark']}，共 {card['total']} 次给过立场）"]
    for horizon, item in card["horizons"].items():
        if not item["settled"]:
            lines.append(f"{horizon} 个交易日后：都还没到期")
            continue
        parts = [f"{horizon} 个交易日后：{item['settled']} 条已结算，方向正确 {item['right']} 条（胜率 {item['hit_rate_pct']:g}%）"]
        for stance in ("看多", "看空"):
            if item[f"{stance}_count"]:
                parts.append(f"{stance}的 {item[f'{stance}_count']} 只平均超额收益 {item[f'{stance}_avg_excess_pct']:+g} 个百分点")
        lines.append("，".join(parts))
    if card["note"]:
        lines.append(card["note"])
    return "\n".join(lines)
