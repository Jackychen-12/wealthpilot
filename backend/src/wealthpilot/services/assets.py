"""多资产类别报价 — 基金 / 股票 / ETF / 加密货币。

此前只支持场外基金（天天基金净值接口）。持仓里放个股或 ETF 的话，
取不到价格，市值和收益率全按成本价算，等于没算。

统一入口是 fetch_asset_price(code, asset_type)，各类型走各自的免费源：

    fund    天天基金历史净值（已有）
    stock   新浪实时行情 hq.sinajs.cn
    etf     同上（ETF 在交易所按股票撮合，报价接口相同）
    crypto  CoinGecko simple/price（无需鉴权）

新浪接口返回 GBK 编码的 JS 赋值语句，且校验 Referer —— 两点都容易踩。
"""

from __future__ import annotations

import re

import httpx

from wealthpilot.services.market_data import fetch_fund_nav

ASSET_TYPES = ("fund", "stock", "etf", "crypto")

_SINA_URL = "https://hq.sinajs.cn/list="
_SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}
_SINA_LINE_RE = re.compile(r'hq_str_(\w+)="([^"]*)"')

_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# 常见加密货币代码 → CoinGecko id
CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether",
    "BNB": "binancecoin", "SOL": "solana", "XRP": "ripple",
    "DOGE": "dogecoin", "ADA": "cardano",
}


def sina_symbol(code: str) -> str:
    """A 股 / ETF 代码补市场前缀。

    沪市：6 开头（主板股票）、5 开头（沪市基金/ETF）、9 开头（B 股）
    深市：0 / 3 开头（主板与创业板）、1 开头（深市基金/ETF）
    已带前缀的原样返回。
    """
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith(("0", "3", "1")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"  # 北交所
    return f"sh{code}"


def parse_sina_quote(line: str) -> dict | None:
    """解析单条新浪行情。

    字段顺序：0 名称 / 1 今开 / 2 昨收 / 3 现价 / 4 最高 / 5 最低 …
    停牌或代码不存在时现价为 0，此时视为无效报价而不是"价格是 0"。
    """
    fields = line.split(",")
    if len(fields) < 6 or not fields[0]:
        return None
    try:
        prev_close = float(fields[2])
        current = float(fields[3])
    except ValueError:
        return None
    if current <= 0:
        return None

    change_pct = ((current - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
    return {
        "name": fields[0],
        "price": current,
        "prev_close": prev_close,
        "change_pct": round(change_pct, 2),
        "date": fields[30] if len(fields) > 30 else "",
    }


async def fetch_sina_quotes(codes: list[str]) -> dict[str, dict]:
    """批量取 A 股 / ETF 报价。一次请求拿多个代码，避免逐个往返。"""
    if not codes:
        return {}
    symbols = [sina_symbol(c) for c in codes]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_SINA_URL + ",".join(symbols), headers=_SINA_HEADERS)
            resp.raise_for_status()
            # 新浪返回 GBK，httpx 按响应头猜会得到乱码
            text = resp.content.decode("gbk", errors="replace")
    except Exception:
        return {}

    by_symbol: dict[str, dict] = {}
    for symbol, payload in _SINA_LINE_RE.findall(text):
        quote = parse_sina_quote(payload)
        if quote:
            by_symbol[symbol] = quote

    # 用调用方给的原始代码作键回填
    return {
        code: by_symbol[sina_symbol(code)]
        for code in codes
        if sina_symbol(code) in by_symbol
    }


async def fetch_crypto_quotes(codes: list[str], currency: str = "cny") -> dict[str, dict]:
    """批量取加密货币报价（CoinGecko，无需鉴权）。"""
    ids = {c.upper(): CRYPTO_IDS.get(c.upper()) for c in codes}
    known = {k: v for k, v in ids.items() if v}
    if not known:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _COINGECKO_URL,
                params={"ids": ",".join(sorted(set(known.values()))),
                        "vs_currencies": currency,
                        "include_24hr_change": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return {}

    out: dict[str, dict] = {}
    for code, gecko_id in known.items():
        entry = data.get(gecko_id) or {}
        price = entry.get(currency)
        if not price:
            continue
        out[code] = {
            "name": code,
            "price": float(price),
            "prev_close": 0.0,
            "change_pct": round(float(entry.get(f"{currency}_24h_change", 0) or 0), 2),
            "date": "",
        }
    return out


async def fetch_asset_price(code: str, asset_type: str = "fund") -> dict | None:
    """单个资产的最新价。返回 None 表示取不到，调用方应回退到成本价。"""
    asset_type = (asset_type or "fund").lower()

    if asset_type in ("stock", "etf"):
        return (await fetch_sina_quotes([code])).get(code)

    if asset_type == "crypto":
        return (await fetch_crypto_quotes([code])).get(code.upper())

    # fund：走净值接口，取最近一期
    nav_list = await fetch_fund_nav(code, 2)
    if not nav_list:
        return None
    latest = nav_list[0]
    return {
        "name": "",
        "price": float(latest["nav"]),
        "prev_close": float(nav_list[1]["nav"]) if len(nav_list) > 1 else 0.0,
        "change_pct": float(latest.get("daily_return", 0) or 0),
        "date": latest.get("nav_date", ""),
    }


async def fetch_prices_by_type(items: list[tuple[str, str]]) -> dict[str, float]:
    """批量取价，按类型分组以减少请求数。

    Args:
        items: [(code, asset_type), ...]
    Returns:
        {code: price}，取不到的代码不出现在结果里。
    """
    by_type: dict[str, list[str]] = {}
    for code, asset_type in items:
        by_type.setdefault((asset_type or "fund").lower(), []).append(code)

    prices: dict[str, float] = {}

    market_codes = by_type.get("stock", []) + by_type.get("etf", [])
    for code, quote in (await fetch_sina_quotes(market_codes)).items():
        prices[code] = quote["price"]

    for code, quote in (await fetch_crypto_quotes(by_type.get("crypto", []))).items():
        prices[code] = quote["price"]

    for code in by_type.get("fund", []):
        quote = await fetch_asset_price(code, "fund")
        if quote:
            prices[code] = quote["price"]

    return prices
