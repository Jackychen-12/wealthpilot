"""股票/ETF/加密货币数据查询 — 扩展多资产支持。"""

import httpx


async def fetch_stock_quote(code: str) -> dict | None:
    """查询 A 股/ETF 实时行情（新浪接口）。

    code 格式: sh600519 / sz000001 / sh510300
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://hq.sinajs.cn/list={code}",
                headers={"Referer": "https://finance.sina.com.cn"},
            )
            text = resp.text
            parts = text.split('"')[1].split(",")
            if len(parts) < 10:
                return None
            return {
                "code": code,
                "name": parts[0],
                "open": float(parts[1]),
                "prev_close": float(parts[2]),
                "price": float(parts[3]),
                "high": float(parts[4]),
                "low": float(parts[5]),
                "volume": float(parts[8]),
                "amount": float(parts[9]),
                "change_pct": round((float(parts[3]) - float(parts[2])) / float(parts[2]) * 100, 2) if float(parts[2]) > 0 else 0,
            }
    except Exception:
        return None


async def fetch_crypto_price(symbol: str = "bitcoin") -> dict | None:
    """查询加密货币价格（CoinGecko 免费 API）。"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"https://api.coingecko.com/api/v3/simple/price",
                params={"ids": symbol, "vs_currencies": "usd,cny", "include_24hr_change": "true"},
            )
            data = resp.json()
            if symbol in data:
                return {
                    "symbol": symbol,
                    "price_usd": data[symbol].get("usd"),
                    "price_cny": data[symbol].get("cny"),
                    "change_24h": data[symbol].get("usd_24h_change"),
                }
    except Exception:
        return None


async def fetch_etf_nav(code: str) -> dict | None:
    """查询 ETF 净值（与股票同源，走新浪接口）。"""
    return await fetch_stock_quote(code)
