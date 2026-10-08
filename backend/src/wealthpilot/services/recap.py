"""每日大盘复盘：今天市场发生了什么。全部是取数和计数，不调用模型。

每日简报只盯自己的持仓和自选；这里讲的是市场本身：指数和涨跌家数、涨停跌停与炸板、连板梯队、
涨停集中在哪些题材（以及同花顺给的涨停原因）、概念板块强弱、龙虎榜上机构和活跃营业部在买卖什么。

"情绪"那一栏是按几个公开数字套一把固定的尺子得出的粗略刻度，尺子写在 gauge() 里，数字也一起给出来 ——
它不是预测，只是把"今天热不热"说成一句话。
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import date

import httpx

from wealthpilot.services import cache
from wealthpilot.services.stocks import datacenter

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_EM_POOL = "https://push2ex.eastmoney.com"
_THS_POOL = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
_SINA_BOARDS = "https://vip.stock.finance.sina.com.cn/q/view/newFLJK.php"
_SINA_NODE = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"

# 龙虎榜上经常出现的几类席位。前三类是交易所披露的口径，是事实；
# "散户集中的营业部"是市场上的通行说法（东方财富拉萨的几家营业部开户以个人为主），只作提示。
SEAT_KINDS = (("机构专用", "机构"), ("机构投资者", "机构"), ("沪股通专用", "北向"), ("深股通专用", "北向"), ("自然人", "个人"), ("中小投资者", "个人"), ("拉萨", "散户集中的营业部"))


def _ymd(day: date | str | None) -> str:
    return (day.isoformat() if isinstance(day, date) else str(day or date.today())).replace("-", "")[:8]


async def _em_pool(client: httpx.AsyncClient, name: str, day: str, sort: str) -> dict:
    try:
        resp = await client.get(f"{_EM_POOL}/{name}", params={"ut": "7eea3edcaed734bea9cbfc24409ed989", "dpt": "wz.ztzt", "Pageindex": 0,
                                                             "pagesize": 400, "sort": sort, "date": day},
                                headers={**_UA, "Referer": "https://quote.eastmoney.com/"})
        return resp.json().get("data") or {}
    except (httpx.HTTPError, ValueError):
        return {}


async def _ths_reasons(client: httpx.AsyncClient, day: str) -> dict[str, dict]:
    """同花顺的涨停池：多了一栏"涨停原因"和"几天几板"。取不到就没有原因，别的照常。"""
    out: dict[str, dict] = {}
    for page in (1, 2, 3):
        try:
            resp = await client.get(_THS_POOL, params={"page": page, "limit": 200, "filter": "HS,GEM2STAR", "order_field": "330324", "order_type": 0, "date": day,
                                                       "field": "199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004"},
                                    headers={**_UA, "Referer": "https://data.10jqka.com.cn/datacenterph/limitup/limtupInfo.html"})
            data = resp.json().get("data") or {}
        except (httpx.HTTPError, ValueError):
            break
        for row in data.get("info") or []:
            out[str(row.get("code"))] = {"reason": str(row.get("reason_type") or ""), "streak": str(row.get("high_days") or ""), "kind": str(row.get("limit_up_type") or "")}
        if len(out) >= int((data.get("page") or {}).get("total") or 0):
            break
    return out


def _hm(value) -> str:
    """92500 → 09:25"""
    text = f"{int(value or 0):06d}"
    return f"{text[:2]}:{text[2:4]}"


def limit_board(up: dict, broken: dict, down: dict, yesterday: dict, reasons: dict[str, dict]) -> dict:
    """涨停、炸板、跌停和连板梯队。"""
    ups = [{"code": r["c"], "name": r["n"], "streak": int(r.get("lbc") or 1), "first_sealed": _hm(r.get("fbt")), "opened": int(r.get("zbc") or 0),
            "seal_yi": round((r.get("fund") or 0) / 1e8, 2), "turnover_pct": round(r.get("hs") or 0, 1), "industry": r.get("hybk") or "",
            "reason": (reasons.get(r["c"]) or {}).get("reason", "")} for r in up.get("pool") or []]
    ladder: dict[int, list[str]] = {}
    for r in sorted(ups, key=lambda x: (-x["streak"], x["first_sealed"])):
        if r["streak"] >= 2:
            ladder.setdefault(r["streak"], []).append(r["name"])
    n_up, n_broken, n_down = len(ups), len(broken.get("pool") or []), len(down.get("pool") or [])
    prior = [r.get("zdp") for r in yesterday.get("pool") or [] if isinstance(r.get("zdp"), (int, float))]
    return {
        "limit_up": n_up, "broken": n_broken, "limit_down": n_down,
        "seal_rate_pct": round(n_up / (n_up + n_broken) * 100, 1) if n_up + n_broken else None,
        "first_board": sum(1 for r in ups if r["streak"] == 1), "multi_board": sum(1 for r in ups if r["streak"] >= 2),
        "max_streak": max((r["streak"] for r in ups), default=0),
        "ladder": [{"boards": k, "names": v} for k, v in sorted(ladder.items(), reverse=True)],
        "yesterday_limit_up_today_pct": round(sum(prior) / len(prior), 2) if prior else None,
        "yesterday_limit_up_count": len(prior),
        "stocks": ups,
    }


def themes(ups: list[dict], top: int = 6) -> list[dict]:
    """涨停集中在哪。有涨停原因就按原因里的词数（一只股票常挂好几个题材），没有就按行业数。"""
    tagged = [r for r in ups if r.get("reason")]
    counter: Counter[str] = Counter()
    members: dict[str, list[str]] = {}
    if len(tagged) >= max(3, len(ups) // 3):
        for r in tagged:
            for tag in {t.strip() for t in re.split(r"[+＋]", r["reason"]) if t.strip()}:
                counter[tag] += 1
                members.setdefault(tag, []).append(r["name"])
        basis = "涨停原因"
    else:
        for r in ups:
            if r.get("industry"):
                counter[r["industry"]] += 1
                members.setdefault(r["industry"], []).append(r["name"])
        basis = "所属行业"
    return [{"theme": tag, "count": n, "names": members[tag][:6], "basis": basis} for tag, n in counter.most_common(top) if n >= 2]


async def concept_boards(client: httpx.AsyncClient | None = None) -> list[dict]:
    """全部概念板块：成分股数、平均涨跌幅、领涨股。新浪的口径。"""
    async def load():
        own = client or httpx.AsyncClient(timeout=12.0)
        try:
            resp = await own.get(_SINA_BOARDS, params={"param": "class"}, headers={**_UA, "Referer": "https://finance.sina.com.cn"})
            text = resp.content.decode("gbk", "replace")
        except httpx.HTTPError:
            return []
        finally:
            if client is None:
                await own.aclose()
        out = []
        for node, raw in re.findall(r'"(gn_[a-z0-9_]+)":"([^"]+)"', text):
            f = raw.split(",")
            if len(f) < 13:
                continue
            try:
                out.append({"node": node, "name": f[1], "stocks": int(f[2]), "change_pct": round(float(f[5]), 2),
                            "leader": {"code": f[8][2:], "name": f[12], "change_pct": round(float(f[9]), 2)}})
            except ValueError:
                continue
        return out
    return await cache.cached("recap:concept-boards", 5 * cache.MINUTE, load) or []


async def concept_stocks(name: str, limit: int = 40) -> dict | None:
    """一个概念板块里有哪些股票（按今天涨跌幅排）。name 可以是板块名的一部分。"""
    boards = await concept_boards()
    key = (name or "").strip().lower()
    match = next((b for b in boards if b["name"].lower() == key), None) or next((b for b in boards if key and key in b["name"].lower()), None)
    if match is None:
        return None

    async def load():
        try:
            async with httpx.AsyncClient(timeout=12.0) as c:
                resp = await c.get(_SINA_NODE, params={"page": 1, "num": max(1, min(limit, 80)), "sort": "changepercent", "asc": 0, "node": match["node"]},
                                   headers={**_UA, "Referer": "https://finance.sina.com.cn"})
                rows = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        return [{"code": r.get("code"), "name": r.get("name"), "price": float(r.get("trade") or 0), "change_pct": round(float(r.get("changepercent") or 0), 2),
                 "pe": float(r["per"]) if r.get("per") else None, "mv_yi": round(float(r.get("mktcap") or 0) / 1e4, 1) if r.get("mktcap") else None,
                 "turnover_pct": round(float(r.get("turnoverratio") or 0), 2)} for r in rows or []]
    stocks = await cache.cached(f"recap:concept:{match['node']}:{limit}", 10 * cache.MINUTE, load)
    return {"board": match["name"], "stock_count": match["stocks"], "change_pct": match["change_pct"], "stocks": stocks or [],
            "similar": [b["name"] for b in boards if key and key in b["name"].lower() and b is not match][:6]}


def seat_kind(name: str) -> str:
    return next((kind for mark, kind in SEAT_KINDS if mark in name), "营业部")


async def billboard(day: str) -> dict:
    """龙虎榜：今天上榜的股票，以及买卖最多的席位。day 是 2026-10-08 这种写法。"""
    flt = f"(TRADE_DATE='{day}')"
    stocks_rows, _ = await datacenter("RPT_DAILYBILLBOARD_DETAILSNEW", filter=flt, page_size=200, sort="BILLBOARD_NET_AMT")
    seat_rows, _ = await datacenter("RPT_BILLBOARD_DAILYDETAILSBUY", filter=flt, page_size=500, sort="NET")
    seen, listed = set(), []
    for r in stocks_rows:
        if r.get("SECURITY_CODE") in seen:
            continue
        seen.add(r.get("SECURITY_CODE"))
        listed.append({"code": r.get("SECURITY_CODE"), "name": r.get("SECURITY_NAME_ABBR") or "", "change_pct": round(r.get("CHANGE_RATE") or 0, 2),
                       "net_yi": round((r.get("BILLBOARD_NET_AMT") or 0) / 1e8, 2), "why": r.get("EXPLANATION") or "", "note": r.get("EXPLAIN") or ""})
    names = {r["code"]: r["name"] for r in listed}
    seats: dict[str, dict] = {}
    for r in seat_rows:
        name = r.get("OPERATEDEPT_NAME") or ""
        if not name:
            continue
        item = seats.setdefault(name, {"seat": name, "kind": seat_kind(name), "net_yi": 0.0, "stocks": []})
        item["net_yi"] += (r.get("NET") or 0) / 1e8
        stock = names.get(r.get("SECURITY_CODE")) or r.get("SECURITY_CODE") or ""     # 席位明细里只有代码，名字从上榜列表里对
        if stock and stock not in item["stocks"]:
            item["stocks"].append(stock)
    ranked = sorted(({**s, "net_yi": round(s["net_yi"], 2), "stocks": s["stocks"][:5]} for s in seats.values()), key=lambda s: -abs(s["net_yi"]))
    institutions = [s for s in ranked if s["kind"] == "机构"]
    return {"count": len(listed), "top_buy": listed[:6], "top_sell": sorted(listed, key=lambda r: r["net_yi"])[:4],
            "institution_net_yi": round(sum(s["net_yi"] for s in institutions), 2) if institutions else None,
            "northbound_net_yi": round(sum(s["net_yi"] for s in ranked if s["kind"] == "北向"), 2) if any(s["kind"] == "北向" for s in ranked) else None,
            "seats": [s for s in ranked if s["kind"] in ("营业部", "散户集中的营业部")][:8]}


def gauge(board: dict, breadth: dict | None) -> dict:
    """把"今天热不热"说成一句话。五个数字各打一分（-1 / 0 / +1），加起来落在哪一档。尺子是固定的，不是预测。"""
    points, parts = 0, []

    def score(value, cold, hot, label, unit=""):
        nonlocal points
        if value is None:
            return
        step = 1 if value >= hot else -1 if value <= cold else 0
        points += step
        parts.append(f"{label} {value:g}{unit}")
    score(board.get("limit_up"), 30, 70, "涨停", " 只")
    down_count = board.get("limit_down") or 0
    points += 1 if down_count <= 5 else -1 if down_count >= 20 else 0
    parts.append(f"跌停 {down_count} 只")
    score(board.get("seal_rate_pct"), 60, 80, "封板率", "%")
    score(board.get("yesterday_limit_up_today_pct"), 0, 3, "昨日涨停今日平均", "%")
    up, down = (breadth or {}).get("up"), (breadth or {}).get("down")
    if up is not None and down:
        score(round(up / (up + down) * 100, 1), 35, 60, "上涨家数占比", "%")
    label = "高潮" if points >= 4 else "偏热" if points >= 2 else "偏冷" if points <= -2 else "一般"
    label = "冰点" if points <= -4 else label
    return {"label": label, "points": points, "basis": parts}


async def build(day: date | str | None = None) -> dict:
    """拼出一份复盘。哪一块取不到，那一块就是空的，别的照常给。"""
    from wealthpilot.services import screener
    from wealthpilot.services.market_data import fetch_indices

    ymd = _ymd(day)
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"

    async def load():
        async with httpx.AsyncClient(timeout=12.0) as client:
            up, broken, down, prior, reasons, boards = await asyncio.gather(
                _em_pool(client, "getTopicZTPool", ymd, "fbt:asc"), _em_pool(client, "getTopicZBPool", ymd, "fbt:asc"),
                _em_pool(client, "getTopicDTPool", ymd, "fund:asc"), _em_pool(client, "getYesterdayZTPool", ymd, "zs:desc"),
                _ths_reasons(client, ymd), concept_boards(client))
        if not up.get("pool") and not down.get("pool") and not broken.get("pool"):
            return None                         # 这一天没有数据：休市，或者还没开盘
        actual = str(up.get("qdate") or down.get("qdate") or ymd)
        trade_day = f"{actual[:4]}-{actual[4:6]}-{actual[6:]}"
        snap, indices, lhb = await asyncio.gather(screener.snapshot(), fetch_indices(), billboard(trade_day), return_exceptions=True)
        breadth = screener.market_breadth(snap) if isinstance(snap, dict) and snap else None
        board = limit_board(up, broken, down, prior, reasons)
        ranked = sorted(boards, key=lambda b: -b["change_pct"])
        return {"day": trade_day, "indices": indices if isinstance(indices, list) else [], "breadth": breadth,
                "limits": {k: v for k, v in board.items() if k != "stocks"}, "limit_up_stocks": board["stocks"][:60],
                "themes": themes(board["stocks"]), "concepts": {"top": ranked[:6], "bottom": ranked[-4:][::-1]} if ranked else None,
                "billboard": lhb if isinstance(lhb, dict) else None, "mood": gauge(board, breadth)}
    if day is None:
        return await cache.cached(f"recap:{iso}", 10 * cache.MINUTE, load)
    return await load()


def text(recap: dict | None) -> str:
    """复盘写成几行字：推到手机、打在终端里用。"""
    if not recap:
        return "今天没有可复盘的数据（休市，或者还没开盘）。"
    lines = [f"{recap['day']} 大盘复盘 · 情绪{recap['mood']['label']}"]
    if recap["indices"]:
        lines.append("指数：" + "，".join(f"{i['name']} {i.get('change', '')}" for i in recap["indices"][:4]))
    b, lim = recap.get("breadth"), recap["limits"]
    if b:
        lines.append(f"涨跌：{b['up']} 家涨，{b['down']} 家跌，中位数 {b['median_change_pct']:+.2f}%")
    seal = f"，封板率 {lim['seal_rate_pct']:g}%" if lim.get("seal_rate_pct") is not None else ""
    lines.append(f"涨停 {lim['limit_up']}（首板 {lim['first_board']}，连板 {lim['multi_board']}），炸板 {lim['broken']}{seal}，跌停 {lim['limit_down']}")
    if lim.get("yesterday_limit_up_today_pct") is not None:
        lines.append(f"昨天涨停的 {lim['yesterday_limit_up_count']} 只今天平均 {lim['yesterday_limit_up_today_pct']:+.2f}%")
    for step in lim["ladder"][:4]:
        lines.append(f"{step['boards']} 连板：{'、'.join(step['names'][:6])}")
    if recap["themes"]:
        lines.append("涨停集中在：" + "；".join(f"{t['theme']} {t['count']} 只（{'、'.join(t['names'][:3])}）" for t in recap["themes"][:4]))
    if recap.get("concepts"):
        lines.append("概念领涨：" + "，".join(f"{c['name']} {c['change_pct']:+.2f}%" for c in recap["concepts"]["top"][:4])
                     + "；领跌：" + "，".join(f"{c['name']} {c['change_pct']:+.2f}%" for c in recap["concepts"]["bottom"][:3]))
    lhb = recap.get("billboard")
    if lhb and lhb["count"]:
        inst = f"，机构席位合计净买 {lhb['institution_net_yi']:+.2f} 亿" if lhb.get("institution_net_yi") is not None else ""
        inst += f"，北向席位 {lhb['northbound_net_yi']:+.2f} 亿" if lhb.get("northbound_net_yi") is not None else ""
        lines.append(f"龙虎榜 {lhb['count']} 只{inst}；净买最多：" + "，".join(f"{r['name']} {r['net_yi']:+.2f} 亿" for r in lhb["top_buy"][:3]))
        active = [s for s in lhb["seats"] if s["kind"] == "营业部"][:3]
        if active:
            lines.append("活跃营业部：" + "；".join(f"{s['seat'].replace('股份有限公司', '').replace('有限责任公司', '')[:20]} {s['net_yi']:+.2f} 亿（{'、'.join(s['stocks'][:2])}）" for s in active))
    lines.append("情绪刻度的依据：" + "，".join(recap["mood"]["basis"]))
    return "\n".join(lines)
