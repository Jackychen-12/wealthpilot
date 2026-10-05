"""公告与定期报告正文。

此前公告只有标题，财报只有指标。这里把正文取回来：定期报告动辄几十万字，不可能整篇交给模型，
所以按主题（管理层讨论、主营构成、风险、展望）定位到对应章节，只摘那一段。
正文发布后不会变，取一次就长期缓存。
"""

from __future__ import annotations

import asyncio
import re

import httpx

from wealthpilot.services import cache
from wealthpilot.services.stocks import _HEADERS, plain_code

_LIST = "https://np-anotice-stock.eastmoney.com/api/security/ann"
_CONTENT = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
_MAX_PAGES = 260          # 每页约 5000 字；再长的报告只取前面这些
EXCERPT = 2600
_STUB_CHARS, _MAX_PDF_BYTES, _MAX_PDF_PAGES = 3000, 40 * 1024 * 1024, 400
# 主题 -> 章节标题里会出现的写法（年报、半年报、季报的措辞不完全一样）
TOPICS: dict[str, tuple[str, ...]] = {
    "管理层讨论": ("管理层讨论与分析", "经营情况讨论与分析", "经营情况的讨论与分析", "主要经营情况"),
    "主营构成": ("主营业务分行业", "分行业、分产品", "分产品情况", "营业收入构成", "主营业务分析"),
    "业绩变动原因": ("变动原因说明", "变动的主要原因", "变动原因", "主要原因"),
    "风险": ("可能面对的风险", "风险因素", "重大风险提示", "面临的风险"),
    "展望": ("未来发展的展望", "公司发展战略", "经营计划", "未来展望"),
}
_IMPORTANT = re.compile(r"业绩预告|业绩快报|报告$|报告全文|减持|增持|回购|重大资产|重组|收购|问询|立案|处罚|诉讼|停牌|分红|权益分派|股权激励|解除限售|质押|变更")


async def list_filings(code: str, limit: int = 30, page: int = 1) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(_LIST, params={"sr": -1, "page_size": max(1, min(limit, 50)), "page_index": page,
                                                   "ann_type": "A", "client_source": "web", "stock_list": plain_code(code)})
        items = (resp.json().get("data") or {}).get("list") or []
    except Exception:
        return []
    return [{
        "art_code": i.get("art_code", ""), "date": str(i.get("notice_date", ""))[:10], "title": i.get("title", ""),
        "category": ((i.get("columns") or [{}])[0] or {}).get("column_name", ""),
        "url": f"https://data.eastmoney.com/notices/detail/{plain_code(code)}/{i.get('art_code', '')}.html",
    } for i in items]


def is_important(filing: dict) -> bool:
    return bool(_IMPORTANT.search(filing.get("title", "")) or "报告" in filing.get("category", ""))


async def _load_text(art_code: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
        async def page(n: int) -> dict:
            resp = await client.get(_CONTENT, params={"art_code": art_code, "client_source": "web", "page_index": n})
            return resp.json().get("data") or {}

        first = await page(1)
        if not first.get("notice_content"):
            return {}
        total = min(int(first.get("page_size") or 1), _MAX_PAGES)
        gate = asyncio.Semaphore(8)

        async def guarded(n: int) -> str:
            async with gate:
                return (await page(n)).get("notice_content") or ""

        rest = await asyncio.gather(*[guarded(n) for n in range(2, total + 1)], return_exceptions=True)
    text = first["notice_content"] + "".join(r for r in rest if isinstance(r, str))
    # 有些公告的文本接口只有一句"详见附件"，正文在 PDF 里
    if len(text) < _STUB_CHARS and str(first.get("attach_url") or "").split("?")[0].endswith(".pdf"):
        text = await _pdf_text(first["attach_url"]) or text
    return {"art_code": art_code, "title": first.get("notice_title", ""), "date": str(first.get("notice_date", ""))[:10],
            "pages": total, "text": re.sub(r"[ \t　]{2,}", " ", text)}


async def _pdf_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=60.0, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200 or len(resp.content) > _MAX_PDF_BYTES:
            return ""
        return await asyncio.to_thread(_extract_pdf, resp.content)
    except Exception:
        return ""


def _extract_pdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:_MAX_PDF_PAGES])


async def fetch_text(art_code: str) -> dict:
    """一份公告的全文。取不到返回 {}。"""
    if not re.fullmatch(r"AN\d{12,24}", art_code or ""):
        return {}
    try:
        return await cache.cached(f"filing:{art_code}", 3650 * cache.DAY, lambda: _load_text(art_code))
    except Exception:
        return {}


def excerpt(text: str, keywords: tuple[str, ...] | list[str], size: int = EXCERPT) -> tuple[str, str]:
    """定位到正文里讲这个主题的地方，返回（命中的标题写法，摘录）。目录里的同名条目要跳过。"""
    for kw in keywords:
        for match in re.finditer(re.escape(kw), text):
            tail = text[match.end():match.end() + 12]
            # 目录行（后面跟着一串点和页码）、"详见“××”章节"式的引用、句子中间顺带提到的，都不是章节正文
            if re.match(r"\s*[.…·]{2,}", tail) or re.match(r"\s*[”」』，。；、）)]", tail):
                continue
            return kw, text[match.start():match.start() + size].strip()
    return "", ""


async def latest_report(code: str, topics: list[str] | None = None) -> dict:
    """最新一份定期报告（年报 / 半年报 / 季报全文）里各主题的摘录。"""
    report = None
    for page in range(1, 6):   # 公告多的公司，最近一份定期报告可能排在几百条之后
        batch = await list_filings(code, 50, page)
        report = next((f for f in batch if f["category"].endswith("报告全文")), None)
        if report or len(batch) < 50:
            break
    if report is None:
        return {}
    doc = await fetch_text(report["art_code"])
    if not doc:
        return {}
    wanted = [t for t in (topics or list(TOPICS)) if t in TOPICS] or list(TOPICS)
    sections = []
    for topic in wanted:
        hit, body = excerpt(doc["text"], TOPICS[topic], EXCERPT if len(wanted) > 2 else EXCERPT * 2)
        if body:
            sections.append({"topic": topic, "heading": hit, "excerpt": body})
    return {"code": plain_code(code), "title": report["title"], "date": report["date"], "category": report["category"],
            "art_code": report["art_code"], "url": report["url"], "total_chars": len(doc["text"]), "sections": sections,
            "note": "摘录是按章节标题定位后截取的原文片段，不是全文；表格在纯文本里可能错位，数字以财务指标工具为准"}


async def read(art_code: str, keyword: str = "", page: int = 1, size: int = 4000) -> dict:
    """读一份公告：给了 keyword 就取它附近的片段，否则按页读。"""
    doc = await fetch_text(art_code)
    if not doc:
        return {}
    text = doc["text"]
    base = {"art_code": art_code, "title": doc["title"], "date": doc["date"], "total_chars": len(text)}
    if keyword:
        hits = [m.start() for m in re.finditer(re.escape(keyword), text)][:3]
        if not hits:
            return {**base, "keyword": keyword, "matches": 0, "text": ""}
        return {**base, "keyword": keyword, "matches": text.count(keyword),
                "text": "\n……\n".join(text[max(0, h - 200):h + size // len(hits)] for h in hits)}
    pages = max(1, -(-len(text) // size))
    page = max(1, min(page, pages))
    return {**base, "page": page, "pages": pages, "text": text[(page - 1) * size:page * size]}
