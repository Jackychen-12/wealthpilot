"""WealthPilot MCP Server — 35 investment tools for Claude Code / Cursor."""

from __future__ import annotations

# mcp 2.x 把 FastMCP 改名为 MCPServer；构造器、.tool() 与 .run() 签名保持兼容
from mcp.server.mcpserver import MCPServer

from wealthpilot.services.agents.tools import execute_tool

mcp = MCPServer(
    "wealthpilot",
    instructions=(
        "WealthPilot 智能投顾工具集：59 个实时投资分析工具，覆盖 A 股个股研究（基本面、估值分位、走势、同行、资金与筹码、一致预期与消息、选股、联网搜索、每日复盘、宏观、反向 DCF）、基金查询、持仓分析、风险评估、穿透与回测。"
        "市场工具无需持仓数据即可使用；持仓/风险工具会自动从本地数据库加载用户持仓。"
    ),
)

_ctx: dict = {"holdings": None, "nav_data": None, "nav_history": None, "profile": None}


async def _ensure_context() -> tuple[list, dict, dict, object]:
    """Lazy-load holdings + NAV data + risk profile from SQLite."""
    if _ctx["holdings"] is not None:
        return _ctx["holdings"], _ctx["nav_data"], _ctx["nav_history"], _ctx["profile"]

    from wealthpilot.services.context import load_local_user, load_market_context
    from wealthpilot.settings import get_settings

    # MCP 是本机单用户场景，默认取匿名档；Web 侧才按登录用户隔离
    _ctx["holdings"], _ctx["profile"] = load_local_user(get_settings().local_user_id)
    nav_data, nav_history = await load_market_context(_ctx["holdings"])

    _ctx["nav_data"] = nav_data
    _ctx["nav_history"] = nav_history
    return _ctx["holdings"], nav_data, nav_history, _ctx["profile"]


# ═══════════════════════════════════════════════════════════
# Market Tools (stateless — no portfolio needed)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def get_fund_info(fund_code: str) -> str:
    """Query fund basic info: name, NAV, valuation, type.
    查询基金基本信息（名称、最新净值、估值、类型）。fund_code 示例: 007340, 110011"""
    return await execute_tool("get_fund_info", {"fund_code": fund_code}, [], {}, None)


@mcp.tool()
async def get_nav_history(fund_code: str, days: int = 30) -> str:
    """Query fund NAV history for N days with daily returns.
    查询基金近 N 天净值走势（日期、净值、日涨跌幅），用于趋势分析。"""
    return await execute_tool("get_nav_history", {"fund_code": fund_code, "days": days}, [], {}, None)


@mcp.tool()
async def search_market_news(keyword: str = "") -> str:
    """Fetch latest financial news headlines.
    获取最新财经要闻，了解市场动态。"""
    return await execute_tool("search_market_news", {"keyword": keyword}, [], {}, None)


# ═══════════════════════════════════════════════════════════
# Portfolio Tools (load holdings from DB)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def get_portfolio_overview() -> str:
    """Calculate portfolio overview: total value, returns, weekly P&L, Sharpe ratio.
    持仓总览：总市值、总收益、周收益、Sharpe 比率。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_portfolio_overview", {}, h, nd, nh)


@mcp.tool()
async def get_attribution() -> str:
    """Per-fund return attribution analysis.
    按基金维度收益归因：哪只贡献最大、哪只拖累最多。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_attribution", {}, h, nd, nh)


@mcp.tool()
async def get_health_score() -> str:
    """5-dimension portfolio health score: returns, volatility, diversification, style, risk-return.
    组合健康度 5 维评分（收益表现、波动控制、分散度、风格匹配、风险收益比）。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_health_score", {}, h, nd, nh)


@mcp.tool()
async def get_investment_suggestions() -> str:
    """Rule-based investment suggestions: concentration, loss, correlation, category balance.
    规则引擎投资建议（集中度、亏损、相关性、类别均衡检查）。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_investment_suggestions", {}, h, nd, nh)


# ═══════════════════════════════════════════════════════════
# Risk Tools (load holdings from DB)
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def calculate_return(fund_code: str, days: int) -> str:
    """Calculate cumulative return over N trading days. days: 5≈1week, 21≈1month, 63≈3months.
    计算基金指定天数内的累计收益率。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("calculate_return", {"fund_code": fund_code, "days": days}, h, nd, nh)


@mcp.tool()
async def compare_funds(fund_codes: list[str]) -> str:
    """Compare multiple funds' recent performance (2-5 funds).
    对比多只基金近期表现（净值、涨跌幅），2-5 只。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("compare_funds", {"fund_codes": fund_codes}, h, nd, nh)


@mcp.tool()
async def get_drawdown_analysis() -> str:
    """Analyze drawdown for all holdings: current drop, max drawdown, recovery days.
    全部持仓回撤分析（当前跌幅、最大回撤、恢复天数）。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_drawdown_analysis", {}, h, nd, nh)


@mcp.tool()
async def get_max_drawdown(fund_code: str) -> str:
    """Calculate max drawdown + recovery days for a single fund.
    单只基金最大回撤 + 恢复天数。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_max_drawdown", {"fund_code": fund_code}, h, nd, nh)


@mcp.tool()
async def get_correlation_matrix() -> str:
    """Calculate correlation matrix across held funds to assess diversification.
    持仓基金相关性矩阵，评估分散化程度。"""
    h, nd, nh, _ = await _ensure_context()
    return await execute_tool("get_correlation_matrix", {}, h, nd, nh)


# ═══════════════════════════════════════════════════════════
# Compute / Check Tools（确定性计算，不让模型自己算）
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def compute_concentration() -> str:
    """Portfolio concentration: weights, max weight, HHI, effective holdings.
    持仓集中度：各基金权重、最大单一权重、HHI 指数、有效持仓数。
    需要引用任何占比数字时用本工具，不要按市值心算。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool("compute_concentration", {}, h, nd, nh, pf)


@mcp.tool()
async def simulate_portfolio_change(changes: list[dict]) -> str:
    """Simulate portfolio metrics after proposed position changes.
    推演仓位变动后的组合指标（变动前后的权重、集中度、加权回撤估计）。
    changes 每项给 fund_code，加 target_pct(目标占比 0-100) 或 amount(增减金额，可为负)。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool("simulate_portfolio_change", {"changes": changes}, h, nd, nh, pf)


@mcp.tool()
async def check_profile_constraint(changes: list[dict] | None = None) -> str:
    """Check current (or proposed) portfolio against the user's risk profile.
    按风险画像逐条校验当前持仓，或校验一组拟议变动之后的状态。
    返回是否通过、违反了哪几条、检查了哪几项。给仓位建议前应先调用本工具。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool("check_profile_constraint", {"changes": changes}, h, nd, nh, pf)


@mcp.tool()
async def compute_position_sizing(fund_code: str) -> str:
    """Max position for a fund without breaching the drawdown tolerance.
    在不突破用户回撤容忍度的前提下，该基金最多能占多少比例，以及相对当前还有多少空间。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool("compute_position_sizing", {"fund_code": fund_code}, h, nd, nh, pf)


# ═══════════════════════════════════════════════════════════
# Look-through / Backtest Tools（QuantAgent 同款）
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def lookthrough_portfolio() -> str:
    """Look through funds to stock-level exposure across the portfolio.
    把组合穿透到个股层：汇总各基金重仓股的真实暴露，找出被多只基金同时重仓的个股。
    净值相关性只说明"同涨同跌"，穿透才能解释"为什么"。
    注意：季报只披露前十大且滞后 1-3 个月，返回的 report_date 必须一并转述。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool("lookthrough_portfolio", {}, h, nd, nh, pf)


@mcp.tool()
async def compute_stock_overlap(fund_code_a: str, fund_code_b: str) -> str:
    """Compare top holdings overlap between two funds.
    对比两只基金的重仓股重叠：共有几只、合计权重多少、分别是哪些。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool(
        "compute_stock_overlap",
        {"fund_code_a": fund_code_a, "fund_code_b": fund_code_b}, h, nd, nh, pf,
    )


@mcp.tool()
async def backtest_rule(
    fund_code: str, triggers: list[dict],
    stop_loss_pct: float | None = None, days: int = 250,
) -> str:
    """Backtest a staged-buy rule against lump-sum and DCA baselines.
    回测一条分批建仓规则，并与"一次性买入""等额定投"两个基线对比。
    triggers 每项形如 {"drawdown_pct": 5, "add_pct": 30}，每档只触发一次。
    给出任何分批加仓/止损规则之前应先用本工具验证其历史表现。"""
    h, nd, nh, pf = await _ensure_context()
    return await execute_tool(
        "backtest_rule",
        {"fund_code": fund_code, "triggers": triggers,
         "stop_loss_pct": stop_loss_pct, "days": days}, h, nd, nh, pf,
    )


# ═══════════════════════════════════════════════════════════
# Stock Tools（A 股个股 / ETF，无需持仓）
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def get_stock_quote(code: str) -> str:
    """Real-time quote for an A-share stock or ETF: price, change, turnover, market cap.
    个股 / ETF 实时行情：现价、涨跌幅、成交额、换手率、总市值。code 示例: 600519"""
    return await execute_tool("get_stock_quote", {"code": code}, [], {}, None)


@mcp.tool()
async def get_stock_kline(code: str, days: int = 60) -> str:
    """Daily K-line summary (forward-adjusted): period return, high/low, position in range.
    近 N 个交易日前复权日线摘要：区间涨跌幅、高低点、当前价在区间内的位置。"""
    return await execute_tool("get_stock_kline", {"code": code, "days": days}, [], {}, None)


@mcp.tool()
async def get_stock_valuation(code: str) -> str:
    """Valuation: PE(TTM), PB, market cap, and where price sits in its 1-year range.
    个股估值：PE(TTM)、PB、总市值，以及当前价在近一年价格区间的位置（是价格分位，不是估值分位）。"""
    return await execute_tool("get_stock_valuation", {"code": code}, [], {}, None)


@mcp.tool()
async def get_stock_financials(code: str, periods: int = 4) -> str:
    """Recent earnings reports: revenue, net profit, YoY, ROE, EPS, gross margin.
    最近几期业绩：营收、归母净利润及同比、ROE、每股收益、毛利率。引用时须转述报告期。"""
    return await execute_tool("get_stock_financials", {"code": code, "periods": periods}, [], {}, None)


@mcp.tool()
async def get_stock_profile(code: str) -> str:
    """Company profile: industry, region, market cap.
    个股所属行业、地域板块与市值。"""
    return await execute_tool("get_stock_profile", {"code": code}, [], {}, None)


# ═══════════════════════════════════════════════════════════
# Research Tools（证券解析、估值分位、财务指标、同行、选股）
# ═══════════════════════════════════════════════════════════

@mcp.tool()
async def resolve_security(query: str) -> str:
    """Resolve a security name or code to its exact code and type (stock / etf / fund).
    把证券名称、简称或代码解析成确定的代码与类型。不确定代码时先调用它。"""
    return await execute_tool("resolve_security", {"query": query}, [], {}, None)


@mcp.tool()
async def get_financial_indicators(code: str, periods: int = 8) -> str:
    """Multi-period financial indicators: revenue, profit, ROE, margins, debt ratio, cash flow.
    个股多期主要财务指标：营收与净利润及同比、ROE、毛利率、净利率、负债率、每股经营现金流。"""
    return await execute_tool("get_financial_indicators", {"code": code, "periods": periods}, [], {}, None)


@mcp.tool()
async def get_dividend_history(code: str) -> str:
    """Dividend history: cash per 10 shares, yield, ex-dividend date.
    个股历史分红：每 10 股派现、股息率、除权除息日。"""
    return await execute_tool("get_dividend_history", {"code": code}, [], {}, None)


@mcp.tool()
async def get_valuation_history(code: str, years: int = 5) -> str:
    """Historical percentile of PE(TTM) / PB / PS over the past N years.
    个股 PE / PB / PS 的历史分位：当前值处在过去 N 年自身估值区间的什么位置。"""
    return await execute_tool("get_valuation_history", {"code": code, "years": years}, [], {}, None)


@mcp.tool()
async def compare_peers_valuation(code: str) -> str:
    """Compare a stock's PE / PB with its industry peers.
    个股估值与同行业公司对比：行业 PE 中位数、行业内估值排位、主要同行估值。"""
    return await execute_tool("compare_peers_valuation", {"code": code}, [], {}, None)


@mcp.tool()
async def get_technical_indicators(code: str) -> str:
    """Moving averages (MA5/20/60), deviation, alignment, 20-day annualized volatility.
    个股均线、现价相对均线的偏离、均线排列、20 日年化波动率。"""
    return await execute_tool("get_technical_indicators", {"code": code}, [], {}, None)


@mcp.tool()
async def get_industry_peers(code: str) -> str:
    """Industry, market-cap rank, and main peers of a stock.
    个股所属行业、行业内市值排名与主要同行。"""
    return await execute_tool("get_industry_peers", {"code": code}, [], {}, None)


@mcp.tool()
async def get_stock_announcements(code: str, limit: int = 10) -> str:
    """Recent company announcement titles and dates.
    个股最近的公告标题与日期（不含正文）。"""
    return await execute_tool("get_stock_announcements", {"code": code, "limit": limit}, [], {}, None)


@mcp.tool()
async def get_sector_ranking(top: int = 8) -> str:
    """Today's industry ranking by median change of constituents.
    当日各行业涨跌排行（按成分股涨跌幅中位数）。"""
    return await execute_tool("get_sector_ranking", {"top": top}, [], {}, None)


@mcp.tool()
async def get_market_overview() -> str:
    """A-share market overview: indices, advancers / decliners, median change.
    A 股当日市场概况：主要指数、涨跌家数、涨跌幅中位数、涨停跌停家数。"""
    return await execute_tool("get_market_overview", {}, [], {}, None)


@mcp.tool()
async def screen_stocks(
    industry: str = "", mv_min_yi: float | None = None, mv_max_yi: float | None = None,
    pe_max: float | None = None, pb_max: float | None = None, roe_min: float | None = None,
    revenue_yoy_min: float | None = None, profit_yoy_min: float | None = None,
    sort_by: str = "total_mv_yi", descending: bool = True, limit: int = 20,
) -> str:
    """Screen all A-shares by industry, market cap, PE/PB, ROE and growth.
    按条件在全部 A 股里筛选：行业、市值、PE/PB、ROE、营收与净利增速。结果由程序确定性地筛出。"""
    criteria = {k: v for k, v in {
        "industry": industry, "mv_min_yi": mv_min_yi, "mv_max_yi": mv_max_yi, "pe_max": pe_max, "pb_max": pb_max,
        "roe_min": roe_min, "revenue_yoy_min": revenue_yoy_min, "profit_yoy_min": profit_yoy_min,
        "sort_by": sort_by, "descending": descending, "limit": limit,
    }.items() if v not in (None, "")}
    return await execute_tool("screen_stocks", criteria, [], {}, None)


@mcp.tool()
async def read_latest_report(code: str, topics: list[str] | None = None) -> str:
    """Read key sections of a stock's latest periodic report (MD&A, segments, reasons for change, risks, outlook).
    读取个股最新定期报告正文的关键章节摘录。topics 可选：管理层讨论 / 主营构成 / 业绩变动原因 / 风险 / 展望。"""
    return await execute_tool("read_latest_report", {"code": code, "topics": topics}, [], {}, None)


@mcp.tool()
async def read_announcement(art_code: str, keyword: str = "", page: int = 1) -> str:
    """Read the body of one announcement (art_code from get_stock_announcements).
    读取一条公告的正文。给 keyword 则返回该词附近的片段，否则按页返回。"""
    return await execute_tool("read_announcement", {"art_code": art_code, "keyword": keyword, "page": page}, [], {}, None)


@mcp.tool()
async def backtest_screen(criteria: dict, top_n: int = 20, years: float = 2) -> str:
    """Backtest a set of screening criteria over ~2 years against the CSI 300 ETF.
    把一组选股条件放回历史验证：每个调仓日按当时已披露的数据筛选，等权持有，与沪深300ETF 比较。"""
    return await execute_tool("backtest_screen", {"criteria": criteria, "top_n": top_n, "years": years}, [], {}, None)


@mcp.tool()
async def get_research_track_record() -> str:
    """Track record of past research: checkpoints held / broken / pending and the hold rate.
    此前研究的事后验证成绩单：验证点成立 / 被证伪 / 待核对的数量与成立率。"""
    return await execute_tool("get_research_track_record", {}, [], {}, None)


@mcp.tool()
async def list_checkpoints(code: str = "", status: str = "") -> str:
    """List checkpoints set by past research with their verification results.
    列出此前研究设下的验证点及核对结果。code 可选（如 600519），status 可选（pending / held / broken）。"""
    return await execute_tool("list_checkpoints", {"code": code, "status": status}, [], {}, None)


# ── 资金与筹码、预期与消息 ──────────────────────────────

@mcp.tool()
async def get_capital_flow(code: str) -> str:
    """Net capital flow over 5/10/20 trading days, breakdown by order size, main-force cost.
    个股资金流向：近 5 / 10 / 20 日累计净流入、按单子大小的拆分、主力持仓成本。"""
    return await execute_tool("get_capital_flow", {"code": code}, [], {}, None)


@mcp.tool()
async def get_margin_trading(code: str) -> str:
    """Margin financing balance and its recent change.
    个股融资融券：融资余额及 5 / 20 / 60 日变化、融券余额、占流通市值的比例。"""
    return await execute_tool("get_margin_trading", {"code": code}, [], {}, None)


@mcp.tool()
async def get_shareholder_structure(code: str) -> str:
    """Holder count history, top-10 float holders, institutional and northbound holdings.
    筹码结构：股东户数变化、十大流通股东、各类机构持仓、北向持股。"""
    return await execute_tool("get_shareholder_structure", {"code": code}, [], {}, None)


@mcp.tool()
async def get_insider_activity(code: str) -> str:
    """Insider buys/sells, buybacks in the last two years and share unlocks in the next year.
    近两年股东与董监高增减持、回购，以及未来一年的限售股解禁。"""
    return await execute_tool("get_insider_activity", {"code": code}, [], {}, None)


@mcp.tool()
async def get_large_trades(code: str) -> str:
    """Recent block trades (premium/discount) and dragon-tiger list appearances.
    近期大宗交易（折溢价、买卖方）与龙虎榜上榜记录。"""
    return await execute_tool("get_large_trades", {"code": code}, [], {}, None)


@mcp.tool()
async def get_consensus_forecast(code: str) -> str:
    """Sell-side consensus: coverage, rating distribution, EPS forecasts, forward P/E, broker target range.
    卖方一致预期：覆盖机构数、评级分布、未来几年 EPS 预测与预期市盈率、券商目标价区间。"""
    return await execute_tool("get_consensus_forecast", {"code": code}, [], {}, None)


@mcp.tool()
async def get_research_reports(code: str, limit: int = 8) -> str:
    """Sell-side research reports from the last six months.
    近半年的卖方研报：机构、标题、评级及评级变化、EPS 预测。"""
    return await execute_tool("get_research_reports", {"code": code, "limit": limit}, [], {}, None)


@mcp.tool()
async def get_earnings_guidance(code: str) -> str:
    """The company's own latest earnings forecast and preliminary results.
    公司最近一次业绩预告与业绩快报。"""
    return await execute_tool("get_earnings_guidance", {"code": code}, [], {}, None)


@mcp.tool()
async def get_stock_news(code: str, limit: int = 8) -> str:
    """Recent news about one stock: title, summary, outlet, time.
    个股最近的新闻：标题、摘要、媒体、时间。"""
    return await execute_tool("get_stock_news", {"code": code, "limit": limit}, [], {}, None)


@mcp.tool()
async def get_investor_surveys(code: str) -> str:
    """Recent institutional surveys and earnings calls with the opening of the Q&A.
    最近的机构调研与业绩说明会纪要。"""
    return await execute_tool("get_investor_surveys", {"code": code}, [], {}, None)


@mcp.tool()
async def get_business_segments(code: str) -> str:
    """Revenue mix by product, region and industry with gross margins.
    主营构成：按产品、地区、行业拆分的收入占比与毛利率。"""
    return await execute_tool("get_business_segments", {"code": code}, [], {}, None)


@mcp.tool()
async def web_search(query: str, limit: int = 5) -> str:
    """Search the public web for things the fixed data sources do not cover (company events, policy texts, claims going around). Results are unverified.
    联网搜索：公司事件、政策原文、网上流传的说法。结果是没核实过的网页摘录。"""
    return await execute_tool("web_search", {"query": query, "limit": limit}, [], {}, None)


@mcp.tool()
async def read_webpage(url: str) -> str:
    """Read the main text of a public web page (first few thousand characters). Local and private-network addresses are refused.
    读一个公网网页的正文；本机和内网地址不读。"""
    return await execute_tool("read_webpage", {"url": url}, [], {}, None)


@mcp.tool()
async def get_market_recap() -> str:
    """Today's A-share market recap: indices, breadth, limit-up/limit-down counts, consecutive-limit ladder, themes with reasons, billboard seats, a rule-based mood gauge.
    今天的大盘复盘：涨停与连板、题材热点、龙虎榜、情绪刻度。"""
    return await execute_tool("get_market_recap", {}, [], {}, None)


@mcp.tool()
async def get_macro_indicators() -> str:
    """China macro indicators: PMI, CPI, PPI, M1/M2, new loans, GDP, LPR, China and US treasury yields.
    宏观数据：景气、物价、货币信贷、利率。"""
    return await execute_tool("get_macro_indicators", {}, [], {}, None)


@mcp.tool()
async def get_concept_boards(top: int = 10) -> str:
    """Concept boards ranked by today's change, with stock counts and leaders.
    概念板块今天的强弱。"""
    return await execute_tool("get_concept_boards", {"top": top}, [], {}, None)


@mcp.tool()
async def get_concept_stocks(name: str, limit: int = 30) -> str:
    """Constituents of a concept board (by today's change), with market cap, PE and turnover.
    一个概念板块里有哪些股票。"""
    return await execute_tool("get_concept_stocks", {"name": name, "limit": limit}, [], {}, None)


@mcp.tool()
async def compute_reverse_dcf(code: str) -> str:
    """Reverse DCF: the profit growth the current market cap implies, next to the past three-year growth. Not a price target.
    反向 DCF：现价隐含了多高的利润增速。不是目标价。"""
    return await execute_tool("compute_reverse_dcf", {"code": code}, [], {}, None)


@mcp.tool()
async def compare_stocks(codes: list[str]) -> str:
    """Compare 2-6 stocks you name side by side (A-share, HK and US can be mixed): market cap, PE, PB, 5-year percentiles, latest growth and margins.
    把点名的几只股票放在一张表里比，A 股、港股、美股可以混着比。比谁由你决定。"""
    return await execute_tool("compare_stocks", {"codes": codes}, [], {}, None)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
