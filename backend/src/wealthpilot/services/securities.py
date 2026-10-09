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
_OVERSEAS_RE = re.compile(r"(?<![A-Za-z0-9])(\d{4,5}\.HK|HK\d{4,5}|[A-Z]{1,5}\.US)(?![A-Za-z0-9])", re.IGNORECASE)


async def search(query: str, limit: int = 8) -> list[dict]:
    """按名称 / 代码 / 拼音搜索。返回 A 股、港股、美股、场内基金（ETF）、场外基金。"""
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
        kind, code = item.get("Classify", ""), item.get("Code", "")
        asset_type = _CLASSIFY.get(kind)
        if asset_type and re.fullmatch(r"\d{6}", code):
            out.append({"code": code, "name": item.get("Name", ""), "asset_type": asset_type, "market": "cn",
                        "type_label": item.get("SecurityTypeName", "")})
        elif kind == "HK" and re.fullmatch(r"0\d{4}", code):      # 只要 0 开头的正股和 ETF：1、2 开头是窝轮，5、6 是牛熊证，8 是人民币柜台
            out.append({"code": f"{code}.HK", "name": item.get("Name", ""), "asset_type": "stock", "market": "hk", "type_label": "港股"})
        elif kind == "UsStock" and re.fullmatch(r"[A-Z]{1,5}", code):                        # 带数字的是债券、权证这类
            out.append({"code": f"{code}.US", "name": item.get("Name", ""), "asset_type": "stock", "market": "us", "type_label": "美股"})
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

    # 直接写了港股、美股代码的（00700.HK、hk00700、AAPL.US、$AAPL）：去取一下名字，取得到才算
    from wealthpilot.services import global_stocks
    explicit = {global_stocks.canonical(m) for m in _OVERSEAS_RE.findall(text) if global_stocks.is_global(m)}
    explicit |= {f"{m}.US" for m in re.findall(r"\$([A-Z]{1,5})\b", text)}
    if explicit:
        for code, quote in (await global_stocks.fetch_quotes(sorted(explicit)[:4])).items():
            found.setdefault(code, {"code": code, "name": quote["name"], "asset_type": "stock", "industry": "", "market": quote["market"]})

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
                                           "industry": industry.get(top["code"], ""), "market": top.get("market", "cn")})
    return list(found.values())
