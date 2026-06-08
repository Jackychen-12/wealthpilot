"""行情数据路由 — 多源聚合。"""

from fastapi import APIRouter

from wealthpilot.models.schemas import IndexInfo, NewsItem
from wealthpilot.services.market_data import (
    fetch_fund_info,
    fetch_fund_nav,
    fetch_indices,
    fetch_market_news,
    get_comprehensive_fund_info,
    get_fund_rank_akshare,
    get_macro_data_akshare,
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
    rank = get_fund_rank_akshare(fund_code)
    if not rank:
        return {"error": f"基金 {fund_code} 排名数据获取失败"}
    return rank


@router.get("/macro")
async def get_macro():
    """宏观经济指标（PMI/CPI 等）。"""
    return get_macro_data_akshare()
