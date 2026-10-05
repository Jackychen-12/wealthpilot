"""终端入口 —— 在终端里直接用 WealthPilot。

两种用法，界面和命令完全一样：

    wealthpilot                              # 本机模式：进程内直接跑 Agent，读本机数据库
    wealthpilot --server http://host:8000    # 远程模式：连到一台已经在跑的后端

直接输入问题就是一次研究（规划、取证、校验的过程实时显示）；以 / 开头的是命令，
不经过模型、直接出数（/stock、/screen、/review ……）。/help 看全部命令。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sys
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from wealthpilot import __version__

HOME = Path.home() / ".wealthpilot"
COMMANDS: dict[str, str] = {
    "/help": "显示命令",
    "/stock": "/stock <名称或代码> — 行情、估值分位、最近一期财务",
    "/search": "/search <关键词> — 搜索股票 / ETF / 基金",
    "/screen": "/screen pe<15 roe>15 mv>200 [行业] — 选股（pe pb roe mv rev profit chg）",
    "/market": "大盘与行业强弱",
    "/holdings": "我的持仓",
    "/watch": "/watch [add|rm <名称或代码>] — 自选股",
    "/review": "验证点成绩单（事后验证）",
    "/verify": "立即核对到期的验证点",
    "/proposals": "操作建议单",
    "/approve": "/approve <编号> <数量> [成交价] — 授权一条建议（开了模拟盘按最新价下单，否则填成交价记账）",
    "/reject": "/reject <编号> [原因] — 不采纳一条建议（原因会记下来）",
    "/digest": "/digest [run] — 每日简报（run 立即检查一次）",
    "/broker": "模拟盘账户与持仓",
    "/order": "/order <buy|sell> <名称或代码> <数量> — 在模拟盘下单（会再确认一次）",
    "/skills": "我的研究方法（技能）",
    "/memory": "/memory [add <内容> | rm <编号>] — AI 记住的事",
    "/audit": "审计日志（只追加，带完整性校验）",
    "/history": "研究记录",
    "/evidence": "/evidence [证据ID前4位] — 上一次回答的证据",
    "/new": "开始新会话（清空上下文）",
    "/status": "当前模式、后端与模型",
    "/login": "/login <用户名> — 远程模式登录（密码单独输入）",
    "/quit": "退出",
}
STATUS = {"passed": ("green", "已通过校验"), "partial": ("yellow", "部分证据缺失"), "rejected": ("red", "未通过校验 · 未发布"),
          "insufficient_data": ("red", "证据不足 · 未发布"), "failed": ("red", "执行失败")}
CP_STATUS = {"pending": ("dim", "待核对"), "held": ("green", "成立"), "broken": ("red", "被证伪"), "unverifiable": ("yellow", "无法核对")}


# ── 后端：本机 / 远程 ───────────────────────────────────

class Backend:
    """界面只认这三个方法；本机和远程各实现一遍。"""

    label = ""

    async def request(self, method: str, path: str, **kw) -> object:
        resp = await self.http.request(method, path, **kw)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise RuntimeError(str(detail))
        return resp.json()

    async def tool(self, name: str, **inputs) -> object:
        """调用一个 Agent 工具；工具返回字符串表示没取到数据。"""
        data = (await self.request("POST", f"/api/tools/{name}", json=inputs))["data"]
        if isinstance(data, str):
            raise RuntimeError(data)
        return data

    def chat(self, message: str, history: list[dict], conversation_id: str) -> AsyncIterator[dict]:
        raise NotImplementedError

    async def close(self) -> None:
        await self.http.aclose()


class LocalBackend(Backend):
    """进程内运行：不需要先起服务。数据接口走 ASGI 直连，研究直接调编排器（这样才能逐步显示过程）。"""

    def __init__(self) -> None:
        from wealthpilot.main import app
        from wealthpilot.services.deps import current_user_id
        from wealthpilot.settings import get_settings
        from wealthpilot.storage.db import get_engine

        self.settings = get_settings()
        self.settings.ensure_dirs()
        get_engine()
        # 终端里就是本机用户，和 CLI / MCP 用同一个 LOCAL_USER_ID
        app.dependency_overrides[current_user_id] = lambda: self.settings.local_user_id
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local", timeout=120)
        self.label = f"本机 · {self.settings.ai_provider} / {self.settings.active_model}"

    async def chat(self, message, history, conversation_id):
        from sqlmodel import Session

        from wealthpilot.services.agents.orchestrator import chat_stream
        from wealthpilot.services.context import load_local_user, load_market_context
        from wealthpilot.storage.db import get_engine

        uid = self.settings.local_user_id
        holdings, profile = load_local_user(uid)
        nav_data, nav_history = await load_market_context(holdings)
        with Session(get_engine()) as db:
            async for line in chat_stream(message, history, holdings, nav_data, nav_history,
                                          conversation_id=conversation_id, db_session=db, profile=profile, user_id=uid):
                if line.startswith("data: "):
                    yield json.loads(line[6:])


class RemoteBackend(Backend):
    def __init__(self, server: str, token: str = "") -> None:
        self.server = server.rstrip("/")
        self.http = httpx.AsyncClient(base_url=self.server, timeout=httpx.Timeout(30, read=600))
        self.label = f"远程 · {self.server}"
        if token:
            self.set_token(token)

    def set_token(self, token: str) -> None:
        self.http.headers["Authorization"] = f"Bearer {token}"

    async def chat(self, message, history, conversation_id):
        body = {"message": message, "history": history, "conversation_id": conversation_id}
        async with self.http.stream("POST", "/api/chat", json=body) as resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"后端返回 {resp.status_code}")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])


# ── 小工具 ──────────────────────────────────────────────

_SCREEN_KEYS = {"pe": "pe", "pb": "pb", "roe": "roe", "mv": "mv", "rev": "revenue_yoy", "profit": "profit_yoy", "chg": "change"}


def parse_screen(args: str) -> dict:
    """把 `pe<15 roe>15 mv>200 白酒` 这样的写法转成筛选条件。认不出的词当作行业。"""
    criteria: dict = {"limit": 20}
    for token in args.split():
        match = re.fullmatch(r"([a-zA-Z]+)(<=|>=|<|>)(-?\d+(?:\.\d+)?)", token)
        if not match:
            criteria["industry"] = token
            continue
        key, op, value = match.group(1).lower(), match.group(2)[0], float(match.group(3))
        if key not in _SCREEN_KEYS:
            raise ValueError(f"不认识的条件：{key}（可用 {' '.join(_SCREEN_KEYS)}）")
        base = _SCREEN_KEYS[key]
        if op == "<":
            if key not in ("pe", "pb", "mv", "chg"):
                raise ValueError(f"{key} 只支持 > （下限）")
            criteria[{"mv": "mv_max_yi"}.get(key, f"{base}_max")] = value
        else:
            criteria[{"mv": "mv_min_yi", "roe": "roe_min"}.get(key, f"{base}_min")] = value
    return criteria


def num(v, digits: int = 2, suffix: str = "") -> str:
    return "—" if v is None else f"{v:,.{digits}f}{suffix}"


def signed(v, suffix: str = "%") -> Text:
    """红涨绿跌。"""
    if v is None:
        return Text("—", style="dim")
    return Text(f"{v:+.2f}{suffix}", style="red" if v > 0 else "green" if v < 0 else "")


def cite(text: str) -> str:
    """证据引用 [E-abcd1234…] 缩成 [abcd]，/evidence abcd 可以查原始返回。"""
    return re.sub(r"\[E-([a-f0-9]{4})[a-f0-9]*\]", r"`\1`", text)


# ── 界面 ────────────────────────────────────────────────

class App:
    def __init__(self, backend: Backend, console: Console | None = None) -> None:
        self.backend = backend
        self.console = console or Console()
        self.history: list[dict] = []
        self.conversation_id = str(uuid.uuid4())
        self.evidence: list[dict] = []

    def table(self, *columns: str, right: tuple[int, ...] = ()) -> Table:
        t = Table(box=None, pad_edge=False, header_style="dim", padding=(0, 2, 0, 0))
        for i, c in enumerate(columns):
            t.add_column(c, justify="right" if i in right else "left", no_wrap=i == 0)
        return t

    # —— 研究 ——

    async def research(self, message: str) -> None:
        c, started, answer, meta = self.console, time.time(), "", {}
        self.evidence = []
        with c.status("[dim]解析证券与规划…", spinner="dots") as status:
            async for e in self.backend.chat(message, list(self.history), self.conversation_id):
                kind = e.get("type")
                if kind == "resolved":
                    c.print("[dim]◆ 已解析[/] " + "、".join(f"{s['name']} [cyan]{s['code']}[/]" for s in e["securities"]))
                elif kind == "plan":
                    head = e.get("intent") or "自由问答"
                    c.print(f"[dim]◆ 规划[/] [bold]{head}[/] [dim]· {len(e.get('tasks', []))} 个任务[/]")
                    for t in e.get("tasks", []):
                        c.print(f"  [dim]├[/] {t.get('label', t['agent'])} [dim]{t.get('goal', '')[:60]}[/]")
                    status.update("[dim]取证中…")
                elif kind == "tool_call":
                    status.update(f"[dim]取证中 · {e.get('tool')}")
                elif kind == "evidence":
                    self.evidence.append(e["evidence"])
                elif kind == "task_done":
                    ok = e.get("status") == "completed"
                    c.print(f"  [{'green' if ok else 'red'}]{'✓' if ok else '✗'}[/] {e.get('agent')} [dim]{' '.join(e.get('tools', []))}[/]")
                elif kind == "replan":
                    c.print(f"[yellow]◆ 证据不足，补查 {len(e.get('tasks', []))} 项[/]")
                elif kind == "critic":
                    gate = "证据审核" if e.get("gate") == "evidence" else f"回答校验 第 {e.get('attempt', 1)} 稿"
                    if e.get("passed"):
                        c.print(f"[dim]◆ {gate}[/] [green]通过[/]")
                    else:
                        c.print(f"[dim]◆ {gate}[/] [yellow]打回[/] [dim]{'；'.join(e.get('issues', []))[:110]}[/]")
                    status.update("[dim]撰写并校验回答…")
                elif kind == "synthesizing":
                    status.update("[dim]整合各方证据…")
                elif kind == "checkpoints":
                    meta["checkpoints"], meta["proposals"] = e.get("items", []), e.get("proposals", [])
                elif kind == "error":
                    c.print(f"[red]✗ {e.get('content')}[/]")
                elif kind == "done":
                    answer, meta["done"] = e.get("content", ""), e.get("meta", {})

        c.print()
        c.print(Markdown(cite(answer or "没有生成回答。")))
        done = meta.get("done", {})
        color, label = STATUS.get(done.get("status", ""), ("dim", done.get("status", "")))
        usage = done.get("usage") or {}
        cost = (f" · {(usage['input_tokens'] + usage['output_tokens']) / 1000:.0f}k token（缓存 {usage['cache_hit_pct']}%）"
                if usage.get("input_tokens") else "")
        c.print(f"\n[{color}]● {label}[/] [dim]· {time.time() - started:.0f} 秒 · {len(self.evidence)} 条证据（/evidence 查看）{cost}[/]")
        if done.get("missing_evidence"):
            c.print("[yellow]未能取得的证据：[/]" + "；".join(done["missing_evidence"]))
        if meta.get("checkpoints"):
            c.print("\n[bold]验证点[/] [dim]到期后自动核对这次的判断对不对（/review）[/]")
            self.show_checkpoints(meta["checkpoints"])
        if meta.get("proposals"):
            c.print("\n[bold]操作建议单[/] [dim]需要你逐条授权[/]")
            self.show_proposals(meta["proposals"])
        if done.get("status") in ("passed", "partial"):
            self.history += [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]

    def show_checkpoints(self, items: list[dict]) -> None:
        t = self.table("股票", "条件", "设定时", "核对结果", "状态", right=(2, 3))
        for i in items:
            color, label = CP_STATUS.get(i["status"], ("", i["status"]))
            actual = f"{i['actual_value']}%（{i['actual_as_of']}）" if i["actual_value"] is not None else f"{i['due']} 核对"
            t.add_row(f"{i['name']} {i['code']}", f"{i['metric_label']} {'≥' if i['op'] == '>=' else '≤'} {i['threshold']:g}%",
                      f"{num(i['baseline_value'])}%（{i['baseline_as_of']}）", actual, Text(label, style=color))
        self.console.print(t)

    def show_proposals(self, items: list[dict]) -> None:
        for p in items:
            state = {"proposed": "[magenta]待你决定[/]", "executed": f"[green]已执行 {p['exec_shares']} 股 @ {p['exec_price']}[/]",
                     "rejected": "[dim]已拒绝[/]"}.get(p["status"], p["status"])
            qty = f"建议 {p['shares']} 股" if p["shares"] else "数量由你定"
            self.console.print(f"  [bold]#{p['id']}[/] {p['action_label']} {p['name']} [cyan]{p['code']}[/] [dim]{qty} · 参考价 {num(p['price_ref'])}[/] {state}")
            if p["reason"]:
                self.console.print(f"     {p['reason']}")
            if p["invalidation"]:
                self.console.print(f"     [dim]失效条件：{p['invalidation']}[/]")
        if any(p["status"] == "proposed" for p in items):
            self.console.print("  [dim]/approve <编号> <数量> <成交价> 授权并记入持仓 · /reject <编号> 不采纳[/]")

    # —— 命令 ——

    async def resolve(self, query: str) -> dict:
        if not query:
            raise RuntimeError("需要名称或代码")
        hits = await self.backend.request("GET", "/api/securities/search", params={"q": query})
        if not hits:
            raise RuntimeError(f"没有找到「{query}」")
        return hits[0]

    async def cmd_stock(self, args: str) -> None:
        sec = await self.resolve(args)
        if sec["asset_type"] == "fund":
            info = await self.backend.tool("get_fund_info", fund_code=sec["code"])
            self.console.print(f"[bold]{info['name']}[/] [cyan]{info['code']}[/] 净值 {info['nav']}（{info['nav_date']}）")
            return
        code = sec["code"]
        quote, valuation, fin = await asyncio.gather(
            self.backend.tool("get_stock_quote", code=code), self.backend.tool("get_valuation_history", code=code),
            self.backend.tool("get_financial_indicators", code=code, periods=4), return_exceptions=True)
        if isinstance(quote, Exception):
            raise quote
        c = self.console
        c.print(Text.assemble((f"{quote['name']} ", "bold"), (code, "cyan"), f"  {quote['price']}  ", signed(quote.get("change_pct")),
                              (f"   PE {num(quote.get('pe_ttm'))} · PB {num(quote.get('pb'))} · 市值 {num(quote.get('total_mv_yi'), 0)} 亿 · {quote.get('quote_time', '')}", "dim")))
        if not isinstance(valuation, Exception):
            parts = [f"{k.upper()} {num(v.get('current'))}（分位 {num(v.get('percentile'), 1)}%）" for k in ("pe", "pb", "ps") if (v := valuation.get(k))]
            c.print(f"[dim]估值历史分位（{valuation.get('window_start')} 起，0 最便宜）[/] " + " · ".join(parts))
        if not isinstance(fin, Exception):
            t = self.table("报告期", "营收(亿)", "同比", "归母净利(亿)", "同比", "ROE", "毛利率", "负债率", right=(1, 2, 3, 4, 5, 6, 7))
            for r in fin["reports"]:
                t.add_row(r["report_name"], num(r["revenue_yi"]), signed(r["revenue_yoy_pct"]), num(r["net_profit_yi"]), signed(r["net_profit_yoy_pct"]),
                          num(r["roe_pct"], 2, "%"), num(r["gross_margin_pct"], 2, "%"), num(r["debt_ratio_pct"], 2, "%"))
            c.print(t)
        c.print(f"[dim]直接输入「帮我深度分析一下{quote['name']}」做完整研究[/]")

    async def cmd_search(self, args: str) -> None:
        t = self.table("名称", "代码", "类型")
        for s in await self.backend.request("GET", "/api/securities/search", params={"q": args}):
            t.add_row(s["name"], s["code"], {"stock": "股票", "etf": "ETF", "fund": "基金"}.get(s["asset_type"], s["asset_type"]))
        self.console.print(t if t.row_count else "[dim]没有找到[/]")

    async def cmd_screen(self, args: str) -> None:
        r = await self.backend.request("POST", "/api/screener", json=parse_screen(args))
        t = self.table("公司", "代码", "行业", "市值(亿)", "PE", "PB", "ROE", "营收同比", "净利同比", "涨跌", right=(3, 4, 5, 6, 7, 8, 9))
        for s in r["stocks"]:
            t.add_row(s["name"], s["code"], s["industry"], num(s["total_mv_yi"], 0), num(s["pe_ttm"]), num(s["pb"]), num(s["roe_pct"], 2, "%"),
                      signed(s["revenue_yoy_pct"]), signed(s["profit_yoy_pct"]), signed(s["change_pct"]))
        self.console.print(t)
        self.console.print(f"[dim]符合 {r['matched']} 只，显示 {r['shown']} 只 · 行情 {r['trade_date']} · 业绩 {r['report_date']} · 条件 {r['criteria']}[/]")

    async def cmd_market(self, _: str) -> None:
        overview, sectors = await asyncio.gather(self.backend.tool("get_market_overview"), self.backend.tool("get_sector_ranking", top=5))
        b = overview["breadth"]
        self.console.print("  ".join(f"{i['name']} {i['value']} [{'red' if i['up'] else 'green'}]{i['change']}[/]" for i in overview["indices"]))
        self.console.print(f"上涨 [red]{b['up']}[/] / 下跌 [green]{b['down']}[/] · 涨跌中位数 {b['median_change_pct']:+.2f}% [dim]（{b['trade_date']}）[/]")
        t = self.table("领涨行业", "中位涨跌", "领跌行业", "中位涨跌", right=(1, 3))
        for up, down in zip(sectors["top"], sectors["bottom"], strict=False):
            t.add_row(up["industry"], signed(up["median_change_pct"]), down["industry"], signed(down["median_change_pct"]))
        self.console.print(t)

    async def cmd_holdings(self, _: str) -> None:
        rows = await self.backend.request("GET", "/api/portfolio")
        if not rows:
            self.console.print("[dim]还没有持仓。在工作台的「持仓」页录入，或导入 CSV。[/]")
            return
        total = sum(h.get("market_value") or 0 for h in rows)
        t = self.table("名称", "代码", "类型", "数量", "成本", "最新", "市值", "占比", "收益率", right=(3, 4, 5, 6, 7, 8))
        order = {"stock": 0, "etf": 1, "fund": 2}
        for h in sorted(rows, key=lambda h: (order.get(h["asset_type"], 9), -(h.get("market_value") or 0))):
            t.add_row(h["fund_name"], h["fund_code"], {"stock": "股票", "etf": "ETF", "fund": "基金"}.get(h["asset_type"], h["asset_type"]),
                      num(h["shares"], 0), num(h["cost_price"], 3), num(h.get("latest_nav"), 3), num(h.get("market_value"), 0),
                      num((h.get("market_value") or 0) / total * 100 if total else None, 1, "%"), signed(h.get("return_pct")))
        self.console.print(t)
        self.console.print(f"[dim]总市值 {total:,.0f} 元 · {len(rows)} 项[/]")

    async def cmd_watch(self, args: str) -> None:
        action, _, rest = args.partition(" ")
        if action == "add":
            sec = await self.resolve(rest.strip())
            await self.backend.request("POST", "/api/watchlist", json={"code": sec["code"], "name": sec["name"], "asset_type": sec["asset_type"]})
            self.console.print(f"已加入自选：{sec['name']} {sec['code']}")
        elif action == "rm":
            rows = await self.backend.request("GET", "/api/watchlist")
            hit = next((w for w in rows if rest.strip() in (w["code"], w["name"])), None)
            if not hit:
                raise RuntimeError("自选里没有这一只")
            await self.backend.request("DELETE", f"/api/watchlist/{hit['id']}")
            self.console.print(f"已移出自选：{hit['name']}")
        rows = await self.backend.request("GET", "/api/watchlist")
        t = self.table("名称", "代码", "最新价", "涨跌", "备注", right=(2, 3))
        for w in rows:
            t.add_row(w["name"], w["code"], num(w["price"]), signed(w["change_pct"]), w["note"])
        self.console.print(t if rows else "[dim]还没有自选。/watch add 茅台[/]")

    async def cmd_review(self, _: str) -> None:
        card = await self.backend.request("GET", "/api/checkpoints/scorecard")
        if not card["total"]:
            self.console.print("[dim]还没有验证点。对一只具体的股票做深度研究后会自动生成。[/]")
            return
        rate = "—" if card["hold_rate_pct"] is None else f"{card['hold_rate_pct']}%"
        self.console.print(f"[bold]成立率 {rate}[/]  成立 [green]{card['held']}[/] · 被证伪 [red]{card['broken']}[/] · 待核对 {card['pending']} · 共 {card['total']}")
        self.console.print(f"[dim]{card['note']}[/]")
        self.show_checkpoints(await self.backend.request("GET", "/api/checkpoints"))

    async def cmd_verify(self, _: str) -> None:
        r = await self.backend.request("POST", "/api/checkpoints/verify")
        self.console.print(f"核对出 {r['checked']} 条结果：成立 {r['held']}，被证伪 {r['broken']}" if r["checked"] else "[dim]没有到核对时点的验证点[/]")

    async def cmd_proposals(self, _: str) -> None:
        rows = await self.backend.request("GET", "/api/proposals")
        self.show_proposals(rows) if rows else self.console.print("[dim]还没有建议单[/]")

    async def cmd_approve(self, args: str) -> None:
        parts = args.split()
        paper = (await self.backend.request("GET", "/api/broker")).get("mode") == "paper"
        if len(parts) not in ((2, 3) if paper else (3,)):
            raise RuntimeError("用法：/approve <编号> <数量>" + ("" if paper else " <成交价>"))
        pid, shares = int(parts[0].lstrip("#")), int(parts[1])
        price = None if paper else float(parts[2])
        target = next((p for p in await self.backend.request("GET", "/api/proposals") if p["id"] == pid), None)
        if target is None:
            raise RuntimeError(f"没有编号 {pid} 的建议单")
        if paper:
            self.console.print(f"将在[bold]模拟盘[/]按最新价 [bold]{target['action_label']} {target['name']} {shares} 股[/]（不动真钱）。")
        else:
            self.console.print(f"将把 [bold]{target['action_label']} {target['name']} {shares} 股 @ {price}[/] 记入持仓。"
                               "[yellow]这一步不会向券商下单[/]，请确认你已在券商成交。")
        if (await self.ask("确认？输入 yes：")).strip().lower() != "yes":
            self.console.print("[dim]已取消[/]")
            return
        done = await self.backend.request("POST", f"/api/proposals/{pid}/authorize", json={"shares": shares} if price is None else {"shares": shares, "price": price})
        self.show_proposals([done])

    async def cmd_reject(self, args: str) -> None:
        pid, _, reason = args.strip().partition(" ")
        self.show_proposals([await self.backend.request("POST", f"/api/proposals/{int(pid.lstrip('#'))}/reject", json={"reason": reason.strip()})])

    async def cmd_digest(self, args: str) -> None:
        if args.strip() == "run":
            digest = await self.backend.request("POST", "/api/digest/run")
        else:
            rows = await self.backend.request("GET", "/api/digest")
            if not rows:
                self.console.print("[dim]还没有简报。/digest run 立即检查一次；后端开着时每个交易日会自动跑。[/]")
                return
            digest = rows[0]
        self.console.print(f"[bold]{digest['day']}[/] {digest['summary']}")
        for e in digest["events"]:
            self.console.print(f"  [dim]•[/] {e['name']} [cyan]{e['code']}[/] {e['text']}")

    async def cmd_broker(self, _: str) -> None:
        a = await self.backend.request("GET", "/api/broker")
        if a.get("mode") != "paper":
            self.console.print("[dim]模拟盘未开启：在 backend/.env 里设置 BROKER=paper 后重启[/]")
            return
        self.console.print(Text.assemble(f"总资产 {a['total_assets']:,.0f}  可用 {a['cash']:,.0f}  市值 {a['market_value']:,.0f}  累计盈亏 ", signed(a["total_pnl_pct"])))
        t = self.table("证券", "代码", "数量", "成本", "最新", "市值", "盈亏率", right=(2, 3, 4, 5, 6))
        for p in a["positions"]:
            t.add_row(p["name"], p["code"], str(p["shares"]), num(p["cost_price"], 3), num(p["price"], 3), num(p["market_value"], 0), signed(p["pnl_pct"]))
        self.console.print(t if a["positions"] else "[dim]还没有持仓。/order buy 茅台 100[/]")

    async def cmd_order(self, args: str) -> None:
        parts = args.split()
        if len(parts) != 3 or parts[0] not in ("buy", "sell") or not parts[2].isdigit():
            raise RuntimeError("用法：/order <buy|sell> <名称或代码> <数量>")
        sec = await self.resolve(parts[1])
        if sec["asset_type"] == "fund":
            raise RuntimeError("模拟盘只支持股票和 ETF")
        verb = "买入" if parts[0] == "buy" else "卖出"
        self.console.print(f"将在[bold]模拟盘[/]按最新价 [bold]{verb} {sec['name']} {sec['code']} {parts[2]} 股[/]（不动真钱）。")
        if (await self.ask("确认？输入 yes：")).strip().lower() != "yes":
            self.console.print("[dim]已取消[/]")
            return
        o = await self.backend.request("POST", "/api/broker/orders", json={
            "code": sec["code"], "name": sec["name"], "side": parts[0], "shares": int(parts[2]), "asset_type": sec["asset_type"]})
        if o["status"] == "filled":
            self.console.print(f"[green]已成交[/] {verb} {o['name']} {o['shares']} 股 @ {o['price']}，费用 {o['fee']} 元")
        else:
            self.console.print(f"[red]被拒[/] {o['reason']}")

    async def cmd_skills(self, _: str) -> None:
        data = await self.backend.request("GET", "/api/skills")
        t = self.table("方法", "名称", "触发词", "派谁去查")
        for s in data["skills"]:
            t.add_row(s["label"], s["name"], "、".join(s["triggers"][:4]), " ".join(s["agents"]))
        self.console.print(t if data["skills"] else "[dim]还没有方法。[/]")
        for bad in data["invalid"]:
            self.console.print(f"[yellow]未加载 {bad['path']}：{'；'.join(bad['problems'])}[/]")
        self.console.print(f"[dim]文件放在 {data['dirs'][0]}；话里带上触发词或方法名就会按它研究[/]")

    async def cmd_memory(self, args: str) -> None:
        action, _, rest = args.partition(" ")
        if action == "add" and rest.strip():
            await self.backend.request("POST", "/api/memory", json={"content": rest.strip()})
        elif action == "rm" and rest.strip().isdigit():
            await self.backend.request("DELETE", f"/api/memory/{rest.strip()}")
        rows = await self.backend.request("GET", "/api/memory")
        label = {"preference": "偏好", "decision": "决定", "note": "备注"}
        for m in rows:
            self.console.print(f"  [bold]#{m['id']}[/] [dim]{label.get(m['kind'], m['kind'])}[/] {m['content']}")
        if not rows:
            self.console.print("[dim]还没有。提问时说「记住，……」会被记下来，也可以 /memory add <内容>[/]")

    async def cmd_audit(self, _: str) -> None:
        data = await self.backend.request("GET", "/api/audit", params={"limit": 30})
        ok = data["integrity"]
        self.console.print(f"[green]共 {ok['count']} 条，哈希链校验通过[/]" if ok["ok"] else f"[red]校验失败：第 {ok['broken_at']} 条被改动过[/]")
        t = self.table("时间", "类型", "谁", "内容")
        for e in data["events"]:
            t.add_row(e["at"][:16].replace("T", " "), e["kind"], {"user": "你", "agent": "AI", "system": "系统"}.get(e["actor"], e["actor"]), e["summary"][:60])
        self.console.print(t)

    async def cmd_history(self, _: str) -> None:
        t = self.table("时间", "问题", "结论", "证据", right=(3,))
        for r in await self.backend.request("GET", "/api/research/history"):
            color, label = STATUS.get(r["status"], ("dim", r["status"]))
            t.add_row(r["created_at"][:16].replace("T", " "), r["question"][:44], Text(label, style=color), str(r["evidence_count"]))
        self.console.print(t if t.row_count else "[dim]还没有研究记录[/]")

    async def cmd_evidence(self, args: str) -> None:
        if not self.evidence:
            self.console.print("[dim]这次会话里还没有做过研究[/]")
            return
        key = args.strip().lower()
        for e in self.evidence:
            short = e["id"][2:6]
            if not key:
                self.console.print(f"  [magenta]{short}[/] {e['tool']} [dim]{json.dumps(e.get('input', {}), ensure_ascii=False)[:80]}[/]")
            elif short == key:
                self.console.print(f"[magenta]{short}[/] {e['tool']} {json.dumps(e.get('input', {}), ensure_ascii=False)}")
                self.console.print(str(e.get("output", ""))[:3000], markup=False, highlight=False)

    async def cmd_new(self, _: str) -> None:
        self.history, self.evidence, self.conversation_id = [], [], str(uuid.uuid4())
        self.console.print("[dim]已开始新会话[/]")

    async def cmd_status(self, _: str) -> None:
        health = await self.backend.request("GET", "/health")
        self.console.print(f"{self.backend.label} · 后端 {health.get('status', '?')} · 本次会话 {len(self.history) // 2} 轮")

    async def cmd_login(self, args: str) -> None:
        if not isinstance(self.backend, RemoteBackend):
            raise RuntimeError("本机模式不需要登录（用的是 LOCAL_USER_ID 对应的账户）")
        if not args or " " in args:
            raise RuntimeError("用法：/login <用户名>（密码随后单独输入，不会进历史记录）")
        password = await self.ask_secret("密码：")
        res = await self.backend.request("POST", "/api/auth/login", json={"username": args, "password": password})
        self.backend.set_token(res["access_token"])
        HOME.mkdir(exist_ok=True)
        token_file = HOME / "token"
        token_file.write_text(json.dumps({"server": self.backend.server, "token": res["access_token"]}))
        token_file.chmod(0o600)
        self.console.print(f"已登录：{res['username']}")

    async def cmd_help(self, _: str) -> None:
        t = self.table("命令", "说明")
        for name, text in COMMANDS.items():
            t.add_row(f"[cyan]{name}[/]", text)
        self.console.print(t)
        self.console.print("[dim]直接输入问题就是一次研究，例如：帮我深度分析一下宁德时代 / 对比茅台和五粮液 / 复盘一下之前的研究[/]")

    # —— 主循环 ——

    async def handle(self, line: str) -> bool:
        """处理一行输入。返回 False 表示退出。"""
        line = line.strip()
        if not line:
            return True
        if line in ("/quit", "/exit", "quit", "exit"):
            return False
        try:
            if line.startswith("/"):
                name, _, args = line.partition(" ")
                handler = getattr(self, f"cmd_{name[1:]}", None)
                if handler is None:
                    self.console.print(f"[red]没有这个命令：{name}[/]（/help 看全部）")
                else:
                    await handler(args.strip())
            else:
                await self.research(line)
        except (RuntimeError, ValueError, httpx.HTTPError) as e:
            self.console.print(f"[red]✗ {e or type(e).__name__}[/]")
        return True

    async def ask(self, prompt: str) -> str:
        return await asyncio.to_thread(input, prompt)

    async def ask_secret(self, prompt: str) -> str:
        import getpass
        return await asyncio.to_thread(getpass.getpass, prompt)

    async def run(self) -> None:
        c = self.console
        c.print(f"[bold]WealthPilot[/] [dim]v{__version__} · {self.backend.label}[/]")
        c.print("[dim]输入问题开始研究，/help 看命令，Ctrl-C 中断当前研究，/quit 退出[/]\n")
        read = self._reader()
        while True:
            try:
                line = await read()
            except (EOFError, KeyboardInterrupt):
                break
            task = asyncio.ensure_future(self.handle(line))
            try:
                if not await task:
                    break
            except (KeyboardInterrupt, asyncio.CancelledError):
                # Ctrl-C 只中断当前这次研究，不退出程序
                task.cancel()
                current = asyncio.current_task()
                if current is not None:
                    current.uncancel()
                c.print("\n[yellow]已中断[/]")
            c.print()
        await self.backend.close()

    def _reader(self):
        """交互终端用 prompt_toolkit（历史、命令补全）；管道输入退回逐行读取。"""
        if not sys.stdin.isatty():
            async def plain() -> str:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    raise EOFError
                self.console.print(f"[bold cyan]›[/] {line.strip()}")
                return line
            return plain

        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import FileHistory

        HOME.mkdir(exist_ok=True)
        session = PromptSession(history=FileHistory(str(HOME / "history")),
                                completer=WordCompleter(list(COMMANDS), sentence=True, match_middle=False),
                                complete_while_typing=True,
                                bottom_toolbar=lambda: HTML(f" {self.backend.label} · 会话 {len(self.history) // 2} 轮 · /help"))
        self.ask = lambda prompt: session.prompt_async(prompt)  # type: ignore[method-assign]
        return lambda: session.prompt_async(HTML("<ansicyan><b>› </b></ansicyan>"))


def saved_token(server: str) -> str:
    try:
        data = json.loads((HOME / "token").read_text())
    except (OSError, ValueError):
        return ""
    return data.get("token", "") if data.get("server") == server.rstrip("/") else ""


def main(server: str = "", token: str = "") -> None:
    backend: Backend = RemoteBackend(server, token or saved_token(server)) if server else LocalBackend()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(App(backend).run())
