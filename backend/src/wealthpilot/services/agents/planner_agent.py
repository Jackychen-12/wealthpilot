"""PlannerAgent — 把用户问题拆解成可并行执行的任务图。

替代原来的 RouterAgent。Router 只能三选一，导致 "我半导体仓位重不重、要不要调"
这类需要同时调用持仓 + 风险 + 市场三方面证据的问题必然答不全 —— 那是架构上限，
不是 prompt 能补的。

Planner 产出一张小型 DAG：无依赖的任务并行执行，有依赖的排到下一波。
同时产出 success_criteria，交给 Critic 检查证据是否足够支撑结论。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from wealthpilot.models.profile import InvestorProfile
from wealthpilot.services import skills
from wealthpilot.services.agents.prompts import build_profile_context
from wealthpilot.services.ai_client import json_mode, raise_if_unavailable
from wealthpilot.settings import get_settings

if TYPE_CHECKING:
    from wealthpilot.services.ai_client import AIClient

VALID_AGENTS = ("fundamental", "valuation", "price", "industry", "capital", "expectation", "screener", "portfolio", "fund")
INTENTS = ("stock_deep", "stock_compare", "holding_review", "screen", "review", "free")
# 有固定流程、不需要模型拆任务的意图
_PLAYBOOK_INTENTS = INTENTS[:5]

# 关键词兜底：LLM 不可用时仍能路由
KEYWORD_RULES: list[tuple[list[str], str]] = [
    # 得分并列时靠前的优先
    (["筛选", "选股", "找出", "有哪些股票", "哪些股票"], "screener"),
    (["营收", "净利润", "利润", "财报", "业绩", "ROE", "毛利率", "负债", "现金流", "分红", "基本面"], "fundamental"),
    (["估值", "市盈率", "市净率", "PE", "PB", "贵不贵", "便宜", "分位"], "valuation"),
    (["股价", "走势", "涨跌", "行情", "均线", "K线", "波动", "高位", "低位", "回测", "分批"], "price"),
    (["资金", "主力", "流入", "流出", "融资", "融券", "两融", "股东户数", "筹码", "十大股东", "机构持仓", "北向", "增持", "减持",
      "回购", "解禁", "大宗", "龙虎榜"], "capital"),
    (["预期", "一致预期", "研报", "评级", "目标价", "券商怎么看", "机构怎么看", "业绩预告", "业绩快报", "超预期", "调研", "消息", "利好", "利空"], "expectation"),
    (["行业", "板块", "同行", "公告", "新闻", "大盘", "指数", "市场"], "industry"),
    (["持仓", "组合", "收益", "归因", "回撤", "相关性", "集中度", "穿透", "调仓", "配置", "健康"], "portfolio"),
    (["基金", "净值", "基金经理"], "fund"),
]

# 触发仓位/操作类意图的词 —— 这类问题必须带上组合层面的约束检查
ACTION_KEYWORDS = ("加仓", "减仓", "买入", "卖出", "调仓", "止损", "仓位", "该不该", "值得")

_HOLDING_WORDS = ("我的持仓", "我的组合", "我的仓位", "我持有", "我的股票", "我的基金", "持仓诊断")
_REVIEW_WORDS = ("复盘", "验证点", "成绩单", "之前的研究", "之前的判断", "说得对不对", "准不准", "回头看")
_SCREEN_WORDS = ("筛选", "选股", "找出", "有哪些股票", "哪些股票", "帮我找")
# 只问一个具体数字的窄问题，不值得跑四个维度
_NARROW_WORDS = ("多少钱", "股价多少", "现价", "最新价", "市盈率多少", "PE多少", "涨了多少", "跌了多少", "净值多少")


@dataclass
class Task:
    id: str
    agent: str
    goal: str
    deps: list[str] = field(default_factory=list)


@dataclass
class Plan:
    intent: str
    tasks: list[Task]
    success_criteria: list[str] = field(default_factory=list)
    source: str = "llm"  # llm | fallback
    playbook: str = ""   # 命中的研究模板；空表示自由规划
    sections: list[str] = field(default_factory=list)   # 模板要求回答包含的章节
    securities: list[dict] = field(default_factory=list)
    method: str = ""     # 技能正文：用户写的做法，交给撰写环节

    @property
    def is_single(self) -> bool:
        return len(self.tasks) == 1

    def waves(self) -> list[list[Task]]:
        """按依赖关系分波，同一波内的任务可以并发执行。"""
        remaining = {t.id: t for t in self.tasks}
        done: set[str] = set()
        result: list[list[Task]] = []

        while remaining:
            wave = [t for t in remaining.values() if all(d in done for d in t.deps)]
            if not wave:
                # 依赖成环或指向不存在的任务 —— 剩余任务一次性放行，不阻塞用户
                wave = list(remaining.values())
            result.append(wave)
            for t in wave:
                done.add(t.id)
                remaining.pop(t.id, None)

        return result


class PlannerAgent:
    def __init__(self, client: AIClient, model: str, profile: InvestorProfile | None = None):
        self.client = client
        self.model = model
        self.profile = profile

    def plan(self, message: str, context: str = "", securities: list[dict] | None = None,
             holdings: list | None = None, nav_data: dict | None = None, depth: str = "auto") -> Plan:
        """规划一轮研究。

        先识别意图：命中研究模板就由代码生成任务图（稳定、可预期），否则用模型拆解的任务。
        context 是此前几轮对话，只喂给模型；规则兜底只看当前问题，免得被历史带偏。
        securities 是规划之前已经解析出来的证券 —— 代码不让模型猜。
        """
        securities = securities or []
        if depth == "quick":
            return self._quick_plan(message, context, securities, holdings or [])
        # 用户自己写的方法优先：话里点到了某个技能的触发词，就按它来，不再让模型另外规划
        skill = skills.match(message)
        if skill:
            from wealthpilot.services.agents.playbooks import build_skill_tasks
            tasks = build_skill_tasks(skill, securities, holdings or [], message)
            if tasks:
                return Plan(intent=skill.label or skill.name, tasks=tasks, success_criteria=list(skill.criteria), source="skill",
                            playbook=skill.key, sections=list(skill.sections), securities=securities, method=skill.body)
        decision = self._decide(message, context, securities)
        intent = decision.intent if decision else self.classify_by_rules(message, securities, bool(holdings))
        if depth == "deep" and intent not in _PLAYBOOK_INTENTS:
            # 用户点了"深入"：问题里有股票就走完整的研究模板，哪怕问法很随意
            stocks = [s for s in securities if s["asset_type"] in ("stock", "etf")]
            intent = "stock_compare" if len(stocks) >= 2 else "stock_deep" if stocks else intent

        from wealthpilot.services.agents.playbooks import PLAYBOOKS, build_tasks
        if intent in PLAYBOOKS:
            tasks = build_tasks(intent, securities, holdings or [], nav_data or {}, message)
            if tasks:
                book = PLAYBOOKS[intent]
                sections = list(book.sections)
                # 建议模式：个股研究多一节明确的立场与操作建议
                if getattr(get_settings(), "advice_mode", False) and intent in ("stock_deep", "stock_compare"):
                    sections.append("建议")
                return Plan(intent=book.label, tasks=tasks, success_criteria=list(book.criteria),
                            source="llm" if decision else "fallback", playbook=book.key,
                            sections=sections, securities=securities)

        plan = decision if decision and decision.tasks else self._keyword_fallback(message)
        plan.securities = securities
        return plan

    def _quick_plan(self, message: str, context: str, securities: list[dict], holdings: list) -> Plan:
        """快速回答：最多派两个 Agent，不走完整模板、不留验证点，十来秒给一个带证据的短结论。"""
        from wealthpilot.services.agents.playbooks import _stock_tasks

        stocks = [s for s in securities if s["asset_type"] in ("stock", "etf")]
        decision = self._decide(message, context, securities)
        intent = decision.intent if decision else self.classify_by_rules(message, securities, bool(holdings))
        if decision and decision.tasks:
            tasks = decision.tasks[:1]
        elif intent in ("stock_deep", "stock_compare") and stocks:
            dims = ("valuation",) if len(stocks) > 1 else ("fundamental", "valuation")
            tasks = [t for i, s in enumerate(stocks[:2]) for t in _stock_tasks(s, dims, f"q{i + 1}_")][:2]
        elif intent == "holding_review" and holdings:
            tasks = [Task("portfolio", "portfolio", "概括用户持仓的市值与收益、最大的一个风险点，并做画像约束校验")]
        elif intent == "screen":
            tasks = [Task("screen", "screener", f"按用户的要求筛选股票：{message}")]
        elif intent == "review":
            tasks = [Task("review", "review", "概括验证点成绩单：成立、被证伪、待核对各多少")]
        else:
            tasks = self._keyword_fallback(message).tasks[:1]
        for t in tasks:
            t.deps = []
        return Plan(intent="快速回答", tasks=tasks, source="llm" if decision else "fallback", securities=securities)

    def extract_names(self, message: str, context: str = "") -> list[str]:
        """让模型列出问题里提到的证券名称（简称、基金名），供解析环节去查代码。失败返回 []。"""
        try:
            result = self.client.create(
                model=self.model, max_tokens=2000,
                system=('列出用户问题里提到的每一只股票、ETF 或基金的名称或代码，原样照抄，不要补全、不要翻译成代码。'
                        '只返回 JSON：{"securities":["..."]}。没有提到任何具体证券就返回 {"securities":[]}。'),
                messages=[{"role": "user", "content": f"此前对话：\n{context}\n\n当前问题：{message}" if context else message}],
                **json_mode(self.client),
            )
            match = re.search(r"\{.*\}", result.text.strip(), re.DOTALL)
            names = json.loads(match.group()).get("securities") if match else []
            return [str(n) for n in names][:5] if isinstance(names, list) else []
        except Exception as e:
            raise_if_unavailable(e)
            return []

    def _decide(self, message: str, context: str, securities: list[dict]) -> Plan | None:
        max_tasks = get_settings().planner_max_tasks
        resolved = "\n".join(f"- {s['name']}（{s['code']}，{s['asset_type']}）" for s in securities) or "（没有解析出具体证券）"
        prompt = (f"此前对话：\n{context}\n\n" if context else "") + f"已解析出的证券：\n{resolved}\n\n当前问题：{message}"
        try:
            result = self.client.create(
                model=self.model,
                # 默认开启思考的模型，思考 token 也计入 max_tokens，给太少 JSON 会被截断
                max_tokens=4000,
                system=build_planner_prompt(self.profile),
                messages=[{"role": "user", "content": prompt}],
                **json_mode(self.client),
            )
            return self._parse(result.text, max_tasks)
        except Exception as e:
            raise_if_unavailable(e)   # 模型用不了就别退回关键词规划了：后面的 Agent 一样跑不动
            return None

    @staticmethod
    def classify_by_rules(message: str, securities: list[dict], has_holdings: bool) -> str:
        """模型不可用时的意图识别。"""
        stocks = [s for s in securities if s["asset_type"] in ("stock", "etf")]
        if any(w in message for w in _REVIEW_WORDS):
            return "review"
        if any(w in message for w in _SCREEN_WORDS) and not stocks:
            return "screen"
        if len(stocks) >= 2:
            return "stock_compare"
        if len(stocks) == 1 and not any(w in message for w in _NARROW_WORDS):
            return "stock_deep"
        if has_holdings and any(w in message for w in _HOLDING_WORDS):
            return "holding_review"
        return "free"

    @staticmethod
    def _parse(text: str, max_tasks: int) -> Plan | None:
        match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None

        raw_tasks = data.get("tasks") or []
        tasks: list[Task] = []
        for i, rt in enumerate(raw_tasks[:max_tasks]):
            agent = rt.get("agent")
            if agent not in VALID_AGENTS:
                continue
            tasks.append(
                Task(
                    id=str(rt.get("id") or f"t{i + 1}"),
                    agent=agent,
                    goal=str(rt.get("goal") or "").strip(),
                    deps=[str(d) for d in (rt.get("deps") or [])],
                )
            )

        intent = str(data.get("intent") or "free")
        if not tasks and intent not in _PLAYBOOK_INTENTS:
            return None

        known = {t.id for t in tasks}
        for t in tasks:
            t.deps = [d for d in t.deps if d in known and d != t.id]

        return Plan(
            intent=intent,
            tasks=tasks,
            success_criteria=[str(c) for c in (data.get("success_criteria") or [])],
            source="llm",
        )

    @staticmethod
    def _keyword_fallback(message: str) -> Plan:
        scores = dict.fromkeys(VALID_AGENTS, 0)
        for keywords, agent in KEYWORD_RULES:
            for kw in keywords:
                if kw in message:
                    scores[agent] += 1

        # 得分并列时按 KEYWORD_RULES 的先后取
        order = [agent for _, agent in KEYWORD_RULES]
        best = max(order, key=lambda k: (scores[k], -order.index(k)))
        if scores[best] == 0:
            best = "portfolio"

        tasks = [Task(id="t1", agent=best, goal=message, deps=[])]

        # 操作类问题在兜底路径下也要补一条组合层面的任务，否则会给出没有约束依据的仓位建议
        if any(kw in message for kw in ACTION_KEYWORDS) and best != "portfolio":
            tasks.append(Task(id="t2", agent="portfolio",
                              goal=f"评估该操作对组合回撤与集中度的影响，并按风险画像校验：{message}", deps=[]))

        criteria = ["需覆盖用户问题涉及的核心指标"]
        if len(tasks) > 1:
            criteria.append("需包含操作对组合风险的影响")

        return Plan(
            intent="free",
            tasks=tasks,
            success_criteria=criteria,
            source="fallback",
        )


def build_planner_prompt(profile: InvestorProfile | None = None) -> str:
    from wealthpilot.services.agents.registry import AGENTS

    experts = "\n".join(f"- {name}: {spec.summary}" for name, spec in AGENTS.items())
    return f"""你是投研任务规划器。先判断用户问题属于哪种意图，再决定是否需要你来拆任务。

## 意图（intent）
- stock_deep: 对**一只**股票做综合研究（"XX 怎么样""值得关注吗""帮我分析 XX"）。只问一个具体数字、或只问一个维度（只问业绩 / 只问估值 / 只问走势）的不算，归 free。
- stock_compare: 对比两到三只股票
- holding_review: 诊断用户自己的整体持仓 / 组合
- screen: 按条件找股票（"找出 ROE 高于 15 的白酒股"）
- review: 复盘此前的研究——之前的判断对不对、验证点成立了多少、成绩单（"复盘一下之前的研究""上次对茅台的判断准不准"）
- free: 以上都不是，或者只是问一个具体的点或单一维度（"茅台现在多少钱""比亚迪最近业绩怎么样""招商银行最近走势如何""今天大盘怎么样"），只派对应的一两个专家

前五种意图有固定的研究流程，**不需要你拆任务**，tasks 留空即可。只有 free 需要你拆。

## 可用专家（仅 free 时使用）
{experts}

## free 时的拆解规则
1. 简单查询只拆 1 个任务；需要多方面证据的拆 2-4 个
2. 相互独立的任务 deps 留空，它们会被并发执行；只有真正需要前序结果时才写 deps
3. 涉及加仓/减仓/调仓/止损/仓位的问题，必须包含一个 portfolio 任务来评估对组合回撤与集中度的影响并校验风险画像
4. 任务目标里提到证券时，使用"已解析出的证券"里的名称和代码，不要自己写代码
5. success_criteria 写明"回答这个问题必须拿到哪些证据"。只写用户问到的、且上述专家取得到的证据；
   用户没问的延伸内容不要写进来——写了取不到，整轮回答会被判为证据不足
6. 不要把多轮追问当成孤立问题，结合此前对话理解指代

{build_profile_context(profile)}

## 输出
只返回 JSON，不要任何其他内容：
{{"intent":"free","tasks":[{{"id":"t1","agent":"price","goal":"具体要查什么","deps":[]}}],"success_criteria":["..."]}}"""
