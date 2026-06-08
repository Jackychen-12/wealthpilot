"""API 路由。"""

from fastapi import APIRouter

from wealthpilot.routes.portfolio import router as portfolio_router
from wealthpilot.routes.market import router as market_router
from wealthpilot.routes.analysis import router as analysis_router
from wealthpilot.routes.chat import router as chat_router
from wealthpilot.routes.report import router as report_router

api_router = APIRouter(prefix="/api")
api_router.include_router(portfolio_router)
api_router.include_router(market_router)
api_router.include_router(analysis_router)
api_router.include_router(chat_router)
api_router.include_router(report_router)
