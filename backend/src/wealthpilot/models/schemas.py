"""Pydantic request/response schemas。"""

from datetime import date

from pydantic import BaseModel, Field


# === Portfolio ===
class PortfolioCreate(BaseModel):
    fund_code: str = Field(..., description="基金代码", examples=["007340"])
    fund_name: str = Field(..., description="基金名称", examples=["国泰半导体芯片ETF联接"])
    shares: float = Field(..., gt=0, description="持有份额")
    cost_price: float = Field(..., gt=0, description="成本净值")
    buy_date: date = Field(..., description="买入日期")
    category: str = Field(default="equity", description="equity/bond/money/hybrid")
    industry: str = Field(default="", description="行业标签")


class PortfolioUpdate(BaseModel):
    fund_name: str | None = None
    shares: float | None = None
    cost_price: float | None = None
    category: str | None = None
    industry: str | None = None


class PortfolioResponse(BaseModel):
    id: int
    fund_code: str
    fund_name: str
    shares: float
    cost_price: float
    buy_date: date
    category: str
    industry: str
    latest_nav: float | None = None
    market_value: float | None = None
    total_return: float | None = None
    return_pct: float | None = None


# === Market ===
class IndexInfo(BaseModel):
    name: str
    value: str
    change: str
    up: bool


class NewsItem(BaseModel):
    tag: str
    text: str


class FundDetail(BaseModel):
    code: str
    name: str
    nav: float
    nav_date: str
    daily_return: float
    category: str
    manager: str = ""


# === Analysis ===
class OverviewResponse(BaseModel):
    weekly_return: float
    weekly_growth_pct: float
    excess_return_pct: float
    volatility_status: str
    description: str
    total_market_value: float


class AttributionItem(BaseModel):
    name: str
    value: str
    pct: float
    positive: bool


class DrawdownItem(BaseModel):
    name: str
    value: str
    severity: str


class HealthDimension(BaseModel):
    name: str
    score: float
    status: str
    severity: str


class SuggestionItem(BaseModel):
    title: str
    desc: str
    priority: str = "medium"


# === Chat ===
class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    history: list[dict[str, str]] = Field(default_factory=list, description="对话历史")
