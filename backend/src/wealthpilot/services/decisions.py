"""买卖理由与按来源对账：钱是怎么决定花出去的，事后看哪一类决定靠谱。

很多买入并不是研究出来的：看到一位博主的帖子、朋友提了一句、群里在传。这没什么可耻的，但值得记下来 ——
每次动手时写一句为什么、消息从哪来；过一阵子按来源对一次账：听博主买的那几笔后来跑赢大盘没有，自己研究的那几笔呢。
对账用的是和立场回溯同一把尺子：买入之后 20、60 个交易日相对沪深 300 的超额收益。全部由行情数据计算，不调用模型。

这里不评价消息来源本身，只把结果摆出来。样本少的时候明说样本少。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

from sqlmodel import Session, select

from wealthpilot.models.decision import Decision
from wealthpilot.services import global_stocks, stance
from wealthpilot.services.stocks import fetch_stock_kline

SOURCE_KINDS = ("自己研究", "AI 研究", "博主 / 大V", "朋友推荐", "新闻 / 公告", "群 / 论坛", "券商研报", "其他")
HORIZONS = (20, 60)
MAX_REASON = 300


def _kind(text: str) -> str:
    """来源写得随意一点也认：大V、博主、雪球某某 → 博主 / 大V。"""
    text = (text or "").strip()
    if not text:
        return "自己研究"
    if text in SOURCE_KINDS:
        return text
    table = (("博主 / 大V", ("大v", "大V", "博主", "up主", "UP主", "雪球", "微博", "公众号", "抖音", "小红书", "b站", "B站")), ("朋友推荐", ("朋友", "同事", "亲戚", "同学", "家人")),
             ("群 / 论坛", ("群", "论坛", "股吧", "贴吧")), ("新闻 / 公告", ("新闻", "公告", "财报", "政策")), ("券商研报", ("研报", "券商", "分析师")),
             ("AI 研究", ("ai", "AI", "模型", "wealthpilot", "WealthPilot")), ("自己研究", ("自己", "研究", "分析")))
    return next((kind for kind, words in table if any(w in text for w in words)), "其他")


USAGE = "这样记：记一笔 宁德时代 储能订单超预期 来自 雪球某某（“来自”后面写消息从哪来，不写就当自己研究的；终端里是 /why 宁德时代 …）"


def parse_note(text: str) -> dict:
    """终端和手机里的一句话记法：<名称或代码> <理由> [来自 <来源>]。理由以“卖出 / 清仓 / 减仓”开头就记成卖出。"""
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        raise ValueError(USAGE)
    reason, _, source = parts[1].partition(" 来自 ")
    if not source and parts[1].startswith("来自 "):
        raise ValueError(USAGE)
    return {"query": parts[0], "reason": reason.strip(), "source_kind": source.strip(), "source_name": source.strip(),
            "action": "sell" if reason.startswith(("卖出", "卖了", "清仓", "减仓")) else "buy"}


def add(db: Session, user_id: int, data: dict) -> Decision:
    code, reason = str(data.get("code") or "").strip(), str(data.get("reason") or "").strip()
    if not code:
        raise ValueError("要说是哪只股票")
    if not reason:
        raise ValueError("写一句当时为什么买（或卖），哪怕只是“看到某某说好”")
    day = str(data.get("day") or date.today().isoformat())[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError("日期写成 2026-10-08 这样") from e
    if day > date.today().isoformat():
        raise ValueError("日期不能在今天之后")
    price = data.get("price")
    kind = _kind(str(data.get("source_kind") or ""))
    who = str(data.get("source_name") or "").strip()[:40]
    if who in SOURCE_KINDS or who in ("朋友", "博主", "大V", "大v", "新闻", "公告", "研报", "自己", "AI", "ai", "群", "论坛"):   # 只写了类别，没写具体是谁
        who = ""
    row = Decision(user_id=user_id, code=code, name=str(data.get("name") or code).strip()[:40], action="sell" if str(data.get("action")) in ("sell", "卖", "卖出") else "buy",
                   day=day, price=float(price) if price not in (None, "") else None, reason=reason[:MAX_REASON],
                   source_kind=kind, source_name=who)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def listing(db: Session, user_id: int, limit: int = 200) -> list[Decision]:
    return list(db.exec(select(Decision).where(Decision.user_id == user_id).order_by(Decision.day.desc(), Decision.id.desc()).limit(limit)).all())


def remove(db: Session, user_id: int, decision_id: int) -> bool:
    row = db.get(Decision, decision_id)
    if row is None or row.user_id != user_id:
        return False
    db.delete(row)
    db.commit()
    return True


def serialize(row: Decision) -> dict:
    return {"id": row.id, "code": row.code, "name": row.name, "action": row.action, "day": row.day, "price": row.price, "reason": row.reason,
            "source_kind": row.source_kind, "source_name": row.source_name}


def _group(rows: list[dict], horizon: int) -> dict:
    done = [r["results"][horizon] for r in rows if r["results"][horizon]["settled"]]
    excess = [x["excess_pct"] for x in done]
    return {"settled": len(done), "beat": sum(1 for x in excess if x > 0), "avg_excess_pct": round(sum(excess) / len(excess), 2) if excess else None}


async def review(db: Session, user_id: int, *, today: date | None = None, kline=fetch_stock_kline) -> dict:
    """按来源对账。只算买入：卖出记下来是为了以后回看，不参与这张表。"""
    rows = [serialize(r) for r in listing(db, user_id)]
    buys = [r for r in rows if r["action"] == "buy"]
    if not buys:
        return {"decisions": rows, "by_source": [], "by_name": [], "note": "还没有记过买入理由。下次动手时记一句：为什么买，消息从哪来。", "benchmark": "沪深 300"}
    oldest = min(r["day"] for r in buys)
    span = max(40, int(((today or date.today()) - date.fromisoformat(oldest)).days * 0.75) + 20)
    codes = sorted({r["code"] for r in buys})[:60]
    fetched = await asyncio.gather(kline(stance.BENCHMARK, span), *(kline(code, span) for code in codes), return_exceptions=True)
    closes = lambda rows_: sorted((x["nav_date"], x["nav"]) for x in rows_ if x.get("nav")) if isinstance(rows_, list) else []  # noqa: E731
    bench, by_code = closes(fetched[0]), {code: closes(got) for code, got in zip(codes, fetched[1:], strict=True)}
    for r in buys:
        settled = stance.settle("看多", r["day"], by_code.get(r["code"]) or [], bench)       # 买入就是看多：之后跑赢大盘才算这笔决定对了
        r["results"] = {h: settled[h] for h in HORIZONS}

    def table(key: str, minimum: int) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for r in buys:
            if r[key]:
                groups.setdefault(r[key], []).append(r)
        out = [{"source": name, "count": len(items), **{f"d{h}": _group(items, h) for h in HORIZONS}} for name, items in groups.items() if len(items) >= minimum]
        return sorted(out, key=lambda g: -g["count"])
    settled_total = sum(1 for r in buys if r["results"][HORIZONS[0]]["settled"])
    note = ("" if settled_total >= 10 else f"已经到期的只有 {settled_total} 笔，样本太少，先看个大概；攒到十笔以上再下结论。") if settled_total else "这些买入都还没满 20 个交易日，到期后这里会出结果。"
    if any(global_stocks.is_global(r["code"]) for r in buys):
        note = (note + " " if note else "") + "港股、美股也是和沪深 300 比的，不是和它们自己的大盘比，只能看个大概。"
    return {"decisions": rows, "by_source": table("source_kind", 1), "by_name": table("source_name", 2), "note": note, "benchmark": "沪深 300"}


def text(report: dict) -> str:
    if not report["by_source"]:
        return report["note"]
    lines = [f"按来源对账（买入之后相对{report['benchmark']}的超额收益）"]
    for g in report["by_source"] + [{**n, "source": f"其中 {n['source']}"} for n in report["by_name"]]:
        parts = [f"{g['source']}：{g['count']} 笔"]
        for h in HORIZONS:
            d = g[f"d{h}"]
            parts.append(f"{h} 日后{d['settled']} 笔到期，{d['beat']} 笔跑赢，平均超额 {d['avg_excess_pct']:+g} 个百分点" if d["settled"] else f"{h} 日后都还没到期")
        lines.append("，".join(parts))
    if report["note"]:
        lines.append(report["note"])
    return "\n".join(lines)
