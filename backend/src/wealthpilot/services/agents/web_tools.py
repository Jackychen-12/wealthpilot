"""联网搜索、读网页 —— 这两个工具的定义和执行。

约定和其他工具一样：返回 JSON 字符串；取不到就返回一句以"未获取到"开头的话，证据记录会标成"无数据"。
"""

from __future__ import annotations

import json

from wealthpilot.services import websearch

WEB_TOOLS = [
    {"name": "web_search",
     "description": "在公开网页里搜索。只在固定数据源查不到时用：公司最近的事件、产品与订单、政策原文、行业动态、网上流传的某个说法是真是假。"
                    "返回标题、网址、来源网站、日期和一小段摘要。财务数字、估值、行情不要用它查，用对应的专门工具。",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "搜索词。写具体：公司名 + 事件 + 年份，如「宁德时代 储能订单 2026」"},
         "limit": {"type": "integer", "description": "要几条，默认 5，最多 8"}}, "required": ["query"]}},
    {"name": "read_webpage",
     "description": "读一个网页的正文（前几千字）。搜索结果的摘要不够下结论时，挑最相关、来源最可靠的一两条读原文。只能读公网上的网页。",
     "input_schema": {"type": "object", "properties": {
         "url": {"type": "string", "description": "网页地址，用 web_search 返回的 url"}}, "required": ["url"]}},
]
NAMES = frozenset(t["name"] for t in WEB_TOOLS)


async def execute(name: str, input_data: dict) -> str:
    if name == "web_search":
        query = str(input_data.get("query") or "").strip()
        found = await websearch.search(query, int(input_data.get("limit") or 5))
        if not found["results"]:
            return f"未获取到「{query}」的搜索结果：{found.get('error') or '没有搜到'}"
        return json.dumps({"query": query, "engine": found["engine"],
                           "results": [{**r, "source_url": r["url"], "published_at": r.get("date", "")} for r in found["results"]],
                           "note": websearch.NOTE}, ensure_ascii=False)
    if name == "read_webpage":
        page = await websearch.read(str(input_data.get("url") or ""))
        if page.get("error"):
            return f"未获取到这个网页的内容：{page['error']}"
        return json.dumps({**page, "source_url": page["url"], "note": websearch.NOTE}, ensure_ascii=False)
    return f"未知工具: {name}"
