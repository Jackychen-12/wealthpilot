"""Agent 工具定义 + 统一执行器。"""

import asyncio
import json

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services import filings, screener
from wealthpilot.services.agents import depth_tools, insight_tools, web_tools
from wealthpilot.services.analysis import (
    calculate_attribution_by_fund,
    calculate_correlation,
    calculate_drawdown,
    calculate_health,
    calculate_max_drawdown,
    calculate_overview,
    generate_suggestions,
)
from wealthpilot.services.assets import fetch_price_history
from wealthpilot.services.backtest import backtest_rule
from wealthpilot.services.lookthrough import (
    aggregate_exposure,
    fetch_fund_holdings,
    overlap_between,
    summarize_overlap,
)
from wealthpilot.services.market_data import (
    fetch_fund_info,
    fetch_fund_nav,
    fetch_indices,
    fetch_market_news,
    get_comprehensive_fund_info,
)
from wealthpilot.services.securities import search as search_securities
from wealthpilot.services.simulation import (
    check_constraints,
    concentration_metrics,
    max_position_within_drawdown,
    portfolio_weights,
    simulate_change,
)
from wealthpilot.services.stocks import (
    fetch_dividends,
    fetch_financial_indicators,
    fetch_industry_peers,
    fetch_stock_financials,
    fetch_stock_kline,
    fetch_stock_profile,
    fetch_stock_quote,
    fetch_valuation_history,
    summarize_kline,
    summarize_technicals,
    summarize_valuation,
)

# ═══════════════════════════════════════════════════════════
# MarketAgent 工具
# ═══════════════════════════════════════════════════════════

MARKET_TOOLS = [
    {
        "name": "get_fund_info",
        "description": "查询某只基金的基本信息（名称、最新净值、估值、类型等）。当用户问某只基金的情况时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {
                    "type": "string",
                    "description": "基金代码，如 007340、110011",
                }
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "get_nav_history",
        "description": "查询某只基金近 N 个交易日的净值历史数据（日期、净值、日涨跌幅）。用于分析走势和计算收益。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "交易日数，默认30", "default": 30},
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "search_market_news",
        "description": "获取最新财经要闻。用于回答市场动态相关问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词（可选）", "default": ""},
            },
        },
    },
]

# ═══════════════════════════════════════════════════════════
# PortfolioAgent 工具
# ═══════════════════════════════════════════════════════════

PORTFOLIO_TOOLS = [
    {
        "name": "get_portfolio_overview",
        "description": "计算用户持仓总览：总市值、总收益、周收益、Sharpe 比率等。用于回答'我的持仓怎么样'类问题。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_attribution",
        "description": "按基金维度计算收益归因。用于回答'哪只基金贡献最大/最差'。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_health_score",
        "description": "计算组合健康度 5 维评分（收益表现、波动控制、分散度、风格匹配、风险收益比）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_investment_suggestions",
        "description": "基于规则引擎生成投资建议（集中度、亏损、相关性、类别均衡检查）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ═══════════════════════════════════════════════════════════
# RiskAgent 工具
# ═══════════════════════════════════════════════════════════

RISK_TOOLS = [
    {
        "name": "calculate_return",
        "description": "计算某只基金在最近 N 个交易日内的累计收益率。用于回答'近1周/1月/3月表现如何'。",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
                "days": {"type": "integer", "description": "区间交易日数（5≈近1周, 21≈近1月, 63≈近3月）"},
            },
            "required": ["fund_code", "days"],
        },
    },
    {
        "name": "compare_funds",
        "description": "对比多只基金的近期表现（净值、涨跌幅）。用于回答'哪只基金更好'类问题。",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要对比的基金代码列表（2-5只）",
                }
            },
            "required": ["fund_codes"],
        },
    },
    {
        "name": "get_drawdown_analysis",
        "description": "分析持仓中每只基金的回撤情况（当前跌幅、最大回撤、恢复天数）。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_max_drawdown",
        "description": "计算某只基金的最大回撤 + 恢复天数。",
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
            },
            "required": ["fund_code"],
        },
    },
    {
        "name": "get_correlation_matrix",
        "description": "计算持仓基金之间的相关性矩阵。用于评估分散化程度。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ═══════════════════════════════════════════════════════════
# 计算 / 校验工具（确定性，不让模型自己算）
#
# 取数工具回答"是什么"，这组回答"如果……会怎样"和"这样行不行"。
# 目的是让最终答案里的每个数字都能追溯到某次工具返回。
# ═══════════════════════════════════════════════════════════

COMPUTE_TOOLS = [
    {
        "name": "compute_concentration",
        "description": (
            "计算当前持仓的集中度：各基金权重、最大单一权重、HHI 指数、有效持仓数。"
            "需要引用任何占比数字时调用本工具，不要自己按市值心算。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate_portfolio_change",
        "description": (
            "推演一组仓位变动后的组合指标，返回变动前后的权重、集中度与加权回撤估计。"
            "回答'加仓到 X% 会怎样''减掉 Y 元之后呢'这类问题时必须调用本工具，"
            "不要自行推算变动后的占比。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "description": "变动列表。每项给 target_pct(目标占比 0-100) 或 amount(增减金额，可为负)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fund_code": {"type": "string", "description": "基金代码"},
                            "target_pct": {"type": "number", "description": "目标占比（0-100）"},
                            "amount": {"type": "number", "description": "增减金额，负数为减仓"},
                        },
                        "required": ["fund_code"],
                    },
                }
            },
            "required": ["changes"],
        },
    },
    {
        "name": "check_profile_constraint",
        "description": (
            "按用户风险画像逐条校验当前持仓，或校验一组拟议变动之后的状态。"
            "返回是否通过、违反了哪几条、检查了哪几项。"
            "给出任何仓位相关建议之前必须先调用本工具确认不越界。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "array",
                    "description": "可选。要校验的拟议变动，格式同 simulate_portfolio_change；不传则校验当前持仓",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fund_code": {"type": "string"},
                            "target_pct": {"type": "number"},
                            "amount": {"type": "number"},
                        },
                        "required": ["fund_code"],
                    },
                }
            },
        },
    },
    {
        "name": "compute_position_sizing",
        "description": (
            "在不突破用户回撤容忍度的前提下，计算某只基金最多能占多少比例，"
            "并给出相对当前仓位还有多少空间。用户问'还能加多少'时调用本工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code": {"type": "string", "description": "基金代码"},
            },
            "required": ["fund_code"],
        },
    },
]


# ═══════════════════════════════════════════════════════════
# 穿透 / 回测工具（QuantAgent）
# ═══════════════════════════════════════════════════════════

QUANT_TOOLS = [
    {
        "name": "lookthrough_portfolio",
        "description": (
            "把组合穿透到个股层：汇总各基金重仓股的真实暴露，找出被多只基金"
            "同时重仓的个股。净值相关性只说明'同涨同跌'，穿透才能解释'为什么'。"
            "回答分散度、重叠、真实行业暴露类问题时调用。"
            "注意：季报只披露前十大且滞后 1-3 个月，结果里带 report_date 必须转述。"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compute_stock_overlap",
        "description": (
            "对比两只基金的重仓股重叠：共有几只、合计权重多少、分别是哪些。"
            "用于回答'这两只基金是不是买的差不多'。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_code_a": {"type": "string", "description": "基金代码 A"},
                "fund_code_b": {"type": "string", "description": "基金代码 B"},
            },
            "required": ["fund_code_a", "fund_code_b"],
        },
    },
    {
        "name": "backtest_rule",
        "description": (
            "回测一条分批建仓规则，并与'一次性买入''等额定投'两个基线对比。"
            "**给出任何分批加仓/止损规则之前，必须先用本工具验证它的历史表现**，"
            "不要凭空给出未经检验的规则。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {
                    "type": "string", "enum": ["fund", "stock", "etf"],
                    "description": "标的类型。不填时：在用户持仓里的按持仓记录判断，否则按基金处理。查个股必须填 stock",
                },
                "fund_code": {"type": "string", "description": "基金代码"},
                "triggers": {
                    "type": "array",
                    "description": "触发档位，每档只触发一次",
                    "items": {
                        "type": "object",
                        "properties": {
                            "drawdown_pct": {"type": "number", "description": "自高点回调达到该比例时触发"},
                            "add_pct": {"type": "number", "description": "投入总资金的百分比"},
                        },
                        "required": ["drawdown_pct", "add_pct"],
                    },
                },
                "stop_loss_pct": {"type": "number", "description": "可选。相对持仓成本跌破该比例则清仓"},
                "days": {"type": "integer", "description": "回测使用的历史交易日数，默认 250"},
            },
            "required": ["fund_code", "triggers"],
        },
    },
]


# ═══════════════════════════════════════════════════════════
# StockAgent 工具 —— A 股个股 / ETF
# ═══════════════════════════════════════════════════════════

_STOCK_CODE = {"type": "string", "description": "A 股代码，如 600519、000858、510300（可带 sh/sz 前缀）"}

STOCK_TOOLS = [
    {
        "name": "get_stock_quote",
        "description": "查询个股或 ETF 的实时行情：现价、涨跌幅、成交额、换手率、总市值。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_stock_kline",
        "description": (
            "查询个股或 ETF 最近 N 个交易日的前复权日线摘要：区间涨跌幅、区间高低点、"
            "当前价在区间内的位置，以及最近几日收盘。用于回答'近期走势如何''现在在高位还是低位'。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": _STOCK_CODE,
                           "days": {"type": "integer", "description": "交易日数，默认 60（21≈1月，250≈1年）"}},
            "required": ["code"],
        },
    },
    {
        "name": "get_stock_valuation",
        "description": (
            "查询个股估值：PE(TTM)、PB、总市值，以及当前价在近一年价格区间里的位置。"
            "注意返回的是**价格**分位而不是估值分位——没有历史 PE 序列，不要把它说成'PE 处于历史 xx 分位'。"
        ),
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_stock_financials",
        "description": (
            "查询个股最近几期业绩：营收、归母净利润及同比、ROE、每股收益、毛利率。"
            "每条都带 report_date（报告期），引用时必须转述报告期——财报是滞后数据，不代表现状。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": _STOCK_CODE,
                           "periods": {"type": "integer", "description": "取最近几期，默认 4"}},
            "required": ["code"],
        },
    },
    {
        "name": "get_stock_profile",
        "description": "查询个股的所属行业、地域板块与市值。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
]


RESEARCH_TOOLS = [
    {
        "name": "resolve_security",
        "description": (
            "把证券名称、简称或代码解析成确定的代码与类型（股票 / ETF / 基金）。"
            "**遇到任务上下文里没有给出代码的证券，必须先调用本工具，不得凭记忆写代码。**"
        ),
        "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "名称、简称或代码，如 茅台、宁德时代、510300"}}, "required": ["query"]},
    },
    {
        "name": "get_financial_indicators",
        "description": (
            "查询个股多期主要财务指标：营收与净利润及同比、扣非净利润、ROE、毛利率、净利率、资产负债率、"
            "每股经营现金流。用于判断盈利质量、成长性与杠杆。每条带 report_date，引用时必须转述报告期。"
        ),
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE, "periods": {"type": "integer", "description": "取最近几期，默认 8"}}, "required": ["code"]},
    },
    {
        "name": "get_dividend_history",
        "description": "查询个股历史分红：每 10 股派现、股息率、除权除息日。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_valuation_history",
        "description": (
            "查询个股 PE(TTM) / PB / PS 的**历史分位**：当前值处在过去 N 年自身估值区间的什么位置，"
            "以及区间的最低、中位、最高。这是判断'相对自己历史贵不贵'的依据。"
        ),
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE, "years": {"type": "integer", "description": "回看年数，默认 5，最多 8"}}, "required": ["code"]},
    },
    {
        "name": "compare_peers_valuation",
        "description": "把个股的 PE / PB 与同行业公司对比：行业 PE 中位数、该股在行业内的估值排位、主要同行的估值。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_technical_indicators",
        "description": "计算个股的均线（MA5/20/60）、现价相对均线的偏离、均线排列、20 日年化波动率。只描述已发生的走势。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_industry_peers",
        "description": "查询个股所属行业、行业内公司数量、该股的市值排名，以及按市值排序的主要同行（含当日涨跌幅）。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE}, "required": ["code"]},
    },
    {
        "name": "get_stock_announcements",
        "description": "查询个股最近的公告：标题、日期、类别与 art_code。要看某条公告的正文，把 art_code 交给 read_announcement。",
        "input_schema": {"type": "object", "properties": {"code": _STOCK_CODE, "limit": {"type": "integer", "description": "条数，默认 10"}}, "required": ["code"]},
    },
    {
        "name": "get_sector_ranking",
        "description": "查询当日各行业涨跌排行（按成分股涨跌幅中位数），返回领涨与领跌的行业及各自的领涨股。",
        "input_schema": {"type": "object", "properties": {"top": {"type": "integer", "description": "领涨、领跌各取几个，默认 8"}}},
    },
    {
        "name": "get_market_overview",
        "description": "查询 A 股当日市场概况：主要指数、上涨 / 下跌家数、涨跌幅中位数、涨停跌停家数。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "screen_stocks",
        "description": (
            "按条件在全部 A 股里筛选。条件都是可选的，按需填写；结果由程序确定性地筛出，"
            "不要自己凭印象列股票。返回匹配总数与排序后的前若干只。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "industry": {"type": "string", "description": "行业名称关键词，如 白酒、银行、半导体"},
                "mv_min_yi": {"type": "number", "description": "总市值下限（亿元）"},
                "mv_max_yi": {"type": "number", "description": "总市值上限（亿元）"},
                "pe_min": {"type": "number"}, "pe_max": {"type": "number", "description": "PE(TTM) 上限；设置后自动排除亏损股"},
                "pb_max": {"type": "number"},
                "roe_min": {"type": "number", "description": "ROE 下限（%），取自最近一期业绩"},
                "revenue_yoy_min": {"type": "number", "description": "营收同比下限（%）"},
                "profit_yoy_min": {"type": "number", "description": "净利润同比下限（%）"},
                "change_min": {"type": "number", "description": "当日涨跌幅下限（%）"},
                "change_max": {"type": "number", "description": "当日涨跌幅上限（%）"},
                "sort_by": {"type": "string", "enum": list(screener.SORT_KEYS), "description": "排序字段，默认按总市值"},
                "descending": {"type": "boolean", "description": "是否降序，默认 true"},
                "limit": {"type": "integer", "description": "返回条数，默认 20，最多 100"},
            },
        },
    },
]

FILING_TOOLS = [
    {
        "name": "read_latest_report",
        "description": (
            "读取个股最新一份定期报告（年报 / 半年报 / 季报）正文里的关键章节摘录：管理层讨论、主营构成、业绩变动原因、风险、展望。"
            "用来回答“公司自己怎么解释这期业绩”“管理层提示了哪些风险”。摘录是原文片段，引用时要说明出自哪份报告。"
        ),
        "input_schema": {"type": "object", "properties": {
            "code": _STOCK_CODE,
            "topics": {"type": "array", "items": {"type": "string", "enum": ["管理层讨论", "主营构成", "业绩变动原因", "风险", "展望"]},
                       "description": "要读哪些章节；不填读全部"},
        }, "required": ["code"]},
    },
    {
        "name": "read_announcement",
        "description": "读取一条公告的正文。art_code 来自 get_stock_announcements。给 keyword 则返回该词附近的片段，否则按页返回（每页约 4000 字）。",
        "input_schema": {"type": "object", "properties": {
            "art_code": {"type": "string", "description": "公告编号，如 AN202608141827994408"},
            "keyword": {"type": "string", "description": "只看包含这个词的片段，如 减持、回购、业绩"},
            "page": {"type": "integer", "description": "第几页，默认 1"},
        }, "required": ["art_code"]},
    },
    {
        "name": "backtest_screen",
        "description": (
            "把一组选股条件放回历史验证：每个调仓日（每年 5、9、11 月初）按当时已披露的数据筛出前 top_n 只，等权持有到下一个调仓日，"
            "与沪深300ETF 比较。条件字段与 screen_stocks 相同。返回每期收益、累计与年化收益、超额、最大回撤和局限说明。"
            "历史只有约两年，持有期很少——引用结果时必须同时转述 limitations。"
        ),
        "input_schema": {"type": "object", "properties": {
            "criteria": {"type": "object", "description": "与 screen_stocks 相同的筛选条件，如 {\"pe_max\":15,\"roe_min\":15}"},
            "top_n": {"type": "integer", "description": "每期持有几只，默认 20"},
            "years": {"type": "number", "description": "回测几年，默认 2，最多 2.5"},
        }, "required": ["criteria"]},
    },
]

REVIEW_TOOLS = [
    {
        "name": "get_research_track_record",
        "description": "查询此前研究的事后验证成绩单：验证点总数、已成立 / 被证伪 / 待核对的数量、成立率，按类别（财务 / 估值 / 涨跌）和按股票的分布，以及最近核对出结果的条目。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_checkpoints",
        "description": "列出此前研究设下的验证点及核对结果。每条包含：股票、指标、条件、设定时的值与日期、状态（pending 待核对 / held 成立 / broken 被证伪）、实际值与日期、出自哪个问题。",
        "input_schema": {"type": "object", "properties": {
            "code": {"type": "string", "description": "只看某只股票，如 600519；不填看全部"},
            "status": {"type": "string", "enum": ["pending", "held", "broken"], "description": "只看某种状态；不填看全部"},
        }},
    },
]

_ALL_TOOLS = {t["name"]: t for t in [*MARKET_TOOLS, *PORTFOLIO_TOOLS, *RISK_TOOLS, *COMPUTE_TOOLS,
                                     *QUANT_TOOLS, *STOCK_TOOLS, *RESEARCH_TOOLS, *REVIEW_TOOLS, *FILING_TOOLS,
                                     *insight_tools.INSIGHT_TOOLS, *web_tools.WEB_TOOLS, *depth_tools.DEPTH_TOOLS]}


def _pick(*names: str) -> list[dict]:
    return [_ALL_TOOLS[n] for n in names]


# 按研究维度分组 —— 每个 Agent 拿到的就是这里的一组。同一个工具可以出现在多个组里。
AGENT_TOOLS: dict[str, list[dict]] = {
    "fundamental": _pick("resolve_security", "get_stock_profile", "get_stock_financials",
                         "get_financial_indicators", "get_business_segments", "get_dividend_history", "read_latest_report"),
    "valuation": _pick("resolve_security", "get_stock_valuation", "get_valuation_history", "compare_peers_valuation", "compute_reverse_dcf"),
    "price": _pick("resolve_security", "get_stock_quote", "get_stock_kline", "get_technical_indicators",
                   "calculate_return", "get_max_drawdown", "backtest_rule"),
    "industry": _pick("resolve_security", "get_industry_peers", "get_sector_ranking", "get_stock_announcements",
                      "read_announcement", "search_market_news", "get_stock_news", "get_market_overview", "web_search", "read_webpage",
                      "get_market_recap", "get_macro_indicators", "get_concept_boards", "get_concept_stocks"),
    # 资金与筹码：钱往哪走、票在谁手里、内部人在干什么
    "capital": _pick("resolve_security", *insight_tools.CAPITAL),
    # 预期与消息：卖方怎么看、公司怎么预告、最近有什么新闻
    "expectation": _pick("resolve_security", *insight_tools.EXPECTATION, "web_search", "read_webpage"),
    "screener": _pick("screen_stocks", "get_sector_ranking", "backtest_screen"),
    "portfolio": _pick("get_portfolio_overview", "get_attribution", "get_health_score", "get_investment_suggestions",
                       "get_drawdown_analysis", "get_correlation_matrix", "lookthrough_portfolio",
                       "compute_concentration", "simulate_portfolio_change", "check_profile_constraint",
                       "compute_position_sizing"),
    "review": REVIEW_TOOLS,
    "fund": _pick("resolve_security", "get_fund_info", "get_nav_history", "compare_funds",
                  "compute_stock_overlap", "calculate_return", "get_max_drawdown", "backtest_rule"),
}


def _asset_type_of(code: str, input_data: dict, holdings: list[PortfolioHolding]) -> str:
    """工具入参没指明类型时：持仓里有就按持仓记录，否则按基金。"""
    explicit = input_data.get("asset_type")
    if explicit:
        return str(explicit).lower()
    return next((h.asset_type or "fund" for h in holdings if h.fund_code == code), "fund")


async def execute_tool(
    name: str,
    input_data: dict,
    holdings: list[PortfolioHolding],
    nav_data: dict[str, float],
    nav_history: dict[str, list[dict]] | None = None,
    profile: InvestorProfile | None = None,
) -> str:
    """统一工具执行器。"""
    if name in insight_tools.NAMES:
        return await insight_tools.execute(name, input_data)
    if name in web_tools.NAMES:
        return await web_tools.execute(name, input_data)
    if name in depth_tools.NAMES:
        return await depth_tools.execute(name, input_data)
    # === 事后复盘 ===
    if name in ("get_research_track_record", "list_checkpoints"):
        from sqlmodel import Session

        from wealthpilot.services import checkpoints
        from wealthpilot.storage.db import get_engine
        with Session(get_engine()) as db:
            uid = checkpoints.active_user()
            if name == "get_research_track_record":
                card = checkpoints.scorecard(db, uid)
                if not card["total"]:
                    return "还没有任何验证点：做过带具体股票的研究之后才会有"
                return json.dumps(card, ensure_ascii=False)
            rows = checkpoints.list_checkpoints(db, uid, code=str(input_data.get("code") or ""),
                                                status=str(input_data.get("status") or ""), limit=40)
            if not rows:
                return "没有符合条件的验证点"
            return json.dumps({"count": len(rows), "checkpoints": [checkpoints.serialize(c) for c in rows]}, ensure_ascii=False)
    # === 证券解析 / 研究工具 ===
    if name == "resolve_security":
        hits = await search_securities(str(input_data["query"]), 5)
        if not hits:
            return f"未找到与「{input_data['query']}」匹配的 A 股、ETF 或基金"
        return json.dumps({"query": input_data["query"], "matches": hits,
                           "note": "matches 按相关度排序；asset_type 为 stock / etf / fund"}, ensure_ascii=False)

    if name == "get_financial_indicators":
        rows = await fetch_financial_indicators(input_data["code"], int(input_data.get("periods", 8)))
        if not rows:
            return f"未获取到 {input_data['code']} 的财务指标"
        return json.dumps({"code": input_data["code"], "reports": rows,
                           "note": "金额单位亿元；非年报的各期为年初至该期末的累计值；同比为相对上年同期"},
                          ensure_ascii=False)

    if name == "get_dividend_history":
        rows = await fetch_dividends(input_data["code"])
        if not rows:
            return f"未获取到 {input_data['code']} 的分红记录"
        return json.dumps({"code": input_data["code"], "dividends": rows}, ensure_ascii=False)

    if name == "get_valuation_history":
        years = max(1, min(int(input_data.get("years", 5)), 8))
        history = await fetch_valuation_history(input_data["code"], years)
        if not history:
            return f"未获取到 {input_data['code']} 的历史估值"
        return json.dumps({"code": input_data["code"], "name": history[0]["name"], **summarize_valuation(history),
                           "note": "percentile 为当前值在窗口内自身历史中的分位（0 最便宜，100 最贵）；"
                                   "只和自己的历史比，不代表绝对便宜或贵"}, ensure_ascii=False)

    if name in ("compare_peers_valuation", "get_industry_peers"):
        data = await fetch_industry_peers(input_data["code"])
        if not data:
            return f"未获取到 {input_data['code']} 的同行业数据"
        if name == "get_industry_peers":
            return json.dumps({k: data[k] for k in ("industry", "as_of", "peer_count", "mv_rank", "target")}
                              | {"peers": data["peers"][:15]}, ensure_ascii=False)
        ranked = sorted((p for p in data["peers"] if p["pe_ttm"] and p["pe_ttm"] > 0), key=lambda p: p["pe_ttm"])
        target = data["target"] or {}
        return json.dumps({
            "industry": data["industry"], "as_of": data["as_of"], "peer_count": data["peer_count"],
            "target": target, "industry_median_pe": data["industry_median_pe"],
            "pe_rank_low_to_high": next((i + 1 for i, p in enumerate(ranked) if p["code"] == target.get("code")), None),
            "positive_pe_peer_count": len(ranked),
            "largest_peers": [{k: p[k] for k in ("code", "name", "pe_ttm", "pb", "total_mv_yi")} for p in data["peers"][:10]],
            "note": "pe_rank_low_to_high 为该股 PE 在同行业盈利公司中由低到高的名次；亏损公司不参与排名",
        }, ensure_ascii=False)

    if name == "get_technical_indicators":
        kline = await fetch_stock_kline(input_data["code"], 120)
        if len(kline) < 20:
            return f"未获取到 {input_data['code']} 足够的日线数据"
        return json.dumps({"code": input_data["code"], **summarize_technicals(kline)}, ensure_ascii=False)

    if name == "get_stock_announcements":
        rows = await filings.list_filings(input_data["code"], int(input_data.get("limit", 10)))
        if not rows:
            return f"未获取到 {input_data['code']} 的公告"
        return json.dumps({"code": input_data["code"], "announcements": rows,
                           "note": "这里只有标题；正文用 read_announcement 读"}, ensure_ascii=False)

    if name == "read_latest_report":
        report = await filings.latest_report(input_data["code"], input_data.get("topics"))
        if not report or not report.get("sections"):
            return f"未能读取 {input_data['code']} 最新定期报告的正文"
        return json.dumps(report, ensure_ascii=False)

    if name == "read_announcement":
        doc = await filings.read(str(input_data["art_code"]), str(input_data.get("keyword") or ""), int(input_data.get("page") or 1))
        if not doc or not doc.get("text"):
            return "未能读取这条公告的正文" if not doc else f"公告正文里没有出现「{input_data.get('keyword')}」"
        return json.dumps(doc, ensure_ascii=False)

    if name == "backtest_screen":
        result = await screener.backtest_screen(dict(input_data.get("criteria") or {}), float(input_data.get("years") or 2),
                                                int(input_data.get("top_n") or 20))
        return result["error"] if "error" in result else json.dumps(result, ensure_ascii=False)

    if name in ("get_sector_ranking", "get_market_overview", "screen_stocks"):
        snap = await screener.snapshot()
        if not snap:
            return "未获取到全市场快照，暂时无法筛选或统计"
        if name == "get_sector_ranking":
            return json.dumps(screener.sector_ranking(snap, int(input_data.get("top", 8))), ensure_ascii=False)
        if name == "screen_stocks":
            return json.dumps(screener.screen(snap, input_data), ensure_ascii=False)
        return json.dumps({"indices": await fetch_indices(), "breadth": screener.market_breadth(snap)},
                          ensure_ascii=False)

    # === 个股工具 ===
    if name in ("get_stock_quote", "get_stock_valuation"):
        code = input_data["code"]
        quote = await fetch_stock_quote(code)
        if not quote:
            return f"未获取到 {code} 的行情（代码有误、已退市或处于停牌）"
        if name == "get_stock_quote":
            return json.dumps(quote, ensure_ascii=False)
        kline = await fetch_stock_kline(code, 250)
        result = {k: quote[k] for k in ("code", "name", "price", "pe_ttm", "pb", "total_mv_yi", "quote_time")}
        if kline:
            summary = summarize_kline(kline)
            result["price_range_1y"] = {k: summary[k] for k in
                                        ("period_high", "period_low", "range_position_pct", "trading_days")}
        result["note"] = ("pe_ttm 为滚动市盈率，亏损时为负或缺失；price_range_1y 是近一年**价格**所处位置，"
                          "不是估值分位；市值单位为亿元")
        return json.dumps(result, ensure_ascii=False)

    if name == "get_stock_kline":
        code = input_data["code"]
        days = max(5, min(int(input_data.get("days", 60)), 750))
        kline = await fetch_stock_kline(code, days)
        if not kline:
            return f"未获取到 {code} 的日线数据"
        recent = [{"date": r["nav_date"], "close": r["nav"], "change_pct": r["daily_return"]} for r in kline[:5]]
        return json.dumps({"code": code, **summarize_kline(kline), "recent": recent}, ensure_ascii=False)

    if name == "get_stock_financials":
        code = input_data["code"]
        rows = await fetch_stock_financials(code, int(input_data.get("periods", 4)))
        if not rows:
            return f"未获取到 {code} 的业绩报表"
        return json.dumps({"code": code, "reports": rows,
                           "note": "金额单位为亿元；同比为相对上年同期；各期为累计值（如 06-30 是上半年合计）"},
                          ensure_ascii=False)

    if name == "get_stock_profile":
        profile_data = await fetch_stock_profile(input_data["code"])
        if not profile_data:
            return f"未获取到 {input_data['code']} 的公司信息"
        return json.dumps(profile_data, ensure_ascii=False)

    # === 穿透 / 回测工具 ===
    if name == "lookthrough_portfolio":
        if not holdings:
            return "当前没有持仓，无法穿透。"
        # 只有基金有季报重仓股；直接持有的个股由 aggregate_exposure 并入
        codes = list(dict.fromkeys(h.fund_code for h in holdings if (h.asset_type or "fund") == "fund"))
        fetched = await asyncio.gather(*[fetch_fund_holdings(c) for c in codes])
        fund_holdings = dict(zip(codes, fetched, strict=True))
        result = aggregate_exposure(holdings, nav_data, fund_holdings)
        result["summary"] = summarize_overlap(result)
        return json.dumps(result, ensure_ascii=False)

    if name == "compute_stock_overlap":
        a, b = await asyncio.gather(
            fetch_fund_holdings(input_data["fund_code_a"]),
            fetch_fund_holdings(input_data["fund_code_b"]),
        )
        if not a["stocks"] or not b["stocks"]:
            missing = [c for c, d in ((a["fund_code"], a), (b["fund_code"], b)) if not d["stocks"]]
            return f"未取到以下基金的季报持仓：{'、'.join(missing)}（可能是新基金或非股票型）"
        return json.dumps(overlap_between(a, b), ensure_ascii=False)

    if name == "backtest_rule":
        code = input_data["fund_code"]
        days = max(2, min(int(input_data.get("days", 250)), 1500))
        asset_type = _asset_type_of(code, input_data, holdings)
        nav_list = (nav_history or {}).get(code, [])
        if len(nav_list) < days:
            nav_list = await fetch_price_history(code, asset_type, days)
        nav_list = sorted(nav_list, key=lambda r: r["nav_date"], reverse=True)[:days]
        if not nav_list:
            return f"未获取到 {code} 的历史价格，无法回测。"
        # A 股卖出有印花税 + 双边佣金；没指定费率时给股票一个保守的默认值
        default_fee = 0.1 if asset_type == "stock" else 0.0
        return json.dumps(
            backtest_rule(
                nav_list,
                input_data["triggers"],
                stop_loss_pct=input_data.get("stop_loss_pct"),
                fee_pct=input_data.get("fee_pct", default_fee),
                execution_lag=1,
                price_basis="forward_adjusted_close" if asset_type in ("stock", "etf") else "unit_nav_unadjusted",
            ),
            ensure_ascii=False,
        )

    # === 计算 / 校验工具 ===
    if name == "compute_concentration":
        weights = portfolio_weights(holdings, nav_data)
        if not weights:
            return "当前没有持仓，无法计算集中度。"
        return json.dumps(
            {"weights": {c: round(w, 4) for c, w in weights.items()},
             **concentration_metrics(weights)},
            ensure_ascii=False,
        )

    if name == "simulate_portfolio_change":
        changes = input_data.get("changes") or []
        if not changes:
            return "未提供变动内容，无法推演。"
        return json.dumps(
            simulate_change(holdings, nav_data, nav_history, changes), ensure_ascii=False
        )

    if name == "check_profile_constraint":
        return json.dumps(
            check_constraints(profile, holdings, nav_data, nav_history,
                              input_data.get("changes")),
            ensure_ascii=False,
        )

    if name == "compute_position_sizing":
        return json.dumps(
            max_position_within_drawdown(
                input_data["fund_code"], holdings, nav_data, nav_history, profile
            ),
            ensure_ascii=False,
        )

    # === Market 工具 ===
    if name == "get_fund_info":
        info = await get_comprehensive_fund_info(input_data["fund_code"])
        if info and info.get("name"):
            return json.dumps(info, ensure_ascii=False)
        return f"未找到基金 {input_data['fund_code']} 的信息"

    if name == "get_nav_history":
        nav_list = await fetch_fund_nav(input_data["fund_code"], input_data.get("days", 30))
        if nav_list:
            summary = f"基金 {input_data['fund_code']} 近 {len(nav_list)} 个交易日净值数据：\n"
            for item in nav_list[:5]:
                summary += f"  {item['nav_date']}: 净值{item['nav']}, 涨跌{item['daily_return']}%\n"
            if len(nav_list) > 5:
                first = nav_list[-1]
                last = nav_list[0]
                period_return = (last["nav"] - first["nav"]) / first["nav"] * 100
                summary += f"  ...（共{len(nav_list)}条）\n"
                summary += f"  区间收益率: {period_return:+.2f}%"
            return summary
        return f"未获取到基金 {input_data['fund_code']} 的净值数据"

    if name == "search_market_news":
        news = await fetch_market_news(input_data.get("keyword", ""))
        if news:
            return json.dumps({"news": news, "scope": "最新财经要闻标题过滤，非全网检索"}, ensure_ascii=False)
        return json.dumps({"status": "insufficient_data", "error": "未获取到匹配新闻，不能据此推断没有相关新闻"}, ensure_ascii=False)

    # === Portfolio 工具 ===
    if name == "get_portfolio_overview":
        overview = calculate_overview(holdings, nav_data, nav_history)
        return json.dumps(overview, ensure_ascii=False)

    if name == "get_attribution":
        attribution = calculate_attribution_by_fund(holdings, nav_data)
        return json.dumps(attribution, ensure_ascii=False)

    if name == "get_health_score":
        health = calculate_health(holdings, nav_data, nav_history)
        overall = sum(d["score"] for d in health) / len(health) if health else 0
        result = {"dimensions": health, "overall_score": round(overall)}
        return json.dumps(result, ensure_ascii=False)

    if name == "get_investment_suggestions":
        suggestions = generate_suggestions(holdings, nav_data, nav_history)
        return json.dumps(suggestions, ensure_ascii=False)

    # === Risk 工具 ===
    if name == "calculate_return":
        nav_list = await fetch_price_history(
            input_data["fund_code"], _asset_type_of(input_data["fund_code"], input_data, holdings),
            input_data["days"])
        if nav_list and len(nav_list) >= 2:
            first_nav = nav_list[-1]["nav"]
            last_nav = nav_list[0]["nav"]
            ret = (last_nav - first_nav) / first_nav * 100
            return (
                f"{input_data['fund_code']} 近 {len(nav_list)} 个交易日收益率: {ret:+.2f}%\n"
                f"起始: {first_nav}（{nav_list[-1]['nav_date']}）\n"
                f"最新: {last_nav}（{nav_list[0]['nav_date']}）"
            )
        return "数据不足，无法计算"

    if name == "compare_funds":
        codes = input_data["fund_codes"][:5]
        results = []
        infos = await asyncio.gather(*[fetch_fund_info(c) for c in codes])
        for code, info in zip(codes, infos, strict=True):
            if info:
                results.append(f"  {info['name']}（{code}）: 净值{info['nav']}, 估值涨跌{info.get('estimated_change', 'N/A')}%")
            else:
                results.append(f"  {code}: 信息获取失败")
        return "基金对比结果：\n" + "\n".join(results)

    if name == "get_drawdown_analysis":
        drawdown = calculate_drawdown(holdings, nav_data, nav_history)
        return json.dumps(drawdown, ensure_ascii=False)

    if name == "get_max_drawdown":
        code = input_data["fund_code"]
        hist = nav_history.get(code, []) if nav_history else []
        if not hist:
            hist = await fetch_price_history(code, _asset_type_of(code, input_data, holdings), 60)
        if hist:
            dd = calculate_max_drawdown(hist)
            return json.dumps(dd, ensure_ascii=False)
        return f"未获取到基金 {code} 的历史数据"

    if name == "get_correlation_matrix":
        if not nav_history or len(nav_history) < 2:
            return "至少需要2只基金的历史数据才能计算相关性"
        matrix = calculate_correlation(nav_history)
        name_map = {h.fund_code: h.fund_name for h in holdings}
        return json.dumps({"matrix": matrix, "names": name_map}, ensure_ascii=False)

    return f"未知工具: {name}"
