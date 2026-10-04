"""证券解析：把"宁德时代""茅台""110011"变成确定的代码。

此前代码是模型凭记忆写的 —— 记错一位就会查到另一家公司，而且证据链发现不了。
现在在规划之前用代码解析，解析结果随任务一起交给各 Agent，提示词要求只用解析出的代码。

两条路：
    1. 本地：全市场快照里有全部 A 股的名称，直接在问题文本里找名字（不依赖模型，也不打接口）
    2. 远程：东方财富搜索建议接口，覆盖基金、ETF 和快照里没有的名字
"""

from __future__ import annotations

import re

import httpx

from wealthpilot.services.screener import snapshot

_CLASSIFY = {"AStock": "stock", "OTCFUND": "fund", "Fund": "etf"}
_CODE_RE = re.compile(r"(?<![\d.])(\d{6})(?![\d.])")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


async def search(query: str, limit: int = 8) -> list[dict]:
    """按名称 / 代码 / 拼音搜索。只返回 A 股、场内基金（ETF）、场外基金。"""
    query = query.strip()
    if not query:
        return []
    try:
        async with httpx.AsyncClient(timeout=6.0, headers=_HEADERS) as client:
            resp = await client.get("https://searchapi.eastmoney.com/api/suggest/get",
                                    params={"input": query, "type": 14, "count": max(limit * 2, 10)})
        items = (resp.json().get("QuotationCodeTable") or {}).get("Data") or []
    except Exception:
        items = []
    out = []
    for item in items:
        asset_type = _CLASSIFY.get(item.get("Classify", ""))
        if asset_type and re.fullmatch(r"\d{6}", item.get("Code", "")):
            out.append({"code": item["Code"], "name": item.get("Name", ""), "asset_type": asset_type,
                        "type_label": item.get("SecurityTypeName", "")})
    return out[:limit]


async def resolve_text(text: str, known: list[dict] | None = None) -> list[dict]:
    """从一段自然语言里解析出提到的证券。

    Args:
        known: 已知证券（持仓、自选），优先匹配 —— 用户说"我那只白酒基金"时名字未必是全称，
               但持仓里的名称和代码是准的。
    """
    found: dict[str, dict] = {}

    def add(code, name, asset_type, industry=""):
        found.setdefault(code, {"code": code, "name": name, "asset_type": asset_type, "industry": industry})

    for item in known or []:
        if item["code"] in text or (len(item.get("name", "")) >= 2 and item["name"] in text):
            add(item["code"], item.get("name", ""), item.get("asset_type", "stock"))

    snap = await snapshot()
    stocks = snap.get("stocks", [])
    by_code = {s["code"]: s for s in stocks}
    # 名称匹配：长名优先，避免"中国平安"被"平安"之类的短名抢先
    remaining = text
    for s in sorted(stocks, key=lambda s: -len(s["name"])):
        if len(s["name"]) >= 3 and s["name"] in remaining:
            add(s["code"], s["name"], "stock", s["industry"])
            remaining = remaining.replace(s["name"], " ")

    for code in _CODE_RE.findall(text):
        if code in found:
            continue
        if code in by_code:
            add(code, by_code[code]["name"], "stock", by_code[code]["industry"])
        else:
            hits = [h for h in await search(code, 3) if h["code"] == code]
            if hits:
                add(code, hits[0]["name"], hits[0]["asset_type"])
    return list(found.values())


async def resolve_names(names: list[str], already: list[dict]) -> list[dict]:
    """模型从问题里抽出来的名字（"茅台""宁王"这类简称、基金名）逐个走搜索接口补全。"""
    found = {s["code"]: s for s in already}
    snap = await snapshot()
    industry = {s["code"]: s["industry"] for s in snap.get("stocks", [])}
    for name in names[:5]:
        name = str(name).strip()
        if not name or any(name in s["name"] or name == s["code"] for s in found.values()):
            continue
        hits = await search(name, 3)
        if hits:
            top = hits[0]
            found.setdefault(top["code"], {**{k: top[k] for k in ("code", "name", "asset_type")},
                                           "industry": industry.get(top["code"], "")})
    return list(found.values())
