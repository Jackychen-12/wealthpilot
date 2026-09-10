"""每次研究独立的工具缓存、预算与可追溯证据。"""

import asyncio
import json
import time
from datetime import datetime, timezone
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
    codes = sorted(set([h for h in (nav_history or {})] + [str(v) for k, v in inputs.items() if k.startswith("fund_code") and isinstance(v, str)]))
    as_of = {c: max((r["nav_date"] for r in (nav_history or {}).get(c, [])), default=None) for c in codes}
    sources = []
    if name in ("get_fund_info", "get_nav_history", "calculate_return", "compare_funds", "backtest_rule", "get_max_drawdown"):
        sources = [{"url": f"https://fundf10.eastmoney.com/jjjz_{c}.html", "kind": "fund_nav"} for c in codes]
    if name in ("lookthrough_portfolio", "compute_stock_overlap"):
        sources = [{"url": f"https://fundf10.eastmoney.com/ccmx_{c}.html", "kind": "quarterly_top_ten"} for c in codes]
    if isinstance(data, dict) and "news" in data:
        sources = [{"url": n.get("source_url", ""), "published_at": n.get("published_at", "")} for n in data["news"]]
    return {"id": f"E-{uuid4().hex[:12]}", "tool": name, "input": inputs, "output": output,
            "status": status, "provenance": {"retrieved_at": datetime.now(timezone.utc).isoformat(),
            "as_of": as_of, "sources": sources, "method": name,
            "basis": "工具原始返回及本次持仓快照；计量单位见字段名/原文，未知字段不得推断"}}
