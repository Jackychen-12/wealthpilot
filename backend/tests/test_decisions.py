"""买入理由记录与按来源对账：记的是人自己写的一句话，算的是之后相对大盘的表现。行情是造的，不联网，不调模型。"""

from datetime import date, timedelta

import pytest
from sqlmodel import Session, select

from wealthpilot.models.decision import Decision
from wealthpilot.services import decisions, glossary, stance
from wealthpilot.storage.db import get_engine


def _days(n, start=date(2026, 1, 5)):
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


DAYS = _days(90)
BENCH = [(d, 4000 * (1 + 0.001 * i)) for i, d in enumerate(DAYS)]            # 大盘每天涨千分之一
SERIES = {"300750": [(d, 100 * (1 + 0.004 * i)) for i, d in enumerate(DAYS)],  # 跑赢大盘
          "600519": [(d, 100 * (1 - 0.002 * i)) for i, d in enumerate(DAYS)],  # 跑输
          "000001": [(d, 100 * (1 - 0.001 * i)) for i, d in enumerate(DAYS)]}


async def kline(code, days):
    series = BENCH if code == stance.BENCHMARK else SERIES.get(code, [])
    return [{"nav_date": d, "nav": v} for d, v in series]


@pytest.fixture
def db():
    with Session(get_engine()) as session:
        yield session
        for row in session.exec(select(Decision)).all():
            session.delete(row)
        session.commit()


def test_a_note_needs_a_stock_and_a_reason_and_the_source_is_put_into_a_few_kinds(db):
    row = decisions.add(db, 5, {"code": "300750", "name": "宁德时代", "reason": "储能订单超预期", "source_kind": "雪球某某", "source_name": "雪球某某", "day": DAYS[0]})
    assert (row.action, row.source_kind, row.source_name) == ("buy", "博主 / 大V", "雪球某某")
    assert decisions.add(db, 5, {"code": "600519", "reason": "朋友说要涨", "source_kind": "朋友", "source_name": "朋友", "day": DAYS[0]}).source_name == ""   # 只写了类别：不当成一个具体的人
    assert decisions.add(db, 5, {"code": "000001", "reason": "看了年报", "day": DAYS[0]}).source_kind == "自己研究"
    assert decisions.add(db, 5, {"code": "000001", "reason": "x", "source_kind": "电梯里听来的", "day": DAYS[0]}).source_kind == "其他"
    for bad in ({"reason": "没写股票"}, {"code": "300750"}, {"code": "300750", "reason": "x", "day": "上周"}, {"code": "300750", "reason": "x", "day": "2999-01-01"}):
        with pytest.raises(ValueError):
            decisions.add(db, 5, bad)
    assert len(decisions.listing(db, 5)) == 4 and decisions.listing(db, 6) == []                 # 各人只看到自己的
    assert decisions.remove(db, 6, row.id) is False and decisions.remove(db, 5, row.id) is True


def test_one_line_notes_are_parsed_the_same_way_in_the_terminal_and_on_the_phone():
    note = decisions.parse_note("宁德时代 储能订单超预期 来自 雪球某某")
    assert note == {"query": "宁德时代", "reason": "储能订单超预期", "source_kind": "雪球某某", "source_name": "雪球某某", "action": "buy"}
    assert decisions.parse_note("600519 清仓 跌破成本线")["action"] == "sell" and decisions.parse_note("茅台 看了年报")["source_kind"] == ""
    for bad in ("宁德时代", "", "宁德时代 来自 朋友"):
        with pytest.raises(ValueError):
            decisions.parse_note(bad)
    assert glossary.COMMAND_WORDS["对账"] == "/why" and glossary.lookup("按来源对账")


async def test_the_reckoning_groups_buys_by_where_the_idea_came_from(db):
    for code, kind, who in (("300750", "自己研究", ""), ("600519", "博主", "某财经博主"), ("000001", "大V", "某财经博主"), ("600519", "朋友", "")):
        decisions.add(db, 9, {"code": code, "reason": "当时的想法", "source_kind": kind, "source_name": who, "day": DAYS[0]})
    decisions.add(db, 9, {"code": "300750", "reason": "止盈", "action": "sell", "day": DAYS[30]})          # 卖出只记不算
    decisions.add(db, 9, {"code": "300750", "reason": "刚买的", "day": DAYS[85]})                          # 还没到期
    report = await decisions.review(db, 9, today=date.fromisoformat(DAYS[-1]), kline=kline)
    groups = {g["source"]: g for g in report["by_source"]}
    assert groups["自己研究"]["count"] == 2 and groups["自己研究"]["d20"] == {"settled": 1, "beat": 1, "avg_excess_pct": groups["自己研究"]["d20"]["avg_excess_pct"]}
    assert groups["自己研究"]["d20"]["avg_excess_pct"] > 0 > groups["博主 / 大V"]["d20"]["avg_excess_pct"]
    assert groups["博主 / 大V"]["d60"] == {"settled": 2, "beat": 0, "avg_excess_pct": groups["博主 / 大V"]["d60"]["avg_excess_pct"]}
    assert [n["source"] for n in report["by_name"]] == ["某财经博主"] and report["by_name"][0]["count"] == 2   # 同一个人两笔以上才单列
    assert "样本太少" in report["note"] and len(report["decisions"]) == 6
    out = decisions.text(report)
    assert "博主 / 大V：2 笔，20 日后2 笔到期，0 笔跑赢" in out and "其中 某财经博主" in out and "沪深 300" in out


async def test_nothing_recorded_or_nothing_due_is_said_plainly(db):
    empty = await decisions.review(db, 11, kline=kline)
    assert empty["by_source"] == [] and "还没有记过" in decisions.text(empty)
    decisions.add(db, 11, {"code": "300750", "reason": "刚买", "day": DAYS[88]})
    fresh = await decisions.review(db, 11, today=date.fromisoformat(DAYS[-1]), kline=kline)
    assert fresh["by_source"][0]["d20"]["settled"] == 0 and "还没满 20 个交易日" in fresh["note"] and "都还没到期" in decisions.text(fresh)

    async def broken(code, days):
        raise RuntimeError("行情接口挂了")
    down = await decisions.review(db, 11, today=date.fromisoformat(DAYS[-1]), kline=broken)       # 行情取不到：不报错，只是没有结果
    assert down["by_source"][0]["d20"]["settled"] == 0


def test_the_api_records_lists_and_deletes(monkeypatch):
    from fastapi.testclient import TestClient

    from wealthpilot.main import app
    client = TestClient(app)
    made = client.post("/api/decisions", json={"code": "300750", "name": "宁德时代", "reason": "储能订单超预期", "source_kind": "券商研报"})
    assert made.status_code == 201 and made.json()["source_kind"] == "券商研报" and made.json()["day"] == date.today().isoformat()
    assert client.post("/api/decisions", json={"code": "300750"}).status_code == 422
    listed = client.get("/api/decisions").json()
    assert listed["decisions"][0]["id"] == made.json()["id"] and "朋友推荐" in listed["source_kinds"]

    async def review(db, user_id, **kw):
        return {"decisions": [], "by_source": [], "by_name": [], "note": "x", "benchmark": "沪深 300"}
    monkeypatch.setattr(decisions, "review", review)
    assert client.get("/api/decisions/review").json()["note"] == "x"
    assert client.delete(f"/api/decisions/{made.json()['id']}").json() == {"ok": True}
    assert client.delete(f"/api/decisions/{made.json()['id']}").status_code == 404


async def test_the_terminal_records_a_note_and_shows_the_reckoning():
    from tests.test_tui import run_api
    report = {"decisions": [{"id": 4, "code": "300750", "name": "宁德时代", "action": "buy", "day": "2026-01-05", "price": None, "reason": "储能订单超预期",
                             "source_kind": "博主 / 大V", "source_name": "雪球某某"}],
              "by_source": [{"source": "博主 / 大V", "count": 1, "d20": {"settled": 1, "beat": 1, "avg_excess_pct": 6.2}, "d60": {"settled": 0, "beat": 0, "avg_excess_pct": None}}],
              "by_name": [], "note": "已经到期的只有 1 笔，样本太少，先看个大概；攒到十笔以上再下结论。", "benchmark": "沪深 300"}
    app_, out = run_api({("GET", "/api/securities/search"): [{"code": "300750", "name": "宁德时代", "asset_type": "stock"}],
                         ("POST", "/api/decisions"): lambda kw: {**kw["json"], "id": 4, "day": "2026-01-05", "source_kind": "博主 / 大V"},
                         ("GET", "/api/decisions/review"): report, ("DELETE", "/api/decisions/4"): {"ok": True}})
    await app_.handle("/why 宁德时代 储能订单超预期 来自 雪球某某")
    sent = app_.backend.sent[-1]
    assert sent[:2] == ("POST", "/api/decisions") and sent[2] == {"code": "300750", "name": "宁德时代", "reason": "储能订单超预期", "source_kind": "雪球某某", "source_name": "雪球某某", "action": "buy"}
    assert "记下了：2026-01-05 买入 宁德时代 —— 储能订单超预期（来源：博主 / 大V）" in out.getvalue()
    await app_.handle("对账")                                          # 中文词直接当命令
    assert "博主 / 大V：1 笔，20 日后1 笔到期，1 笔跑赢，平均超额 +6.2 个百分点，60 日后都还没到期" in out.getvalue() and "雪球某某" in out.getvalue()
    await app_.handle("/why 宁德时代")
    assert "这样记" in out.getvalue()
    await app_.handle("/why rm 4")
    assert app_.backend.sent[-2][:2] == ("DELETE", "/api/decisions/4") and app_.backend.sent[-1][1] == "/api/decisions/review"   # 删完接着给最新的对账
    assert app_.backend.calls == []                                    # 全程不调用模型


async def test_the_phone_records_a_note_in_one_message(db, monkeypatch):
    from wealthpilot.services import channels, securities

    class Sink:
        def __init__(self):
            self.sent = []

        async def send(self, chat_id, text, buttons=None):
            self.sent.append(text)

    async def search(query, limit=10, **kw):
        return [{"code": "300750", "name": "宁德时代", "asset_type": "stock"}] if "宁德" in query else []
    monkeypatch.setattr(securities, "search", search)
    monkeypatch.setattr(decisions, "fetch_stock_kline", kline)
    asked = []

    async def ask(question, history, conversation, depth="auto", **kw):
        asked.append(question)
        yield {"type": "done", "content": "结论", "meta": {"status": "passed"}}
    channels.set_owner("me", "feishu")
    try:
        sink = Sink()
        bot = channels.Bot(sink, ask=ask, channel="feishu")
        await bot.message("me", "记一笔 宁德时代 储能订单超预期 来自 朋友")
        assert "买入 宁德时代 —— 储能订单超预期（来源：朋友推荐）" in sink.sent[-1]
        await bot.message("me", "记一笔 不存在的公司 随便写写")
        assert "没认出是哪只股票" in sink.sent[-1]
        await bot.message("me", "记一笔 宁德时代")
        assert "这样记" in sink.sent[-1]
        await bot.message("me", "为什么 宁德时代 今天跌这么多")              # 这是提问，不是记录
        assert asked == ["为什么 宁德时代 今天跌这么多"]
        assert len(decisions.listing(db, bot.uid)) == 1
    finally:
        channels.set_owner(None, "feishu")


async def test_overseas_buys_are_measured_against_the_same_benchmark_even_on_days_it_was_closed(db):
    hk_days = [d for i, d in enumerate(DAYS) if i % 7 != 3] + ["2026-01-10"]                  # 港股的交易日和 A 股不完全重合，还多一个周六
    hk = sorted((d, 300 * (1 + 0.003 * i)) for i, d in enumerate(sorted(hk_days)))

    async def mixed(code, days):
        series = BENCH if code == stance.BENCHMARK else hk
        return [{"nav_date": d, "nav": v} for d, v in series]
    decisions.add(db, 21, {"code": "00700.HK", "name": "腾讯控股", "reason": "游戏流水好", "source_kind": "朋友", "day": "2026-01-10"})
    report = await decisions.review(db, 21, today=date.fromisoformat(DAYS[-1]), kline=mixed)
    friend = report["by_source"][0]
    assert friend["source"] == "朋友推荐" and friend["d20"]["settled"] == 1 and friend["d20"]["avg_excess_pct"] > 0
    assert "港股、美股也是和沪深 300 比的" in report["note"]
    assert stance.settle("看多", DAYS[0], [(d, v) for d, v in BENCH], BENCH)[20]["excess_pct"] == 0     # A 股自己的日子照旧一天不差
