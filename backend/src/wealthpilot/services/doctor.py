"""自检：装好了没有、哪一环不通、该怎么修。

每一项返回 {name, status, detail, fix}：status 是 ok / warn / fail。
warn 是“不影响主要功能但值得知道”，fail 是“这一块现在用不了”。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

from wealthpilot import __version__
from wealthpilot.settings import HOME, get_settings


def _item(name: str, status: str, detail: str, fix: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


async def _timed(call) -> tuple[bool, float]:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(call(), 12)
    except Exception:  # noqa: BLE001
        return False, time.monotonic() - started
    return bool(result), time.monotonic() - started


async def _sources() -> list[dict]:
    from wealthpilot.services import capital, stocks
    from wealthpilot.services.assets import fetch_sina_quotes

    async def consensus():   # 直接问数据中心，不走缓存：要测的是现在通不通
        rows, _ = await stocks.datacenter("RPT_WEB_RESPREDICT", filter='(SECURITY_CODE="600519")', page_size=1)
        return rows

    probes = [("行情（新浪）", lambda: fetch_sina_quotes(["600519"]), "报价、当日涨跌、提醒"),
              ("日线（腾讯 / 东方财富）", lambda: stocks.fetch_stock_kline("600519", 5), "走势、回撤、回测"),
              ("财务与估值（东方财富数据中心）", lambda: stocks.fetch_financial_indicators("600519", 1), "基本面、估值分位、选股"),
              ("公告（东方财富）", lambda: stocks.fetch_announcements("600519", 1), "公告与财报正文"),
              ("资金流向（新浪）", lambda: capital._sina_json("MoneyFlow.ssi_ssfx_flzjtj", {"daima": "sh600519"}), "资金流向"),
              ("一致预期与筹码（东方财富数据中心）", consensus, "一致预期、融资融券、股东与机构持仓、增减持")]
    results = await asyncio.gather(*[_timed(call) for _, call, _ in probes])
    return [_item(name, "ok" if ok else "fail", f"{seconds:.1f} 秒" if ok else "取不到数据",
                  "" if ok else f"影响：{used}。多半是网络或对方限流，过几分钟再试；公司网络可能需要代理。")
            for (name, _, used), (ok, seconds) in zip(probes, results, strict=True)]


def _model(online: bool) -> dict:
    from wealthpilot.routes.onboarding import model_ready
    from wealthpilot.services.ai_client import create_ai_client

    settings = get_settings()
    label = f"{settings.ai_provider} · {settings.active_model}"
    if not model_ready():
        return _item("模型", "fail", "还没有填 API Key", "打开网页版「设置」填一个 DeepSeek 或 Claude 的 Key；不填也能看行情、选股、管持仓，只是不能让 AI 研究。")
    if not online:
        return _item("模型", "ok", f"{label}（已配置，未实测）")
    started = time.monotonic()
    try:
        client = create_ai_client(settings)
        client.create(model=settings.active_model, max_tokens=2000, system="只回复两个字：正常", messages=[{"role": "user", "content": "测试"}])
    except Exception as e:  # noqa: BLE001 — 认得出的说人话，认不出的把供应商返回的原因原样给用户
        from wealthpilot.services.ai_client import diagnose
        known = diagnose(e)
        if known:
            return _item("模型", "fail", f"{label} 用不了", known.message)
        return _item("模型", "fail", f"{label} 调用失败：{str(e)[:160]}", "检查 Key 是否有效、账户是否有余额、模型名是否写对（网页版「设置」里可以改并测试）。")
    return _item("模型", "ok", f"{label}，{time.monotonic() - started:.1f} 秒")


def _storage() -> list[dict]:
    from sqlmodel import Session

    from wealthpilot.services import memory
    from wealthpilot.storage.db import get_engine

    settings = get_settings()
    db = Path(settings.db_path)
    out = [_item("数据目录", "ok", str(HOME))]
    try:
        with Session(get_engine()) as session:
            chain = memory.verify(session, settings.local_user_id)
        size = db.stat().st_size / 1e6 if db.is_file() else 0
        out.append(_item("数据库", "ok", f"{db}（{size:.1f} MB）"))
        out.append(_item("审计日志", "ok" if chain.get("ok") else "fail", f"{chain.get('count', 0)} 条，哈希链{'完整' if chain.get('ok') else '被改动过'}",
                         "" if chain.get("ok") else "审计日志的某一条和它的哈希对不上，说明数据库被直接改过。"))
    except Exception as e:  # noqa: BLE001
        out.append(_item("数据库", "fail", f"打不开 {db}：{str(e)[:120]}", "检查这个路径是否可写；数据库损坏的话可以用 data/backups 里的备份替换。"))
    return out


def _web(port: int, serving: bool) -> list[dict]:
    from wealthpilot.main import WEB_DIR

    built = (WEB_DIR / "index.html").is_file()
    out = [_item("网页版", "ok" if built else "warn", "已构建" if built else "还没有构建",
                 "" if built else "在仓库目录运行 make setup（需要 Node.js）。没有它终端照样能用。")]
    if serving:   # 这次自检就是从正在运行的服务里发起的，不用再去探自己的端口
        return [*out, _item(f"端口 {port}", "ok", "WealthPilot 正在运行")]
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        mine = resp.status_code == 200 and resp.json().get("status") == "ok"
        out.append(_item(f"端口 {port}", "ok" if mine else "warn", "WealthPilot 正在运行" if mine else "被别的程序占着",
                         "" if mine else f"换一个端口启动：wealthpilot --port {port + 1}"))
    except httpx.HTTPError:
        out.append(_item(f"端口 {port}", "ok", "空闲（WealthPilot 现在没有在运行）"))
    return out


async def _reach() -> dict:
    from wealthpilot.services import channels, feishu

    settings = get_settings()
    listed = channels.status_all()
    ready = [c for c in listed if c["configured"]]
    if not ready:
        return _item("手机触达", "warn", "没有配置", "可选。想在手机上收简报、提问，到网页版「设置 → 手机触达」接上 Telegram、飞书或企业微信。")
    problems = []
    if settings.telegram_bot_token:
        try:
            await channels.Telegram(settings.telegram_bot_token, settings.telegram_api_base).call("getMe")
        except Exception as e:  # noqa: BLE001
            problems.append(f"连不上 Telegram：{str(e)[:80]}（令牌写错了，或者本机到不了 api.telegram.org）")
    if feishu.listener_error():
        problems.append(feishu.listener_error())
    summary = "、".join(f"{c['label']}{'已绑定' if c['paired'] else '未绑定'}" for c in ready)
    if problems:
        return _item("手机触达", "fail", summary, "；".join(problems))
    unpaired = [c["label"] for c in ready if not c["paired"]]
    return _item("手机触达", "warn" if unpaired else "ok", summary,
                 f"{'、'.join(unpaired)}还没有绑定：到网页版「设置 → 手机触达」生成配对码，在那个应用里发给机器人。" if unpaired else "")


def _extras() -> list[dict]:
    from sqlmodel import Session

    from wealthpilot.services import automations, skills, upgrade
    from wealthpilot.storage.db import get_engine

    found, problems = skills.discover()
    out = [_item("技能", "warn" if problems else "ok", f"{len(found)} 个可用" + (f"，{len(problems)} 个文件有问题" if problems else ""),
                 "；".join(f"{Path(p['path']).name}：{p['problems'][0]}" for p in problems[:3]) if problems else "")]
    with Session(get_engine()) as db:
        autos = automations.list_all(db, get_settings().local_user_id)
    active = [a for a in autos if a.enabled]
    out.append(_item("自动任务", "ok", f"{len(active)} 条开着（共 {len(autos)} 条）；只在 WealthPilot 运行时执行"))
    status = upgrade.check() if get_settings().update_check else {"checked": False, "how": "已在设置里关闭更新检查"}
    if status.get("behind"):
        out.append(_item("版本", "warn", f"v{__version__}，落后 {status['behind']} 处更新", "运行 wealthpilot update"))
    else:
        tail = "已是最新" if status.get("checked") else status.get("how") or "没能检查更新"
        out.append(_item("版本", "ok", f"v{__version__} · {status.get('commit') or '无 git 信息'}（{tail}）"))
    return out


async def run(*, online: bool = True, port: int = 8000, serving: bool = False) -> list[dict]:
    """跑一遍自检。online=False 时不调用模型（其余检查照做）；serving=True 表示是从运行中的服务里发起的。"""
    items = [_item("Python", "ok" if sys.version_info >= (3, 11) else "fail", sys.version.split()[0],
                   "" if sys.version_info >= (3, 11) else "需要 Python 3.11 或更高")]
    items += _storage()
    model, sources, reach, web, extras = await asyncio.gather(
        asyncio.to_thread(_model, online), _sources(), _reach(), asyncio.to_thread(_web, port, serving), asyncio.to_thread(_extras))
    items += [model, *sources, *web, reach, *extras]
    if os.environ.get("WATCH_ENABLED", "").lower() == "false" or not get_settings().watch_enabled:
        items.append(_item("每日盯盘", "warn", "已关闭", "盯盘、定时任务和提醒都不会自己跑。到网页版「设置」里打开。"))
    return items


def render(items: list[dict]) -> str:
    mark = {"ok": "✓", "warn": "!", "fail": "✗"}
    lines = []
    for item in items:
        lines.append(f" {mark[item['status']]} {item['name']}：{item['detail']}")
        if item["fix"]:
            lines.append(f"     → {item['fix']}")
    fails, warns = sum(i["status"] == "fail" for i in items), sum(i["status"] == "warn" for i in items)
    lines.append("")
    lines.append("一切正常。" if not fails and not warns else f"{fails} 项不通，{warns} 项值得留意。" if fails else f"能用，{warns} 项值得留意。")
    return "\n".join(lines)
