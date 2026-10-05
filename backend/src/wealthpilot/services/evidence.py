"""每次研究独立的工具缓存、预算与可追溯证据。"""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4


class ToolSession:
    def __init__(self, timeout: float = 30, max_calls: int = 24):
        self.timeout = timeout
        self.max_calls = max_calls
        self.cache: dict[str, asyncio.Task] = {}

    async def execute(self, name, inputs, call):
        key = json.dumps([name, inputs], sort_keys=True, ensure_ascii=False)
        if key not in self.cache:
            if len(self.cache) >= self.max_calls:
                raise RuntimeError("本次研究的工具调用预算已用完")
            self.cache[key] = asyncio.create_task(asyncio.wait_for(call(), self.timeout))
        return await self.cache[key]


def record_evidence(name, inputs, output, nav_history=None):
    status = "ok"
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict) and (data.get("error") or data.get("status") in ("insufficient_data", "failed", "invalid_input")):
        status = "insufficient_data"
    if any(str(output).startswith(s) for s in ("未获取", "未找到", "未取到", "暂无", "数据不足", "工具执行失败", "当前没有", "至少需要", "未知工具")):
        status = "insufficient_data"
    # 指名了基金的工具只溯源到那几只；组合级工具（无基金入参）才溯源到全部持仓
    codes = [str(v) for k, v in inputs.items() if k.startswith("fund_code") and isinstance(v, str)]
    codes += [str(c) for c in inputs.get("fund_codes") or [] if isinstance(inputs.get("fund_codes"), list)]
    codes = sorted(set(codes or (nav_history or {})))
    as_of = {c: max((r["nav_date"] for r in (nav_history or {}).get(c, [])), default=None) for c in codes}
    sources = []
    if name in ("get_fund_info", "get_nav_history", "calculate_return", "compare_funds", "backtest_rule", "get_max_drawdown"):
        sources = [{"url": f"https://fundf10.eastmoney.com/jjjz_{c}.html", "kind": "fund_nav"} for c in codes]
    if name in ("lookthrough_portfolio", "compute_stock_overlap"):
        sources = [{"url": f"https://fundf10.eastmoney.com/ccmx_{c}.html", "kind": "quarterly_top_ten"} for c in codes]
    if isinstance(data, dict) and "news" in data:
        sources = [{"url": n.get("source_url", ""), "published_at": n.get("published_at", "")} for n in data["news"]]
    return {"id": f"E-{uuid4().hex[:12]}", "tool": name, "input": inputs, "output": output,
            "status": status, "provenance": {"retrieved_at": datetime.now(UTC).isoformat(),
            "as_of": as_of, "sources": sources, "method": name,
            "basis": "工具原始返回及本次持仓快照；计量单位见字段名/原文，未知字段不得推断"}}


# ── 证据外置：完整内容留在证据库，交给模型的是压缩后的版本 ──────────
# 一轮深度研究里，同一批证据要发给审核、撰写（每次重写再发一遍）好几次。长证据（财报正文摘录、
# 同行列表、公告列表）占了大头，而撰写环节真正要用的数字，取证的 Agent 已经在初步结论里引用过了。
# 所以给模型看的只留"够判断、够引用"的部分；数字溯源校验和界面上的"查看证据"仍然用完整内容。
_LEVELS = ((8, 400), (5, 240), (3, 140))   # (列表保留几项, 字符串保留多少字)，逐级收紧直到放得下


def _shrink(value, keep: int, limit: int):
    if isinstance(value, dict):
        return {k: _shrink(v, keep, limit) for k, v in value.items()}
    if isinstance(value, list):
        head = [_shrink(v, keep, limit) for v in value[:keep]]
        return [*head, f"…其余 {len(value) - keep} 项已省略"] if len(value) > keep else head
    if isinstance(value, str) and len(value) > limit:
        return f"{value[:limit]}…（共 {len(value)} 字，已省略）"
    return value


def compact(output, budget: int = 1600) -> str:
    """把一条工具返回压到 budget 字左右。放得下就原样返回；JSON 按结构收紧，纯文本取开头。"""
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if len(text) <= budget:
        return text
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return f"{text[:budget]}…（共 {len(text)} 字，已省略）"
    result = text
    for keep, limit in _LEVELS:
        result = json.dumps(_shrink(data, keep, limit), ensure_ascii=False, separators=(",", ":"))
        if len(result) <= budget:
            break
    return result


def brief(e: dict, budget: int = 1600) -> str:
    """一条证据给模型看的写法：ID、工具、入参、压缩后的返回、数据日期。"""
    dates = sorted({str(v) for v in ((e.get("provenance") or {}).get("as_of") or {}).values() if v})
    args = json.dumps(e.get("input", {}), ensure_ascii=False, separators=(",", ":"))
    return (f"[{e.get('id', 'legacy')}] {e['tool']}({args}) → {compact(e.get('output', ''), budget)}"
            + (f"（数据日期 {dates[-1]}）" if dates else ""))
