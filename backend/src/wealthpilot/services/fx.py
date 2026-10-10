"""汇率：港元、美元兑人民币。

持仓这本账是按人民币记的 —— 市值、盈亏、占比、风险都是人民币。港股美股要记进来，现价和成本就得折算。

用的是中国货币网每天公布的人民币汇率中间价（官方）：现价按最新的折，成本按买入那天的折（休市日取之前最近的一个工作日）。
它不通时退到新浪的即时汇率 —— 那是市场价，不是中间价，和中间价差千分之几，而且没有历史。

如实说明两件事：
- 港股通实际结算用的是当天的结算汇率，不是中间价；这里折出来的人民币数和券商账户里的会差一点。
- 成本既然按买入日的汇率折成了人民币，之后的盈亏里就包含了汇率的涨跌，不只是股价的。
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from wealthpilot.services import cache, global_stocks, sources
from wealthpilot.services.sources import SourceError

PAIR = {"HKD": "HKD/CNY", "USD": "USD/CNY"}
MARKET_CURRENCY = {"hk": "HKD", "us": "USD"}
SIGN = {"CNY": "¥", "HKD": "HK$", "USD": "US$"}
_UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.chinamoney.com.cn/chinese/bkccpr/"}


def currency_of(code: str) -> str:
    """这只证券用什么货币计价：港股 HKD，美股 USD，其余都当人民币。"""
    found = global_stocks.parse(code)
    return MARKET_CURRENCY[found[0]] if found else "CNY"


async def _chinamoney(currency: str, on: date | None, transport: httpx.AsyncBaseTransport | None = None) -> dict | None:
    """人民币汇率中间价。on 为空取最新；给了日期就取那天或之前最近一个工作日的。"""
    end = on or date.today()
    params = {"startDate": (end - timedelta(days=12)).isoformat(), "endDate": end.isoformat(), "currency": PAIR[currency], "pageNum": "1", "pageSize": "15"}
    async with httpx.AsyncClient(timeout=10, transport=transport, headers=_UA) as client:
        resp = await client.post("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew", params=params)
    try:
        body = resp.json()
        records, listed = body["records"], body["data"].get("searchlist") or []
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise SourceError(f"中国货币网的汇率中间价返回 {resp.status_code}，不是预期的结构") from e
    if PAIR[currency] not in listed:
        raise SourceError(f"中国货币网的汇率中间价里没有 {PAIR[currency]} 这一列")
    column = listed.index(PAIR[currency])
    for record in sorted(records or [], key=lambda r: str(r.get("date")), reverse=True):
        try:
            return {"currency": currency, "rate": float(record["values"][column]), "date": str(record["date"])[:10], "source": "中国货币网（人民币汇率中间价）"}
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    if records:
        raise SourceError("中国货币网的汇率中间价记录里找不到 date / values")
    return None                                # 那十来天里没有公布过：日期太早或在未来


async def _sina(currency: str, transport: httpx.AsyncBaseTransport | None = None) -> dict | None:
    """新浪的即时汇率：只有现在的，没有历史。"""
    name = {"HKD": "fx_shkdcny", "USD": "fx_susdcny"}[currency]
    async with httpx.AsyncClient(timeout=8, transport=transport, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}) as client:
        resp = await client.get(f"https://hq.sinajs.cn/list={name}")
    text = resp.content.decode("gbk", errors="replace")
    if resp.status_code != 200 or "hq_str_" not in text or '"' not in text:
        raise SourceError(f"新浪汇率返回 {resp.status_code}，内容不是预期的格式")
    fields = text.split('"')[1].split(",")
    try:
        value = float(fields[1])
    except (IndexError, ValueError) as e:
        raise SourceError("新浪汇率的字段变了：第二项不是数字") from e
    if not 0.01 < value < 100:
        raise SourceError(f"新浪汇率给的数不像汇率：{value}")
    return {"currency": currency, "rate": value, "date": date.today().isoformat(), "source": "新浪财经（即时汇率，不是中间价）"}


async def rate(currency: str, on: date | None = None) -> dict | None:
    """1 单位外币折多少人民币：{currency, rate, date, source}。人民币直接是 1；取不到返回 None。"""
    if currency == "CNY":
        return {"currency": "CNY", "rate": 1.0, "date": (on or date.today()).isoformat(), "source": ""}
    if currency not in PAIR:
        return None
    past = on is not None and on < date.today()

    async def load():
        chain = [("chinamoney", lambda: _chinamoney(currency, on))]
        if not past:                           # 历史上某一天的汇率，即时行情顶不了
            chain.append(("sina", lambda: _sina(currency)))
        value, _ = await sources.first(chain)
        return value
    if past:                                   # 过去某天的中间价不会再变
        return await cache.resilient(f"fx:{currency}:{on.isoformat()}", 3650 * cache.DAY, load, keep=3650 * cache.DAY, what=f"{on} 的{currency}汇率")
    return await cache.resilient(f"fx:{currency}:latest", 30 * cache.MINUTE, load, keep=30 * cache.DAY, what=f"{currency} 兑人民币汇率")


async def factor(code: str) -> float | None:
    """这只证券的现价乘上多少是人民币。人民币计价的是 1；港股美股是最新汇率；取不到汇率返回 None（不拿 1 冒充）。"""
    currency = currency_of(code)
    if currency == "CNY":
        return 1.0
    found = await rate(currency)
    return found["rate"] if found else None


async def book(code: str, cost: float, bought: date | None = None) -> dict:
    """一笔持仓怎么入账。港股美股：用户填的是原币种的成本，按买入日的中间价折成人民币记账，原来的数和用的汇率一起留着。

    返回 {code, currency, cost_price（人民币）, cost_native, cost_fx}。取不到汇率抛 SourceError —— 宁可不记，也不记一笔币种不明的账。
    """
    currency = currency_of(code)
    if currency == "CNY":
        return {"code": code, "currency": "CNY", "cost_price": cost, "cost_native": None, "cost_fx": None}
    found = await rate(currency, bought if bought and bought < date.today() else None) or (await rate(currency) if bought else None)
    if not found:
        raise SourceError(f"现在取不到{currency}兑人民币的汇率，这笔{global_stocks.MARKET_LABEL[global_stocks.parse(code)[0]]}持仓先记不了，稍后再试")
    return {"code": global_stocks.canonical(code), "currency": currency, "cost_price": round(cost * found["rate"], 4), "cost_native": cost, "cost_fx": found["rate"]}
