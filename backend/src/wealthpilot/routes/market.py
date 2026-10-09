"""行情数据路由 — 多源聚合。"""

import asyncio

from fastapi import APIRouter, HTTPException

from wealthpilot.models.schemas import IndexInfo, NewsItem
from wealthpilot.services.market_data import (
    fetch_fund_nav,
    fetch_indices,
    fetch_market_news,
    get_comprehensive_fund_info,
    get_fund_rank_akshare,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/indices", response_model=list[IndexInfo])
async def get_indices():
    """实时大盘指数（AKShare + 新浪 fallback）。"""
    return await fetch_indices()


@router.get("/news", response_model=list[NewsItem])
async def get_news():
    """财经要闻（东方财富）。"""
    return await fetch_market_news()


@router.get("/fund/{fund_code}")
async def get_fund(fund_code: str):
    """基金综合信息（实时估值 + 经理 + 规模 + 排名）。"""
    info = await get_comprehensive_fund_info(fund_code)
    if not info or not info.get("name"):
        return {"error": f"基金 {fund_code} 信息获取失败"}
    return info


@router.get("/fund/{fund_code}/nav")
async def get_fund_nav_endpoint(fund_code: str, days: int = 30):
    """基金近 N 日净值历史。"""
    nav_list = await fetch_fund_nav(fund_code, days)
    return {"fund_code": fund_code, "count": len(nav_list), "data": nav_list}


@router.get("/fund/{fund_code}/rank")
async def get_fund_rank(fund_code: str):
    """基金排名信息（近1周/1月/3月/1年收益率）。"""
    rank = await asyncio.to_thread(get_fund_rank_akshare, fund_code)
    if not rank:
        return {"error": f"基金 {fund_code} 排名数据获取失败"}
    return rank


@router.get("/stock/{code}")
async def get_stock(code: str):
    """A 股 / ETF 实时行情与估值。code 可写 600519、sh600519 或 600519.SH。"""
    from wealthpilot.services.stocks import fetch_stock_quote
    result = await fetch_stock_quote(code)
    if not result:
        return {"error": f"股票 {code} 行情获取失败"}
    return result


@router.get("/stock/{code}/kline")
async def get_stock_kline(code: str, days: int = 120):
    """A 股 / ETF 前复权日线（最新在前），字段与基金净值历史一致。"""
    from wealthpilot.services.stocks import fetch_stock_kline
    data = await fetch_stock_kline(code, max(5, min(days, 750)))
    basis = data[0].get("price_basis", "前复权") if data else "前复权"
    return {"code": code, "count": len(data), "data": data, "price_basis": f"{basis}收盘价"}


@router.get("/stock/{code}/valuation-history")
async def get_valuation_series(code: str):
    """近五年 PE / PB 走势（每周取一个点，画图用），最早在前。"""
    from wealthpilot.services.stocks import fetch_valuation_history
    rows = list(reversed(await fetch_valuation_history(code)))
    return {"code": code, "data": [{"date": r["date"], "pe": r["pe_ttm"], "pb": r["pb"]} for r in rows[::5] + rows[-1:]]}


@router.get("/recap")
async def market_recap():
    """今天市场发生了什么：涨停与连板、题材热点、龙虎榜、情绪刻度。不调用模型。"""
    from wealthpilot.services import recap
    report = await recap.build()
    if not report:
        raise HTTPException(404, "今天没有可复盘的数据（休市，或者还没开盘）")
    return report


@router.get("/macro")
async def market_macro():
    """宏观数据：景气、物价、货币信贷、利率。"""
    from wealthpilot.services import macro
    return await macro.snapshot()


@router.get("/concepts")
async def market_concepts(name: str = "", limit: int = 40):
    """不带 name：全部概念板块按涨跌幅排；带 name：这个板块的成分股。"""
    from wealthpilot.services import recap
    if not name.strip():
        return sorted(await recap.concept_boards(), key=lambda b: -b["change_pct"])
    found = await recap.concept_stocks(name, limit)
    if not found:
        raise HTTPException(404, f"没有找到概念板块「{name}」")
    return found


@router.get("/stock/{code}/reverse-dcf")
async def stock_reverse_dcf(code: str):
    """反向 DCF：现价隐含了多高的利润增速。"""
    from wealthpilot.services.agents.depth_tools import reverse_dcf_for
    result = await reverse_dcf_for(code)
    if result is None:
        raise HTTPException(404, f"没有取到 {code} 的行情")
    return result


@router.get("/stock/{code}/minute")
async def get_stock_minute(code: str, days: int = 1):
    """分时：每分钟的价格、均价与成交量。days=1 最近一个交易日，days=5 最近五个交易日。"""
    from wealthpilot.services.stocks import fetch_minute
    data = await fetch_minute(code, 5 if days > 1 else 1)
    if not data:
        raise HTTPException(404, f"没有取到 {code} 的分时数据")
    return data


@router.get("/stock/{code}/capital-series")
async def get_capital_series(code: str):
    """画图用的完整序列：近 30 日资金流向、近 120 日融资余额、近 8 期股东户数。和 Agent 的资金工具是同一份数据。"""
    import asyncio

    from wealthpilot.services import capital
    flow, margin, holders = await asyncio.gather(
        capital.fetch_fund_flow(code, 30), capital.fetch_margin(code, 120), capital.fetch_holder_counts(code, 8))
    return {"code": code, "flow": flow, "margin": list(reversed(margin)), "holders": list(reversed(holders))}


@router.get("/crypto/{symbol}")
async def get_crypto(symbol: str = "bitcoin"):
    """加密货币价格（CoinGecko）。symbol: bitcoin/ethereum/solana"""
    from wealthpilot.services.stock_data import fetch_crypto_price
    result = await fetch_crypto_price(symbol)
    if not result:
        return {"error": f"{symbol} 价格获取失败"}
    return result
