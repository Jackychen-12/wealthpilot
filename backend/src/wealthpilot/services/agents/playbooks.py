"""研究模板（Playbook）—— 固定套路走固定流程。

"研究一只股票"每次都该查基本面、估值、走势、行业四个维度。把这种套路交给模型自由拆解，
同一个问题每次拆法不同，质量不稳定。所以意图识别出来之后，任务图由代码生成；
只有不属于任何模板的问题，才退回让模型自由规划。

每个模板同时规定回答必须包含的章节，Critic 据此检查回答是否完整。
"""

from __future__ import annotations

from dataclasses import dataclass

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.services.agents.planner_agent import Task


@dataclass(frozen=True)
class Playbook:
    key: str
    label: str
    sections: tuple[str, ...]       # 回答必须包含的章节（二级标题里要出现这些词）
    criteria: tuple[str, ...]       # 证据要求，交给 Critic 闸门 A


PLAYBOOKS: dict[str, Playbook] = {
    "stock_deep": Playbook(
        "stock_deep", "个股深度研究",
        sections=("结论", "基本面", "估值", "走势", "行业", "风险", "待验证"),
        criteria=("最近几期营收、净利润及同比，ROE 与负债率", "当前 PE/PB 及其历史分位", "近期走势与所处区间位置", "所属行业与同行对比"),
    ),
    "stock_compare": Playbook(
        "stock_compare", "个股对比",
        sections=("对比", "结论"),
        criteria=("每只股票的营收、净利润及同比、ROE", "每只股票的 PE/PB 及历史分位"),
    ),
    "holding_review": Playbook(
        "holding_review", "持仓诊断",
        sections=("组合概况", "集中度", "重点持仓", "约束", "关注"),
        criteria=("组合市值、收益与各持仓占比", "回撤与相关性", "按风险画像的约束校验结果"),
    ),
    "screen": Playbook(
        "screen", "选股",
        sections=("筛选条件", "候选", "局限"),
        criteria=("筛选条件与匹配到的股票名单",),
    ),
}

_DIMENSIONS = {
    "fundamental": "研究{name}（{code}）的基本面：最近几期营收、净利润及同比、ROE、毛利率、负债率、现金流与分红",
    "valuation": "研究{name}（{code}）的估值：当前 PE/PB/PS、各自的历史分位、与同行业公司的对比",
    "price": "研究{name}（{code}）的走势：最新行情、近一年所处价格区间位置、均线排列与波动率",
    "industry": "研究{name}（{code}）的行业位置：所属行业、行业内市值排名与主要同行、所在行业当日表现、近期公告与新闻",
}


def _stock_tasks(security: dict, dims: tuple[str, ...], prefix: str) -> list[Task]:
    return [Task(id=f"{prefix}{dim}", agent=dim, goal=_DIMENSIONS[dim].format(**security)) for dim in dims]


def build_tasks(playbook: str, securities: list[dict], holdings: list[PortfolioHolding],
                nav_data: dict[str, float], question: str) -> list[Task]:
    """按模板生成任务图。条件不满足（比如没解析出股票）时返回 []，由调用方退回自由规划。"""
    stocks = [s for s in securities if s["asset_type"] in ("stock", "etf")]

    if playbook == "stock_deep" and stocks:
        return _stock_tasks(stocks[0], ("fundamental", "valuation", "price", "industry"), "")

    if playbook == "stock_compare" and len(stocks) >= 2:
        tasks: list[Task] = []
        for i, s in enumerate(stocks[:3]):
            tasks += _stock_tasks(s, ("fundamental", "valuation"), f"s{i + 1}_")
        return tasks

    if playbook == "holding_review" and holdings:
        tasks = [Task(id="portfolio", agent="portfolio",
                      goal="诊断用户的整体持仓：市值与收益、各持仓占比与集中度、回撤与相关性、穿透后的真实暴露，"
                           "并按风险画像做约束校验")]
        # 重点持仓：直接持有的股票里市值最大的一只、亏损最深的一只
        direct = [h for h in holdings if (h.asset_type or "fund") == "stock"]
        if direct:
            def value(h):
                return h.shares * nav_data.get(h.fund_code, h.cost_price)

            def ret(h):
                return (nav_data.get(h.fund_code, h.cost_price) - h.cost_price) / h.cost_price

            focus = {max(direct, key=value).fund_code: max(direct, key=value)}
            worst = min(direct, key=ret)
            if ret(worst) < 0:
                focus.setdefault(worst.fund_code, worst)
            for i, h in enumerate(focus.values()):
                security = {"code": h.fund_code, "name": h.fund_name}
                tasks += _stock_tasks(security, ("fundamental", "valuation"), f"h{i + 1}_")
        return tasks

    if playbook == "screen":
        return [
            Task(id="screen", agent="screener", goal=f"按用户的要求筛选股票：{question}"),
            Task(id="detail", agent="valuation", deps=["screen"],
                 goal="对筛选结果中排在最前的 3 只股票，分别查询 PE/PB 的历史分位"),
        ]

    return []
