"""手机触达：通过 Telegram 机器人收简报、提问、处理建议单。

机器人跟着 WealthPilot 进程跑（长轮询，不需要公网地址）；进程没开时手机上也就没有回应。
只认一个聊天：先在本机生成配对码，再从手机把它发给机器人，这个聊天才成为"主人"。
其他任何人发来的消息一律不处理 —— 这个机器人能看持仓、能授权建议单。
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
import uuid

import httpx
from sqlmodel import Session

from wealthpilot.services import cache
from wealthpilot.settings import get_settings

_OWNER_KEY, _PAIR_KEY = "channel:telegram:owner", "channel:telegram:pair"
_FOREVER = 3650 * cache.DAY
PAIR_TTL = 600
CHUNK = 3800   # Telegram 单条上限 4096
HELP = ("直接发问题就是一次研究，例如：帮我分析一下宁德时代\n"
        "/quick 问题 — 快速回答（十来秒）\n/digest — 今天的简报\n/review — 当初的判断现在怎么样\n"
        "/proposals — 等我决定的建议\n/stock 名称 — 行情与估值分位\n/help — 这份说明")
STATUS = {"passed": "已通过校验", "partial": "部分证据缺失", "rejected": "未通过校验，未发布", "insufficient_data": "证据不足，未发布", "failed": "执行失败"}


# ── 配对 ────────────────────────────────────────────────

def owner() -> int | None:
    data = cache.read(_OWNER_KEY, _FOREVER) or {}
    return data.get("chat_id")


def set_owner(chat_id: int | None) -> None:
    cache.write(_OWNER_KEY, {"chat_id": chat_id})


def new_pair_code() -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.write(_PAIR_KEY, {"code": code, "at": time.time()})
    return code


def _pair_matches(text: str) -> bool:
    data = cache.read(_PAIR_KEY, PAIR_TTL) or {}
    code = data.get("code")
    if not code or time.time() - data.get("at", 0) > PAIR_TTL:
        return False
    return secrets.compare_digest(code, text.strip())


def status() -> dict:
    s = get_settings()
    return {"channel": "telegram", "configured": bool(s.telegram_bot_token), "paired": owner() is not None}


# ── Telegram 接口 ───────────────────────────────────────

class Telegram:
    def __init__(self, token: str, base: str = "https://api.telegram.org", http: httpx.AsyncClient | None = None) -> None:
        self._url = f"{base.rstrip('/')}/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10))

    async def call(self, method: str, **params):
        resp = await self._http.post(f"{self._url}/{method}", json={k: v for k, v in params.items() if v is not None})
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description") or f"Telegram 返回 {resp.status_code}")
        return data.get("result")

    async def send(self, chat_id: int, text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
        """发一条消息；太长就按段落切成几条，按钮挂在最后一条上。"""
        chunks = split_text(text) or ["（空）"]
        for i, chunk in enumerate(chunks):
            markup = None
            if buttons and i == len(chunks) - 1:
                markup = {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in buttons]}
            await self.call("sendMessage", chat_id=chat_id, text=chunk, reply_markup=markup, disable_web_page_preview=True)


def split_text(text: str, size: int = CHUNK) -> list[str]:
    out, current = [], ""
    for para in text.split("\n"):
        while len(para) > size:
            out.append(para[:size])
            para = para[size:]
        if len(current) + len(para) + 1 > size:
            out.append(current)
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current.strip():
        out.append(current)
    return out


def plain(markdown: str) -> str:
    """把回答整理成聊天里能读的纯文本：去掉证据标记和 Markdown 符号。"""
    text = re.sub(r"\s*\[E-[a-f0-9]+\]", "", markdown)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"【\1】", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^\|?\s*:?-{3,}.*$\n?", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── 机器人 ──────────────────────────────────────────────

class Bot:
    def __init__(self, api: Telegram, ask=None) -> None:
        self.api = api
        self._ask = ask            # 测试时换成假的研究入口
        self.history: list[dict] = []
        self.conversation = f"tg-{uuid.uuid4()}"

    def _session(self) -> Session:
        from wealthpilot.storage.db import get_engine
        return Session(get_engine())

    @property
    def uid(self) -> int:
        return get_settings().local_user_id

    async def handle(self, update: dict) -> None:
        callback = update.get("callback_query")
        message = (callback or {}).get("message") or update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if chat_id is None:
            return
        text = str((callback or {}).get("data") or message.get("text") or "").strip()
        master = owner()

        # 没绑定：只接受配对码
        if master is None:
            code = re.sub(r"^/(pair|start)\s*", "", text)
            if _pair_matches(code):
                set_owner(chat_id)
                await self.api.send(chat_id, "已绑定。之后简报和提醒会发到这里，你也可以直接在这里提问。\n\n" + HELP)
            else:
                await self.api.send(chat_id, "这个机器人还没有绑定主人。在 WealthPilot 的「设置 → 手机触达」里生成配对码，然后发送：/pair 配对码")
            return
        if chat_id != master:
            return   # 不是主人：不回应，也不透露任何信息

        try:
            if callback:
                await self.api.call("answerCallbackQuery", callback_query_id=callback.get("id"))
                await self._button(chat_id, text)
            else:
                await self._text(chat_id, text)
        except Exception as e:  # noqa: BLE001 — 出错要告诉用户，而不是沉默
            await self.api.send(chat_id, f"出错了：{e}")

    # —— 文字消息 ——

    async def _text(self, chat_id: int, text: str) -> None:
        command, _, rest = text.partition(" ")
        rest = rest.strip()
        if command in ("/start", "/help"):
            await self.api.send(chat_id, HELP)
        elif command == "/digest":
            await self._digest(chat_id, run=rest == "run")
        elif command == "/review":
            await self._review(chat_id)
        elif command == "/proposals":
            await self._proposals(chat_id)
        elif command == "/stock":
            await self._stock(chat_id, rest)
        elif command == "/approve":
            await self._approve_text(chat_id, rest)
        elif command == "/reject":
            pid, _, reason = rest.partition(" ")
            await self._reject(chat_id, int(pid.lstrip("#")), reason)
        elif command == "/quick":
            await self._research(chat_id, rest, "quick")
        elif command == "/new":
            self.history, self.conversation = [], f"tg-{uuid.uuid4()}"
            await self.api.send(chat_id, "已开始新会话。")
        elif text.startswith("/"):
            await self.api.send(chat_id, "没有这个命令。\n\n" + HELP)
        elif text:
            await self._research(chat_id, text, "auto")

    async def _research(self, chat_id: int, question: str, depth: str) -> None:
        if not question:
            await self.api.send(chat_id, "要问什么？例如：/quick 茅台现在估值贵不贵")
            return
        if self._ask is None:
            from wealthpilot.services.local_run import stream_local
            self._ask = stream_local
        done, proposals, told = None, [], False
        async for e in self._ask(question, list(self.history), self.conversation, depth=depth):
            if e.get("type") == "plan" and not told:
                told = True
                await self.api.send(chat_id, f"收到，{e.get('intent') or '在查'}，预计约 {e.get('eta_seconds') or 30} 秒。")
            elif e.get("type") == "checkpoints":
                proposals = e.get("proposals") or []
            elif e.get("type") == "done":
                done = e
        if done is None:
            await self.api.send(chat_id, "这次没有跑出结果，请稍后再试。")
            return
        meta, answer = done.get("meta") or {}, done.get("content") or ""
        state = STATUS.get(meta.get("status", ""), meta.get("status", ""))
        card = meta.get("summary")
        head = f"{state} · {meta.get('seconds') or '?'} 秒"
        if card:   # 长回答：先给结论，再给正文
            stance = f"\n立场：{card['stance']}" if card.get("stance") else ""
            await self.api.send(chat_id, f"【结论】{card['conclusion']}{'……' if card.get('truncated') else ''}{stance}\n\n{head}")
            body = plain(answer)
            await self.api.send(chat_id, body if len(body) <= 3 * CHUNK else body[:3 * CHUNK] + "\n\n……太长了，完整报告在网页版的「研究记录」里。")
        else:
            await self.api.send(chat_id, f"{plain(answer)}\n\n{head}")
        if meta.get("status") in ("passed", "partial"):
            self.history = [*self.history, {"role": "user", "content": question}, {"role": "assistant", "content": answer}][-6:]
        for p in proposals:
            await self._offer(chat_id, p)

    # —— 只读命令 ——

    async def _digest(self, chat_id: int, run: bool = False) -> None:
        from wealthpilot.services import watcher
        with self._session() as db:
            digest = await watcher.run(db, self.uid, push=False) if run else (watcher.recent(db, self.uid, 1) or [None])[0]
        await self.api.send(chat_id, digest_text(digest) if digest else "还没有简报。发送 /digest run 立即检查一次。")

    async def _review(self, chat_id: int) -> None:
        from wealthpilot.services import checkpoints
        with self._session() as db:
            card = checkpoints.scorecard(db, self.uid)
        if not card["total"]:
            await self.api.send(chat_id, "还没有验证点。对一只具体的股票做一次研究后会自动生成。")
            return
        rate = "—" if card["hold_rate_pct"] is None else f"{card['hold_rate_pct']}%"
        lines = [f"成立率 {rate}：成立 {card['held']}，被证伪 {card['broken']}，待核对 {card['pending']}"]
        lines += [f"· {c['name']} {c['metric_label']} {c['op']} {c['threshold']}：{'成立' if c['status'] == 'held' else '被证伪'}，实际 {c['actual_value']}"
                  for c in card["recent_verified"][:6]]
        await self.api.send(chat_id, "\n".join(lines))

    async def _stock(self, chat_id: int, query: str) -> None:
        from wealthpilot.services import securities, stocks
        hits = await securities.search(query, 1) if query else []
        if not hits:
            await self.api.send(chat_id, f"没有找到「{query}」。" if query else "用法：/stock 茅台")
            return
        sec = hits[0]
        quote, history = await asyncio.gather(stocks.fetch_stock_quote(sec["code"]), stocks.fetch_valuation_history(sec["code"]),
                                              return_exceptions=True)
        if not isinstance(quote, dict):
            await self.api.send(chat_id, f"暂时取不到{sec['name']}的行情。")
            return
        line = f"{quote['name']} {sec['code']}  {quote['price']}  {quote.get('change_pct', 0):+.2f}%\nPE {quote.get('pe_ttm')} · PB {quote.get('pb')}"
        if isinstance(history, list) and history:
            pe = (stocks.summarize_valuation(history).get("pe") or {}).get("percentile")
            if pe is not None:
                line += f" · PE 历史分位 {pe}%"
        await self.api.send(chat_id, line)

    # —— 建议单 ——

    async def _proposals(self, chat_id: int) -> None:
        from wealthpilot.services import checkpoints, proposals
        with self._session() as db:
            rows = [checkpoints.serialize_proposal(p) for p in proposals.open_proposals(db, self.uid)]
        if not rows:
            await self.api.send(chat_id, "没有等你决定的建议。")
        for p in rows:
            await self._offer(chat_id, p)

    async def _offer(self, chat_id: int, p: dict) -> None:
        qty = f"建议 {p['shares']} 股" if p.get("shares") else "数量由你定"
        text = f"建议 #{p['id']}：{p['action_label']} {p['name']} {p['code']}（{qty}，参考价 {p.get('price_ref') or '—'}）\n{p.get('reason') or ''}"
        if p.get("invalidation"):
            text += f"\n失效条件：{p['invalidation']}"
        text += f"\n（想说明为什么不采纳：/reject {p['id']} 原因）"
        await self.api.send(chat_id, text, [[("授权", f"ap:{p['id']}"), ("不采纳", f"rj:{p['id']}")]])

    async def _button(self, chat_id: int, data: str) -> None:
        from wealthpilot.services import broker, checkpoints, proposals
        action, _, raw = data.partition(":")
        pid = int(raw or 0)
        if action == "no":
            await self.api.send(chat_id, "已取消，建议单还在。")
        elif action == "rj":
            await self._reject(chat_id, pid, "")
        elif action == "ap":
            # 第一步只是问清楚；真正执行要再点一次"确认"
            with self._session() as db:
                p = checkpoints.serialize_proposal(proposals.owned(db, self.uid, pid))
            if not broker.enabled():
                await self.api.send(chat_id, f"没有开模拟盘时，授权是把你在券商的实际成交记入持仓。请发送：/approve {pid} 数量 成交价")
            elif not p.get("shares"):
                await self.api.send(chat_id, f"这条建议没有给数量。请发送：/approve {pid} 数量")
            else:
                await self.api.send(chat_id, f"将在模拟盘按最新价{p['action_label']} {p['name']} {p['shares']} 股（不动真钱）。确认吗？",
                                    [[("确认", f"ok:{pid}"), ("取消", f"no:{pid}")]])
        elif action == "ok":
            with self._session() as db:
                p = proposals.owned(db, self.uid, pid)
                done = await proposals.authorize(db, self.uid, pid, int(p.shares or 0))
                await self.api.send(chat_id, f"已执行：{checkpoints.ACTIONS.get(done.action, done.action)} {done.name} {done.exec_shares} 股 @ {done.exec_price}")

    async def _approve_text(self, chat_id: int, rest: str) -> None:
        from wealthpilot.services import checkpoints, proposals
        parts = rest.split()
        if len(parts) not in (2, 3):
            await self.api.send(chat_id, "用法：/approve 编号 数量 [成交价]")
            return
        with self._session() as db:
            done = await proposals.authorize(db, self.uid, int(parts[0].lstrip("#")), int(parts[1]), float(parts[2]) if len(parts) == 3 else None)
            await self.api.send(chat_id, f"已执行：{checkpoints.ACTIONS.get(done.action, done.action)} {done.name} {done.exec_shares} 股 @ {done.exec_price}")

    async def _reject(self, chat_id: int, pid: int, reason: str) -> None:
        from wealthpilot.services import proposals
        with self._session() as db:
            p = proposals.reject(db, self.uid, pid, reason)
            await self.api.send(chat_id, f"已记为不采纳：{p.name}。")


def digest_text(digest: dict) -> str:
    lines = [f"{digest['day']} · {digest['summary']}"]
    lines += [f"· {e['name']} {e['code']}：{e['text']}".replace("  ", " ") for e in digest["events"]]
    return "\n".join(lines)


# ── 推送与轮询 ──────────────────────────────────────────

async def notify(text: str, buttons: list[list[tuple[str, str]]] | None = None) -> bool:
    """给主人发一条消息。没配置、没绑定或发送失败都返回 False，不抛异常。"""
    token, chat_id = get_settings().telegram_bot_token, owner()
    if not token or chat_id is None:
        return False
    try:
        await Telegram(token, get_settings().telegram_api_base).send(chat_id, text, buttons)
        return True
    except Exception:  # noqa: BLE001
        return False


async def run_bot() -> None:
    """长轮询。没填令牌时空转等着 —— 在网页上填好就会接上，不用重启。"""
    bot, token_in_use, offset = None, "", None
    running: set[asyncio.Task] = set()
    while True:
        settings = get_settings()
        token = settings.telegram_bot_token
        if not token:
            await asyncio.sleep(15)
            continue
        if token != token_in_use:
            bot, token_in_use, offset = Bot(Telegram(token, settings.telegram_api_base)), token, None
        try:
            updates = await bot.api.call("getUpdates", timeout=25, offset=offset, allowed_updates=["message", "callback_query"])
            for update in updates or []:
                offset = update["update_id"] + 1
                # 一次研究要几十秒：放到后台跑，期间还能点按钮、发别的命令
                task = asyncio.create_task(bot.handle(update))
                running.add(task)
                task.add_done_callback(running.discard)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 网络抖动、令牌失效：等一会儿再试，不让循环退出
            await asyncio.sleep(10)
