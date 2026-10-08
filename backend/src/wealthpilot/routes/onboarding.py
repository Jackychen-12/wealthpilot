"""上手：首次引导的进度、粘贴导入持仓、手机渠道的配对。"""

import asyncio
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.research import WatchItem
from wealthpilot.routes.config import _local_only
from wealthpilot.services import cache, channels, securities
from wealthpilot.services.ai_client import _PLACEHOLDER_KEYS
from wealthpilot.services.deps import current_user_id
from wealthpilot.services.stocks import fetch_stock_profile
from wealthpilot.settings import get_settings
from wealthpilot.storage.db import get_session

router = APIRouter(tags=["onboarding"])
_FOREVER = 3650 * cache.DAY


def model_ready() -> bool:
    s = get_settings()
    if s.ai_provider == "openai":   # 兼容服务：本机模型不需要 Key，有地址和模型名就算配好了
        return bool(s.openai_base_url.strip() and s.openai_model.strip())
    key = s.deepseek_api_key if s.ai_provider == "deepseek" else s.anthropic_api_key
    return key.strip() not in _PLACEHOLDER_KEYS


@router.get("/onboarding")
def onboarding(db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """第一次用要走的几步，各自做没做。全做完或用户点了"不再显示"，首页就不再放这张卡。"""
    has_data = (db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).first() is not None
                or db.exec(select(WatchItem).where(WatchItem.user_id == user_id)).first() is not None)
    researched = db.exec(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "assistant",
                                                   ChatMessage.conversation_id != "")).first() is not None
    steps = [
        {"key": "model", "title": "配置模型", "done": model_ready(), "to": "/settings",
         "hint": "填一个 DeepSeek 或 Claude 的 API Key。不填也能看行情、选股、管理持仓，只是不能让 AI 研究。"},
        {"key": "data", "title": "放进你的股票", "done": has_data, "to": "/holdings",
         "hint": "把持仓粘贴进来，或搜一只股票加自选；想先看看效果可以用示例数据。"},
        {"key": "research", "title": "做第一次研究", "done": researched, "to": "/research",
         "hint": "问一句“帮我分析一下××”，约一分钟出一份带证据的结论，并留下之后会自动核对的验证点。"},
        {"key": "reach", "title": "连上手机", "done": any(c["paired"] for c in channels.status_all()), "to": "/settings", "optional": True,
         "hint": "在 Telegram、飞书或企业微信里收每日简报、提问、处理建议单。可以以后再说。"},
    ]
    return {"steps": steps, "complete": all(s["done"] for s in steps if not s.get("optional")),
            "dismissed": bool(cache.read(f"onboarding:dismissed:{user_id}", _FOREVER))}


@router.post("/onboarding/dismiss")
def dismiss_onboarding(user_id: int = Depends(current_user_id)):
    cache.write(f"onboarding:dismissed:{user_id}", {"dismissed": True})
    return {"ok": True}


# ── 粘贴导入持仓 ────────────────────────────────────────

_SPLIT_RE = re.compile(r"[\s,，;；|\t]+")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def parse_line(line: str) -> dict:
    """一行一只：名称或代码、数量、成本价，顺序这样写就行，中间用空格或逗号隔开。
    例：`贵州茅台 100 1500`、`600519,100,1500.5`、`宁德时代 2手 成本262`。"""
    tokens = [t for t in _SPLIT_RE.split(line.strip()) if t]
    query, rest = (tokens[0], tokens[1:]) if tokens else ("", [])
    # "名称 代码 数量 成本"这种写法里，以代码为准
    if rest and re.fullmatch(r"\d{6}", rest[0]) and not re.fullmatch(r"\d{6}", query):
        query, rest = rest[0], rest[1:]
    numbers: list[float] = []
    for token in rest:
        for n in _NUMBER_RE.findall(token):
            numbers.append(float(n) * (100 if "手" in token and not numbers else 1))
    problem = "" if query else "没看懂这一行"
    if query and not numbers:
        problem = "没看到数量"
    elif query and len(numbers) < 2:
        problem = "没看到成本价"
    return {"line": line.strip(), "query": query, "shares": numbers[0] if numbers else None,
            "cost": numbers[1] if len(numbers) > 1 else None, "problem": problem}


@router.post("/portfolio/parse")
async def parse_holdings(body: dict):
    """把粘贴的文字解析成持仓预览。只解析和查代码，不落库 —— 用户确认后再调 /portfolio/batch。"""
    lines = [ln for ln in str(body.get("text") or "").splitlines() if ln.strip()][:50]
    rows = [parse_line(ln) for ln in lines]

    async def resolve(row: dict) -> dict:
        hit = (await securities.search(row["query"], 1) or [None])[0] if row["query"] else None
        if hit is None:
            return {**row, "code": "", "name": "", "asset_type": "", "problem": row["problem"] or f"没找到「{row['query']}」"}
        return {**row, "code": hit["code"], "name": hit["name"], "asset_type": hit["asset_type"]}

    resolved = await asyncio.gather(*[resolve(r) for r in rows])
    return {"rows": [{**r, "ok": not r["problem"]} for r in resolved]}


@router.post("/portfolio/batch")
async def add_holdings(body: dict, db: Session = Depends(get_session), user_id: int = Depends(current_user_id)):
    """批量录入确认过的持仓。已经有的代码不动，原样报告回去。"""
    existing = {h.fund_code for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == user_id)).all()}
    added, skipped = 0, []
    for row in (body.get("rows") or [])[:50]:
        code, name = str(row.get("code") or ""), str(row.get("name") or "")
        try:
            shares, cost = float(row["shares"]), float(row["cost"])
        except (KeyError, TypeError, ValueError):
            skipped.append(f"{name or code}：数量或成本价不对")
            continue
        if not re.fullmatch(r"\d{6}", code) or shares <= 0 or cost <= 0:
            skipped.append(f"{name or code}：数量或成本价不对")
            continue
        if code in existing:
            skipped.append(f"{name}（{code}）已经在持仓里，没有改动")
            continue
        asset_type = row.get("asset_type") if row.get("asset_type") in ("stock", "etf", "fund") else "stock"
        profile = await fetch_stock_profile(code) if asset_type == "stock" else None
        db.add(PortfolioHolding(user_id=user_id, asset_type=asset_type, fund_code=code, fund_name=name or code, shares=shares,
                                cost_price=cost, buy_date=date.today(), industry=(profile or {}).get("industry", "")))
        existing.add(code)
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


# ── 手机渠道 ────────────────────────────────────────────

@router.get("/channel")
def channel_status():
    """每个渠道配没配好、绑没绑定。保留顶层的 configured / paired（Telegram 的），老页面还在用。"""
    from wealthpilot.services import dingtalk, feishu
    listed = channels.status_all()
    for item in listed:
        if item["channel"] == "feishu":
            item["error"] = feishu.listener_error()
        if item["channel"] == "dingtalk":
            item["error"] = dingtalk.listener_error()
    return {**channels.status("telegram"), "channels": listed}


def _channel(name: str) -> str:
    if name not in channels.CHANNELS:
        raise HTTPException(404, "没有这个渠道")
    return name


@router.post("/channel/pair")
def start_pairing(request: Request, channel: str = "telegram"):
    """生成一个 10 分钟有效的配对码。只能在本机生成：谁拿到它，谁就能成为机器人的主人。"""
    _local_only(request)
    if not channels.configured(_channel(channel)):
        raise HTTPException(409, f"先把{channels.CHANNELS[channel]}的应用信息填好并保存")
    return {"code": channels.new_pair_code(channel), "ttl_seconds": channels.PAIR_TTL}


@router.delete("/channel/pair")
def unpair(request: Request, channel: str = "telegram"):
    _local_only(request)
    channels.set_owner(None, _channel(channel))
    return {"ok": True}


@router.post("/channel/test")
async def test_channel(request: Request, channel: str = "telegram"):
    """给这个渠道绑定的聊天发一条测试消息。"""
    _local_only(request)
    name, target = channels.CHANNELS[_channel(channel)], channels.owner(channel)
    api = channels._api_for(channel)
    if api is None or target is None:
        return {"ok": False, "error": f"{name}还没有配置好或还没有绑定"}
    try:
        await api.send(target, "这是 WealthPilot 发来的测试消息。收到就说明这个渠道已经通了。")
    except Exception as e:  # noqa: BLE001 — 把对方返回的原因告诉用户
        return {"ok": False, "error": f"没有发出去：{str(e)[:200]}"}
    return {"ok": True, "error": ""}


# ── 企业微信回调 ────────────────────────────────────────
# 这两个接口是给企业微信的服务器调的，所以不要求登录，也不限本机；谁都能往上发，靠签名和解密把关。

def _wecom_open(msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> str:
    from wealthpilot.services import wecom
    s = get_settings()
    if not channels.configured("wecom"):
        raise HTTPException(404, "企业微信渠道没有配置")
    try:
        return wecom.open_envelope(s.wecom_token, s.wecom_aes_key, s.wecom_corp_id, msg_signature, timestamp, nonce, encrypted)
    except Exception as e:  # noqa: BLE001 — 验签或解密不过：一律拒绝，不透露原因
        raise HTTPException(403, "验证失败") from e


@router.get("/channel/wecom/callback", response_class=PlainTextResponse)
def wecom_verify(msg_signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    """在企业微信后台保存回调地址时，它会先来验证一次：把解密出来的内容原样返回。"""
    return _wecom_open(msg_signature, timestamp, nonce, echostr)


@router.post("/channel/wecom/callback", response_class=PlainTextResponse)
async def wecom_receive(request: Request, msg_signature: str = "", timestamp: str = "", nonce: str = ""):
    """成员给应用发了消息。先立刻应答（企业微信只等 5 秒），研究放到后台跑，跑完用发消息接口回过去。"""
    from wealthpilot.services import wecom
    body = (await request.body()).decode("utf-8", errors="replace")
    inner = _wecom_open(msg_signature, timestamp, nonce, wecom._field(body, "Encrypt"))
    parsed = wecom.parse_message(inner)
    bot = wecom.bot()
    if parsed and bot is not None and wecom.fresh(parsed[2]):
        task = asyncio.create_task(bot.message(parsed[0], parsed[1]))
        _wecom_tasks.add(task)
        task.add_done_callback(_wecom_tasks.discard)
    sender = wecom.unsupported_from(inner)
    if sender and bot is not None and sender == channels.owner("wecom") and wecom.fresh(wecom._field(inner, "MsgId")):
        task = asyncio.create_task(bot.api.send(sender, "企业微信这边暂时只收文字。图片和语音可以在 Telegram、飞书或钉钉里发，或者把内容打成文字发给我。"))
        _wecom_tasks.add(task)
        task.add_done_callback(_wecom_tasks.discard)
    return ""


_wecom_tasks: set[asyncio.Task] = set()
