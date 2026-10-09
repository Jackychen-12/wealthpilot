"""数据源：谁提供什么、现在通不通、坏了先歇一会儿。

行情、财务、估值这些数据都来自公开的网页接口，没有服务保障：对方改版、限流、临时故障，哪一样都会让某一路数据断掉。
这里不假装它们可靠，而是把“会断”当成常态来处理：

  1. 关键数据排两个互相独立的来源，前一个不行换后一个（DATASETS 里写明了每类数据的先后顺序）；
  2. 一个来源连续失败就先跳过它两分钟，不让每个请求都把超时等一遍；
  3. 每次成败都记下来：wealthpilot doctor 和「数据连接」页能看到哪一路现在不通、从什么时候开始、报的什么错；
  4. 都取不到时，由 cache.resilient 拿上一次取到的顶上，并写明那是什么时候的数据。

能用官方来源的地方用官方的（公告：巨潮资讯；LPR：中国货币网；社会融资规模：中国人民银行）。
其余仍然是东方财富、新浪、腾讯、百度、同花顺的公开页面数据 —— 只供个人研究，不转发、不批量下载；
要有授权、有服务保障的数据，走「数据连接」接自己的账号（iFinD、Tushare 等）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

log = logging.getLogger("wealthpilot.sources")


class SourceError(Exception):
    """来源不通，或者返回的东西不是预期的样子（多半是对方改版了）。"""


# official：数据的发布方自己，或者监管指定的披露渠道。其余都是第三方整理的公开页面数据
SOURCES: dict[str, dict] = {
    "tencent": {"label": "腾讯财经", "official": False, "what": "实时行情"},
    "tencent_kline": {"label": "腾讯财经", "official": False, "what": "前复权日线"},
    "sina": {"label": "新浪财经", "official": False, "what": "行情、财务指标、概念板块"},
    "eastmoney": {"label": "东方财富数据中心", "official": False, "what": "财务、估值、股东、研报、宏观"},
    "eastmoney_kline": {"label": "东方财富行情", "official": False, "what": "前复权日线"},
    "eastmoney_notice": {"label": "东方财富公告", "official": False, "what": "公告列表与正文"},
    "baidu": {"label": "百度股市通", "official": False, "what": "市盈率、市净率历史（A 股、港股、美股）"},
    "cninfo": {"label": "巨潮资讯", "official": True, "what": "上市公司公告（证监会指定的信息披露网站）"},
    "chinamoney": {"label": "中国货币网", "official": True, "what": "LPR（全国银行间同业拆借中心发布）"},
    "pbc": {"label": "中国人民银行", "official": True, "what": "社会融资规模"},
    "mofcom": {"label": "商务部商务数据中心", "official": True, "what": "社会融资规模（转载央行数据，更新慢）"},
}

# 每类数据先用谁、不行换谁。只有一个来源的也列在这里 —— 那就是它断了就没有的意思，不藏着
DATASETS: list[dict] = [
    {"key": "quote", "label": "A 股实时行情", "chain": ["tencent", "sina"], "note": "备用源没有市盈率和市值"},
    {"key": "kline", "label": "A 股日线", "chain": ["tencent_kline", "eastmoney_kline", "sina"], "note": "最后一个备用源是不复权价，会标出来"},
    {"key": "indicators", "label": "财务指标", "chain": ["eastmoney", "sina"]},
    {"key": "valuation", "label": "估值历史与分位", "chain": ["eastmoney", "baidu"], "note": "备用源没有市销率和行业归属，同行对比用不了"},
    {"key": "announcements", "label": "公告", "chain": ["eastmoney_notice", "cninfo"], "note": "备用源是官方披露的 PDF，只有标题和链接，暂时读不了正文"},
    {"key": "overseas_valuation", "label": "港股、美股估值历史", "chain": ["baidu"]},
    {"key": "lpr", "label": "LPR", "chain": ["chinamoney", "eastmoney"]},
    {"key": "tsf", "label": "社会融资规模", "chain": ["pbc", "mofcom"], "note": "备用源经常晚几个月，晚了会写明"},
    {"key": "fundamentals_more", "label": "分红、股东、机构持仓、融资融券、一致预期、研报、宏观（PMI、物价、货币）", "chain": ["eastmoney"]},
    {"key": "overseas", "label": "港股、美股行情与日线", "chain": ["tencent"]},
]

BREAK_AFTER = 2          # 连续失败几次就先跳过：单次抖动就切换，会让同一份数据一会儿来自这家一会儿来自那家
BREAK_SECONDS = 120.0
_PERSIST_KEY = "sources:health"
_PERSIST_EVERY = 600.0

_state: dict[str, dict] = {}
_saved_at = 0.0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _entry(name: str) -> dict:
    return _state.setdefault(name, {"ok_at": "", "fail_at": "", "since": "", "error": "", "streak": 0, "down_until": 0.0})


def ok(name: str) -> None:
    entry = _entry(name)
    recovered = bool(entry["since"])
    entry.update(ok_at=_now(), since="", error="", streak=0, down_until=0.0)
    if recovered:
        log.info("数据源恢复：%s", SOURCES.get(name, {}).get("label", name))
    _persist(force=recovered)


def fail(name: str, error: object) -> None:
    entry = _entry(name)
    first = not entry["since"]
    text = (f"{type(error).__name__}：{error}" if isinstance(error, Exception) else str(error))[:200]
    entry.update(fail_at=_now(), error=text, streak=entry["streak"] + 1, since=entry["since"] or _now())
    if entry["streak"] >= BREAK_AFTER:
        entry["down_until"] = time.monotonic() + BREAK_SECONDS
    if first:
        log.warning("数据源取不到：%s（%s）—— %s", SOURCES.get(name, {}).get("label", name), SOURCES.get(name, {}).get("what", ""), text)
    _persist(force=first)


def is_down(name: str) -> bool:
    return time.monotonic() < _state.get(name, {}).get("down_until", 0.0)


def reset() -> None:
    """测试用：忘掉所有成败记录，连存下来的那份一起。"""
    global _saved_at
    _state.clear()
    _saved_at = 0.0
    try:
        from wealthpilot.services import cache
        cache.write(_PERSIST_KEY, {})
    except Exception:  # noqa: BLE001
        pass


async def first(chain: list[tuple[str, Callable[[], Awaitable[Any]]]]) -> tuple[Any, str]:
    """按顺序试，返回 (结果, 来源)。正在跳过的来源先不试；如果全都在跳过，那就照样从头试一遍 —— 总得有人去试。

    来源抛异常算它失败；正常返回但是空的（这只股票本来就没有这项数据）不算失败，只是接着问下一家。
    """
    live = [item for item in chain if not is_down(item[0])] or chain
    for name, call in live:
        try:
            value = await call()
        except Exception as e:  # noqa: BLE001 — 任何一种失败都只是“换下一家”
            fail(name, e)
            continue
        ok(name)
        if value:
            return value, name
    return None, ""


def _persist(force: bool = False) -> None:
    """把成败记录存一份：doctor 是另一个进程，页面刷新时后端可能刚重启，都要能看到。"""
    global _saved_at
    if not force and time.monotonic() - _saved_at < _PERSIST_EVERY:
        return
    _saved_at = time.monotonic()
    try:
        from wealthpilot.services import cache
        saved = cache.read(_PERSIST_KEY, 30 * cache.DAY) or {}
        for name, entry in _state.items():
            saved[name] = {k: entry[k] for k in ("ok_at", "fail_at", "since", "error")}
        cache.write(_PERSIST_KEY, saved)
    except Exception:  # noqa: BLE001 — 记不下来不该影响取数
        pass


def health() -> list[dict]:
    """每个来源现在的状态：这个进程里见到的，加上之前存下来的。"""
    try:
        from wealthpilot.services import cache
        saved = cache.read(_PERSIST_KEY, 30 * cache.DAY) or {}
    except Exception:  # noqa: BLE001
        saved = {}
    out = []
    for name, meta in SOURCES.items():
        entry = {**saved.get(name, {}), **{k: v for k, v in _state.get(name, {}).items() if k in ("ok_at", "fail_at", "since", "error") and (v or name in _state)}}
        ok_at, fail_at = entry.get("ok_at", ""), entry.get("fail_at", "")
        status = "unknown" if not ok_at and not fail_at else "failing" if entry.get("since") and fail_at >= ok_at else "ok"
        out.append({"name": name, **meta, "status": status, "last_ok": ok_at, "last_fail": fail_at,
                    "failing_since": entry.get("since", "") if status == "failing" else "", "error": entry.get("error", "") if status == "failing" else ""})
    return out


def overview() -> dict:
    """「数据连接」页和 doctor 用的那张表：每类数据的来源顺序，和各来源现在的状态。"""
    by_name = {h["name"]: h for h in health()}
    datasets = []
    for d in DATASETS:
        chain = [by_name[name] for name in d["chain"]]
        working = next((s for s in chain if s["status"] != "failing"), None)
        datasets.append({"key": d["key"], "label": d["label"], "note": d.get("note", ""),
                         "chain": [{"name": s["name"], "label": s["label"], "official": s["official"], "status": s["status"]} for s in chain],
                         "state": "down" if working is None else "fallback" if working is not chain[0] else "ok" if chain[0]["status"] == "ok" else "unknown"})
    return {"datasets": datasets, "sources": list(by_name.values()),
            "statement": "行情、财务、估值来自东方财富、新浪、腾讯、百度的公开页面，没有服务保障，只供个人研究，不要转发或批量下载；"
                         "LPR、社会融资规模用的是官方发布渠道，公告的备用来源是证监会指定的披露网站。要有授权和保障的数据，在这一页接自己的 iFinD、Tushare 等账号。"}


PROBE = "600519"     # 探测都拿贵州茅台问：它不可能没有数据，返回空就是来源有问题
PROBE_TIMEOUT = 25.0


async def check() -> dict:
    """现在就把每个来源问一遍，看通不通、返回的结构还是不是认识的那个。十来秒，不调用模型。

    日常取数只在出错时才知道哪里坏了，而且有的数据几天才用到一次。这个探测每天收盘后的盯盘会顺带跑一次，
    也可以在「数据连接」页或 wealthpilot doctor 里手动跑 —— 对方改版的那一天就能知道，而不是等到研究做到一半。
    """
    import asyncio

    from wealthpilot.services import macro, stocks

    async def datacenter():
        rows, _ = await stocks.datacenter("RPT_LICO_FN_CPD", filter=f'(SECURITY_CODE="{PROBE}")', page_size=1, strict=True)
        return rows
    probes: dict[str, Callable[[], Awaitable[Any]]] = {
        "tencent": lambda: stocks._tencent_quote(f"sh{PROBE}", PROBE),
        "tencent_kline": lambda: stocks._tencent_kline(f"sh{PROBE}", 5),
        "sina": lambda: stocks._sina_indicators(PROBE, 1),
        "eastmoney": datacenter,
        "eastmoney_kline": lambda: stocks._eastmoney_kline(f"sh{PROBE}", 5),
        "eastmoney_notice": lambda: stocks._em_announcements(PROBE, 1),
        "baidu": lambda: stocks._baidu_valuation(PROBE, "ab", 1),
        "cninfo": lambda: stocks._cninfo_announcements(PROBE, 1),
        "chinamoney": macro._lpr_chinamoney,
        "pbc": macro._tsf_pbc,
        "mofcom": macro._tsf_mofcom,
    }
    for entry in _state.values():        # 明说了要现在查：正在跳过的也照样去问
        entry["down_until"] = 0.0

    async def one(name: str, call: Callable[[], Awaitable[Any]]) -> None:
        try:
            value = await asyncio.wait_for(call(), PROBE_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            fail(name, "超时" if isinstance(e, asyncio.TimeoutError) else e)
            return
        if value:
            ok(name)
        else:
            fail(name, "连上了，但没有返回数据")
    await asyncio.gather(*(one(name, call) for name, call in probes.items()))
    _persist(force=True)
    report = overview()
    report["checked_at"] = _now()
    return report


def problems(report: dict) -> list[str]:
    """探测结果里要告诉人的那几句：哪类数据没了、哪类在用备用的。全都正常返回空。"""
    out = []
    for d in report["datasets"]:
        failing = [s["label"] for s in d["chain"] if s["status"] == "failing"]
        if d["state"] == "down":
            out.append(f"{d['label']}现在取不到（{'、'.join(failing)}都不通）")
        elif d["state"] == "fallback":
            out.append(f"{d['label']}在用备用来源（{failing[0]}不通）" + (f"：{d['note']}" if d["note"] else ""))
    return out
