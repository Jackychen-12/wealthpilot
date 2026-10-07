"""事后验证：把研究结论拆成可核对的验证点，到期后由代码取数判定。

同类工具都停在"写出一篇看起来靠谱的分析"，没人回头检查当时说得对不对。这里把每次研究
最关键的几条判断落成结构化的验证点（指标 + 条件 + 到期），之后由代码而不是模型核对，
结果累计成这个 Agent 的成绩单，并在下一次研究同一只股票时带回给模型。

验证点只有固定的几类，都是代码能取数判定的：
- 财务类：下一期财报出来后核对（营收同比、净利同比、毛利率、净利率、负债率）
- 估值类：到期日核对 PE / PB 历史分位
- 涨跌类（仅建议模式）：到期日核对区间涨跌幅、相对沪深300ETF 的超额收益
"""

from __future__ import annotations

import asyncio
import json
import re
from contextvars import ContextVar
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import cache, memory, stocks
from wealthpilot.services.ai_client import json_mode
from wealthpilot.settings import get_settings

# 工具执行时"当前是谁"。Web 请求由路由 / 编排器设置；CLI 与 MCP 用默认的本机用户
ACTIVE_USER: ContextVar[int | None] = ContextVar("active_user", default=None)


def active_user() -> int:
    uid = ACTIVE_USER.get()
    return get_settings().local_user_id if uid is None else uid


BENCHMARK = "510300"  # 沪深300ETF，作为超额收益的比较基准
# metric -> (名称, 类别)
METRICS: dict[str, tuple[str, str]] = {
    "revenue_yoy_pct": ("营收同比", "financial"),
    "net_profit_yoy_pct": ("归母净利润同比", "financial"),
    "gross_margin_pct": ("毛利率", "financial"),
    "net_margin_pct": ("净利率", "financial"),
    "debt_ratio_pct": ("资产负债率", "financial"),
    "pe_percentile": ("PE 历史分位", "valuation"),
    "pb_percentile": ("PB 历史分位", "valuation"),
    "return_pct": ("区间涨跌幅", "market"),
    "excess_return_pct": ("相对沪深300ETF 的超额收益", "market"),
}
GROUP_LABEL = {"financial": "财务", "valuation": "估值", "market": "涨跌"}
ACTIONS = {"buy": "买入", "add": "加仓", "reduce": "减仓", "sell": "卖出"}
MAX_PER_STOCK, MAX_TOTAL = 4, 10
# 财报最晚披露期限之外再留些余量；过了还没有新一期，就不再等
_FINANCIAL_GIVE_UP_DAYS = 300


def allowed_metrics() -> dict[str, tuple[str, str]]:
    advice = get_settings().advice_mode
    return {k: v for k, v in METRICS.items() if advice or v[1] != "market"}


# ── 取当前值（基准） ────────────────────────────────────

async def current_values(code: str) -> dict[str, tuple[float, str]]:
    """各指标此刻的实际值与数据日期。取不到的指标不出现在结果里。"""
    reports, history, kline = await asyncio.gather(
        stocks.fetch_financial_indicators(code, 2), stocks.fetch_valuation_history(code),
        stocks.fetch_stock_kline(code, 5), return_exceptions=True)
    out: dict[str, tuple[float, str]] = {}
    if isinstance(reports, list) and reports:
        latest = reports[0]
        for metric, (_, group) in METRICS.items():
            if group == "financial" and latest.get(metric) is not None:
                out[metric] = (float(latest[metric]), latest["report_date"])
    if isinstance(history, list) and history:
        summary = stocks.summarize_valuation(history)
        for metric, key in (("pe_percentile", "pe"), ("pb_percentile", "pb")):
            value = (summary.get(key) or {}).get("percentile")
            if value is not None:
                out[metric] = (float(value), summary.get("as_of") or "")
    if isinstance(kline, list) and kline:
        latest_day = max(r["nav_date"] for r in kline)
        out["return_pct"] = out["excess_return_pct"] = (0.0, latest_day)
    return out


# ── 从一次研究里提出验证点与操作建议 ────────────────────

_PROPOSE_SYSTEM = """你在为一份已经发布的股票研究补"事后验证点"：挑出结论最依赖的几条判断，写成以后能用数据核对的条件。

规则：
1. 只能使用给出的 metric，code 只能是给出的股票代码。
2. 每只股票 2 到 3 条，优先选回答里明确依赖的判断（比如回答说"增长稳健"，就选营收或净利同比）。
3. threshold 是具体数字，op 只能是 ">=" 或 "<="。条件要有信息量：不要设成几乎必然成立的宽松条件。
4. 财务类（financial）在下一期财报核对，不需要 horizon_days；估值类和涨跌类要给 horizon_days（30 到 180）。
5. statement 用一句话说明：这条成立或不成立，对原结论意味着什么。不超过 60 字。
{advice}
只返回 JSON，不要解释：
{{"checkpoints":[{{"code":"600519","metric":"revenue_yoy_pct","op":">=","threshold":0,"horizon_days":90,"statement":"..."}}]{proposal_shape}}}"""

_ADVICE_RULES = """6. 回答对某只股票给出了看多或看空的立场时，必须为它加一条 excess_return_pct 验证点（看多 ">=" 0，看空 "<=" 0），用来事后给这次判断打分。立场是中性时不要加涨跌类验证点。
7. 回答里给出了明确的操作建议（买入 / 加仓 / 减仓 / 卖出）时，在 proposals 里为该股票列一条：action 取 buy / add / reduce / sell；
   shares 是建议的股数（100 的整数倍），回答没有给出数量就填 null；reason 一句话；invalidation 写什么情况下这条建议不再成立。回答只是"持有 / 观望"就不要列。
"""


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    try:
        data = json.loads(match.group()) if match else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def validate_checkpoints(raw: list, stocks_by_code: dict[str, dict],
                         baselines: dict[str, dict[str, tuple[float, str]]], today: date) -> list[dict]:
    """模型提的验证点逐条过代码校验；不合规的直接丢弃，不修补。"""
    metrics = allowed_metrics()
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        code, metric, op = str(item.get("code", "")), str(item.get("metric", "")), str(item.get("op", ""))
        if code not in stocks_by_code or metric not in metrics or op not in (">=", "<=") or (code, metric) in seen:
            continue
        try:
            threshold = float(item["threshold"])
        except (KeyError, TypeError, ValueError):
            continue
        baseline = baselines.get(code, {}).get(metric)
        if baseline is None:  # 现在都取不到这个数，以后也没法核对
            continue
        group = metrics[metric][1]
        if metric.endswith("percentile") and not 0 <= threshold <= 100:
            continue
        if abs(threshold) > 1000 or sum(1 for c, _ in seen if c == code) >= MAX_PER_STOCK:
            continue
        due = ""
        if group != "financial":
            try:
                horizon = int(item.get("horizon_days") or 60)
            except (TypeError, ValueError):
                horizon = 60
            due = str(today + timedelta(days=max(20, min(horizon, 180))))
        seen.add((code, metric))
        out.append({"code": code, "name": stocks_by_code[code].get("name", ""), "metric": metric, "op": op,
                    "threshold": threshold, "statement": str(item.get("statement") or "").strip()[:120],
                    "baseline_value": baseline[0], "baseline_as_of": baseline[1], "due_date": due})
        if len(out) >= MAX_TOTAL:
            break
    return out


def validate_proposals(raw: list, stocks_by_code: dict[str, dict], holdings: list[PortfolioHolding]) -> list[dict]:
    held = {h.fund_code: h.shares for h in holdings}
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        code, action = str(item.get("code", "")), str(item.get("action", ""))
        if code not in stocks_by_code or action not in ACTIONS or any(p["code"] == code for p in out):
            continue
        if action in ("reduce", "sell") and held.get(code, 0) <= 0:
            continue  # 没持有就谈不上减仓
        shares = item.get("shares")
        shares = int(shares) if isinstance(shares, (int, float)) and shares > 0 and int(shares) % 100 == 0 else None
        if shares and action in ("reduce", "sell"):
            shares = min(shares, int(held[code]))
        out.append({"code": code, "name": stocks_by_code[code].get("name", ""),
                    "asset_type": stocks_by_code[code].get("asset_type", "stock"), "action": action, "shares": shares,
                    "reason": str(item.get("reason") or "").strip()[:200],
                    "invalidation": str(item.get("invalidation") or "").strip()[:200]})
    return out


async def create_from_research(
    db: Session, client, model: str, *, user_id: int, message_id: int | None, question: str, playbook: str,
    answer: str, securities: list[dict], holdings: list[PortfolioHolding],
) -> tuple[list[Checkpoint], list[TradeProposal]]:
    """研究发布后调用一次：取基准值 → 模型提出 → 代码校验 → 落库。任何一步失败都返回空，不影响研究本身。"""
    targets = {s["code"]: s for s in securities if s.get("asset_type", "stock") in ("stock", "etf")}
    targets = dict(list(targets.items())[:3])
    if not targets:
        return [], []
    values = await asyncio.gather(*[current_values(code) for code in targets])
    baselines = {code: v for code, v in zip(targets, values, strict=True) if v}
    if not baselines:
        return [], []

    metrics = allowed_metrics()
    advice = get_settings().advice_mode
    lines = []
    for code, vals in baselines.items():
        lines.append(f"### {targets[code].get('name', '')}（{code}）可用指标与当前值")
        lines += [f"- {m}（{metrics[m][0]}，{metrics[m][1]}）：当前 {v}（{as_of}）" for m, (v, as_of) in vals.items() if m in metrics]
    prompt = f"用户问题：{question}\n\n已发布的回答：\n{answer[:6000]}\n\n" + "\n".join(lines)
    system = _PROPOSE_SYSTEM.format(
        advice=_ADVICE_RULES if advice else "",
        proposal_shape=',"proposals":[{"code":"600519","action":"add","shares":100,"reason":"...","invalidation":"..."}]' if advice else "")
    result = await asyncio.to_thread(client.create, model=model, max_tokens=4000, system=system,
                                     messages=[{"role": "user", "content": prompt}], **json_mode(client))
    data = _parse_json(result.text)

    today = date.today()
    checkpoints = [Checkpoint(user_id=user_id, message_id=message_id, question=question[:200], playbook=playbook, **c)
                   for c in validate_checkpoints(data.get("checkpoints"), targets, baselines, today)]
    proposals: list[TradeProposal] = []
    if advice:
        for p in validate_proposals(data.get("proposals"), targets, holdings):
            quote = await stocks.fetch_stock_quote(p["code"])
            proposals.append(TradeProposal(user_id=user_id, message_id=message_id,
                                           price_ref=(quote or {}).get("price"), **p))
    for row in (*checkpoints, *proposals):
        db.add(row)
    db.commit()
    for row in (*checkpoints, *proposals):
        db.refresh(row)
    return checkpoints, proposals


# ── 到期核对 ────────────────────────────────────────────

def _judge(op: str, actual: float, threshold: float) -> str:
    return "held" if (actual >= threshold if op == ">=" else actual <= threshold) else "broken"


def _period_return(kline: list[dict], start: str, end: str) -> tuple[float, str] | None:
    """前复权日线上，start 当日（或之前最近一日）收盘到 end 当日（或之前最近一日）收盘的涨跌幅。"""
    rows = sorted(kline, key=lambda r: r["nav_date"])
    before_start = [r for r in rows if r["nav_date"] <= start]
    before_end = [r for r in rows if r["nav_date"] <= end]
    if not before_start or not before_end or before_end[-1]["nav_date"] <= before_start[-1]["nav_date"]:
        return None
    return round((before_end[-1]["nav"] / before_start[-1]["nav"] - 1) * 100, 2), before_end[-1]["nav_date"]


async def _actual(cp: Checkpoint, today: date) -> tuple[float, str] | None | str:
    """返回 (实际值, 数据日期)；还不能核对返回 None；确定核对不了返回 'unverifiable'。"""
    group = METRICS[cp.metric][1]
    if group == "financial":
        reports = await stocks.fetch_financial_indicators(cp.code, 8)
        newer = sorted((r for r in reports if r["report_date"] > cp.baseline_as_of and r.get(cp.metric) is not None),
                       key=lambda r: r["report_date"])
        if newer:  # 取紧接着的下一期，而不是最新一期
            return float(newer[0][cp.metric]), newer[0]["report_date"]
        try:
            age = (today - date.fromisoformat(cp.baseline_as_of[:10])).days
        except ValueError:
            age = 0
        return "unverifiable" if age > _FINANCIAL_GIVE_UP_DAYS else None
    if not cp.due_date or str(today) < cp.due_date:
        return None
    overdue = (today - date.fromisoformat(cp.due_date)).days > 45
    if group == "valuation":
        summary = stocks.summarize_valuation(await stocks.fetch_valuation_history(cp.code))
        value = (summary.get("pe" if cp.metric == "pe_percentile" else "pb") or {}).get("percentile")
        if value is None:
            return "unverifiable" if overdue else None
        return float(value), summary.get("as_of") or str(today)
    days = min(500, int((today - date.fromisoformat(cp.baseline_as_of[:10])).days * 0.75) + 15)
    own = _period_return(await stocks.fetch_stock_kline(cp.code, days), cp.baseline_as_of, cp.due_date)
    if own is None:
        return "unverifiable" if overdue else None
    if cp.metric == "return_pct":
        return own
    bench = _period_return(await stocks.fetch_stock_kline(BENCHMARK, days), cp.baseline_as_of, cp.due_date)
    if bench is None:
        return "unverifiable" if overdue else None
    return round(own[0] - bench[0], 2), own[1]


async def verify_pending(db: Session, user_id: int, *, force: bool = False, today: date | None = None) -> dict:
    """核对该用户所有未决的验证点。默认 6 小时内只跑一次（force 可跳过）。"""
    key = f"checkpoints:verified:{user_id}"
    if not force and cache.read(key, 6 * cache.HOUR):
        return {"checked": 0, "held": 0, "broken": 0, "skipped": True}
    today = today or date.today()
    pending = db.exec(select(Checkpoint).where(Checkpoint.user_id == user_id, Checkpoint.status == "pending")).all()
    counts = {"checked": 0, "held": 0, "broken": 0, "unverifiable": 0}
    verified: list[Checkpoint] = []
    for cp in pending:
        try:
            outcome = await _actual(cp, today)
        except Exception:  # noqa: BLE001 — 一条取数失败不该中断其余的核对，下次再试
            continue
        if outcome is None:
            continue
        if outcome == "unverifiable":
            cp.status = "unverifiable"
            counts["unverifiable"] += 1
        else:
            cp.actual_value, cp.actual_as_of = outcome
            cp.status = _judge(cp.op, cp.actual_value, cp.threshold)
            counts[cp.status] += 1
        cp.checked_at = datetime.now()
        counts["checked"] += 1
        db.add(cp)
        verified.append(cp)
    db.commit()
    for cp in verified:
        memory.record(db, user_id, "checkpoint/verified", f"{cp.name} {METRICS.get(cp.metric, (cp.metric,))[0]}：{cp.status}",
                      {"id": cp.id, "code": cp.code, "status": cp.status, "actual": cp.actual_value, "as_of": cp.actual_as_of})
    cache.write(key, {"at": str(today)})
    return counts


# ── 读取、成绩单、带回给下一次研究 ──────────────────────

def serialize(cp: Checkpoint) -> dict:
    label, group = METRICS.get(cp.metric, (cp.metric, ""))
    return {
        "id": cp.id, "message_id": cp.message_id, "question": cp.question, "playbook": cp.playbook,
        "code": cp.code, "name": cp.name, "metric": cp.metric, "metric_label": label, "group": group,
        "op": cp.op, "threshold": cp.threshold, "statement": cp.statement,
        "baseline_value": cp.baseline_value, "baseline_as_of": cp.baseline_as_of,
        "due": cp.due_date or "下一期财报", "due_date": cp.due_date, "status": cp.status,
        "actual_value": cp.actual_value, "actual_as_of": cp.actual_as_of,
        "checked_at": cp.checked_at.isoformat() if cp.checked_at else None, "created_at": cp.created_at.isoformat(),
    }


def serialize_proposal(p: TradeProposal) -> dict:
    return {
        "id": p.id, "message_id": p.message_id, "code": p.code, "name": p.name, "asset_type": p.asset_type,
        "action": p.action, "action_label": ACTIONS.get(p.action, p.action), "shares": p.shares,
        "price_ref": p.price_ref, "reason": p.reason, "invalidation": p.invalidation, "status": p.status,
        "exec_shares": p.exec_shares, "exec_price": p.exec_price,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None, "created_at": p.created_at.isoformat(),
    }


def list_checkpoints(db: Session, user_id: int, *, code: str = "", status: str = "",
                     message_id: int | None = None, limit: int = 200) -> list[Checkpoint]:
    stmt = select(Checkpoint).where(Checkpoint.user_id == user_id)
    if code:
        stmt = stmt.where(Checkpoint.code == code)
    if status:
        stmt = stmt.where(Checkpoint.status == status)
    if message_id is not None:
        stmt = stmt.where(Checkpoint.message_id == message_id)
    return list(db.exec(stmt.order_by(Checkpoint.created_at.desc()).limit(limit)).all())


def _rate(held: int, broken: int) -> float | None:
    return round(held / (held + broken) * 100, 1) if held + broken else None


def scorecard(db: Session, user_id: int) -> dict:
    """成绩单：只有已核对出结果（成立 / 证伪）的才计入成立率。"""
    rows = list_checkpoints(db, user_id, limit=2000)
    count = lambda items, s: sum(1 for c in items if c.status == s)  # noqa: E731
    groups = []
    for group, label in GROUP_LABEL.items():
        items = [c for c in rows if METRICS.get(c.metric, ("", ""))[1] == group]
        if items:
            groups.append({"group": group, "label": label, "total": len(items), "held": count(items, "held"),
                           "broken": count(items, "broken"), "pending": count(items, "pending"),
                           "hold_rate_pct": _rate(count(items, "held"), count(items, "broken"))})
    stocks_seen: dict[str, dict] = {}
    for c in rows:
        s = stocks_seen.setdefault(c.code, {"code": c.code, "name": c.name, "total": 0, "held": 0, "broken": 0, "pending": 0})
        s["total"] += 1
        if c.status in s:
            s[c.status] += 1
    verified = sorted((c for c in rows if c.status in ("held", "broken")), key=lambda c: c.checked_at or c.created_at, reverse=True)
    return {
        "total": len(rows), "held": count(rows, "held"), "broken": count(rows, "broken"),
        "pending": count(rows, "pending"), "unverifiable": count(rows, "unverifiable"),
        "hold_rate_pct": _rate(count(rows, "held"), count(rows, "broken")),
        "by_group": groups, "by_stock": sorted(stocks_seen.values(), key=lambda s: -s["total"])[:20],
        "recent_verified": [serialize(c) for c in verified[:10]],
        "note": "成立率 = 成立 /（成立 + 证伪），未到期和无法核对的不计入；样本少时不具统计意义",
    }


def _describe(cp: Checkpoint) -> str:
    label = METRICS.get(cp.metric, (cp.metric,))[0]
    text = f"{cp.name}（{cp.code}）{label} {cp.op} {cp.threshold:g}，设定时为 {cp.baseline_value:g}（{cp.baseline_as_of}）"
    if cp.status == "held":
        return f"{text} → 已核对：成立，实际 {cp.actual_value:g}（{cp.actual_as_of}）"
    if cp.status == "broken":
        return f"{text} → 已核对：被证伪，实际 {cp.actual_value:g}（{cp.actual_as_of}）"
    return f"{text} → 尚未到核对时点（{cp.due_date or '等下一期财报'}）"


MIN_SAMPLE = 5


def calibration_note(db: Session, user_id: int) -> str:
    """这个 Agent 自己过去的判断，事后核对下来各类对了多少 —— 带进新一轮研究，让它据此收放把握。

    按判断的类型分开说：某一类经常落空，下次同类判断就该更保守。样本不到 5 条的类型不提，免得被两三次偶然带偏。
    """
    lines = []
    for group in scorecard(db, user_id)["by_group"]:
        verified, rate = group["held"] + group["broken"], group["hold_rate_pct"]
        if verified < MIN_SAMPLE or rate is None:
            continue
        advice = ("这类判断过去经常落空：这次同类的判断要更保守，结论里写明把握不大" if rate < 50
                  else "这类判断过去大多成立" if rate >= 75 else "这类判断对错参半：结论里要写明不确定性")
        lines.append(f"- {group['label']}类：已核对 {verified} 条，成立 {group['held']} 条（{rate:g}%）。{advice}。")
    if not lines:
        return ""
    return "你过去的判断事后核对的结果（据此校准这一次的把握程度，不必在回答里复述）：\n" + "\n".join(lines) + "\n\n"


def prior_note(db: Session, user_id: int, codes: list[str]) -> str:
    """此前研究给这些股票设过的验证点及结果，带给新一轮研究。"""
    if not codes:
        return ""
    rows = db.exec(select(Checkpoint).where(Checkpoint.user_id == user_id, Checkpoint.code.in_(codes),
                                            Checkpoint.status != "unverifiable")
                   .order_by(Checkpoint.created_at.desc()).limit(8)).all()
    if not rows:
        return ""
    return ("此前的研究为这些股票设过的验证点及核对结果（已被证伪的，本次回答必须正面回应：原判断错在哪、结论是否因此改变；尚未到核对时点的不必逐条复述）：\n"
            + "\n".join(f"- {_describe(c)}" for c in rows) + "\n\n")
