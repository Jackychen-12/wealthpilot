"""模拟盘、持仓同步、每日盯盘、财报正文摘录、选股回测。不联网、不调模型。"""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wealthpilot.main import app
from wealthpilot.models.broker import Digest, Order, PaperAccount, PaperPosition
from wealthpilot.models.portfolio import PortfolioHolding
from wealthpilot.models.research import DataCache, WatchItem
from wealthpilot.models.review import Checkpoint, TradeProposal
from wealthpilot.services import broker, filings, screener, stocks, watcher
from wealthpilot.storage.db import get_engine

UID = 42


@pytest.fixture
def db(monkeypatch):
    with TestClient(app):
        pass
    price = {"600519": 1250.0, "300750": 290.0}

    async def quote(code):
        return {"name": {"600519": "贵州茅台", "300750": "宁德时代"}.get(code, code), "price": price[code]} if code in price else None

    async def profile(code):
        return {"industry": "白酒Ⅱ"}

    monkeypatch.setattr(broker, "fetch_stock_quote", quote)
    monkeypatch.setattr(broker, "fetch_stock_profile", profile)
    monkeypatch.setattr(broker, "get_settings", lambda: SimpleNamespace(broker="paper", paper_initial_cash=300_000))
    with Session(get_engine()) as session:
        for model in (Order, PaperAccount, PaperPosition, Digest, DataCache, WatchItem, Checkpoint, TradeProposal, PortfolioHolding):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()
        session.price = price
        yield session


async def test_paper_orders_follow_a_share_rules(db):
    day1 = date.today()
    day2 = day1 + timedelta(days=1)
    place = lambda **kw: broker.place_order(db, UID, **kw)  # noqa: E731
    assert (await place(code="600519", side="buy", shares=150, today=day1)).reason == "买入数量必须是 100 股的整数倍"
    assert "资金不足" in (await place(code="600519", side="buy", shares=300, today=day1)).reason
    assert "取不到最新价" in (await place(code="000001", side="buy", shares=100, today=day1)).reason

    bought = await place(code="600519", side="buy", shares=200, today=day1)
    assert (bought.status, bought.price, bought.amount, bought.fee) == ("filled", 1250.0, 250_000.0, 62.5)
    assert broker.get_account(db, UID).cash == 300_000 - 250_000 - 62.5

    # T+1：当天买的当天不能卖；第二天可以，卖出另收印花税
    assert "可卖 0 股" in (await place(code="600519", side="sell", shares=100, today=day1)).reason
    db.price["600519"] = 1300.0
    sold = await place(code="600519", side="sell", shares=100, today=day2)
    assert (sold.status, sold.fee) == ("filled", round(130_000 * 0.00025 + 130_000 * 0.0005, 2))
    assert "可卖数量不足" in (await place(code="600519", side="sell", shares=500, today=day2)).reason


async def test_sync_only_touches_broker_sourced_holdings(db):
    db.add(PortfolioHolding(user_id=UID, asset_type="fund", fund_code="110011", fund_name="易方达优质精选", shares=1000, cost_price=4.0, buy_date=date(2025, 1, 1)))
    db.add(PortfolioHolding(user_id=UID, asset_type="stock", fund_code="300750", fund_name="宁德时代", shares=100, cost_price=260.0, buy_date=date(2025, 1, 1)))
    db.commit()
    await broker.place_order(db, UID, code="600519", side="buy", shares=100, today=date(2026, 10, 8))
    await broker.place_order(db, UID, code="300750", side="buy", shares=100, today=date(2026, 10, 8))
    first = await broker.sync_holdings(db, UID)
    assert (first["added"], len(first["skipped"])) == (1, 1)   # 宁德时代已有手工记录，不覆盖
    rows = {h.fund_code: h for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == UID)).all()}
    assert (rows["600519"].source, rows["600519"].industry, rows["300750"].source, rows["110011"].shares) == ("broker", "白酒Ⅱ", "", 1000)

    broker.reset(db, UID)
    assert (await broker.sync_holdings(db, UID))["removed"] == 1
    left = {h.fund_code for h in db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == UID)).all()}
    assert left == {"110011", "300750"}   # 手工录入的原样保留


def test_authorizing_with_paper_broker_places_an_order(db, monkeypatch):
    db.add(TradeProposal(user_id=0, code="600519", name="贵州茅台", action="buy", shares=100))
    db.commit()
    with TestClient(app) as client:
        pid = client.get("/api/proposals").json()[0]["id"]
        assert "买入数量必须是 100 股" in client.post(f"/api/proposals/{pid}/authorize", json={"shares": 50}).json()["detail"]
        done = client.post(f"/api/proposals/{pid}/authorize", json={"shares": 100}).json()
        assert (done["status"], done["exec_price"]) == ("executed", 1250.0)   # 成交价来自行情，不是用户填的
        orders = client.get("/api/broker/orders").json()
        assert [o["status"] for o in orders] == ["filled", "rejected"] and orders[0]["proposal_id"] == pid
        held = [h for h in client.get("/api/portfolio").json() if h["fund_code"] == "600519"]
        assert held and held[0]["shares"] == 100
    # 没开模拟盘时，下单接口直接拒绝
    monkeypatch.setattr(broker, "enabled", lambda: False)
    with TestClient(app) as client:
        assert client.post("/api/broker/orders", json={"code": "600519", "side": "buy", "shares": 100}).status_code == 409


async def test_watcher_reports_only_what_changed_since_last_run(db, monkeypatch):
    db.add(WatchItem(user_id=UID, code="600519", name="贵州茅台", asset_type="stock"))
    db.commit()
    world = {"report": "2026-06-30", "pe": 10.0, "filings": [{"art_code": "AN2026081400000001", "date": "2026-08-15", "title": "半年度报告", "category": "半年度报告全文", "url": "u"}],
             "change": 1.0}

    async def indicators(code, periods=1):
        return [{"report_date": world["report"], "report_name": "2026三季报" if world["report"] > "2026-07" else "2026中报",
                 "revenue_yoy_pct": 3.2, "net_profit_yoy_pct": -1.0}]

    async def valuation(code):
        return [{"x": 1}]

    async def listing(code, limit=15):
        return world["filings"]

    async def quotes(codes):
        return {"600519": {"price": 1250.0, "change_pct": world["change"]}}

    monkeypatch.setattr(stocks, "fetch_financial_indicators", indicators)
    monkeypatch.setattr(stocks, "fetch_valuation_history", valuation)
    monkeypatch.setattr(stocks, "summarize_valuation", lambda h: {"pe": {"percentile": world["pe"]}})
    monkeypatch.setattr(filings, "list_filings", listing)
    monkeypatch.setattr(watcher, "fetch_sina_quotes", quotes)
    monkeypatch.setattr(watcher, "get_settings", lambda: SimpleNamespace(watch_move_pct=5.0, alert_webhook_url="", broker="none"))
    monkeypatch.setattr(watcher.broker, "enabled", lambda: False)

    first = await watcher.run(db, UID, today=date(2026, 10, 8))
    assert first["events"] == [] and "今日无事" in first["summary"]   # 第一次只记基线，不把旧财报当新闻

    world.update(report="2026-09-30", pe=85.0, change=-6.5)
    world["filings"] = [{"art_code": "AN2026102800000009", "date": "2026-10-28", "title": "关于股东减持计划的公告", "category": "其他", "url": "u"},
                        {"art_code": "AN2026102800000008", "date": "2026-10-28", "title": "关于召开投资者交流会的通知", "category": "其他", "url": "u"},
                        *world["filings"]]
    second = await watcher.run(db, UID, today=date(2026, 10, 29))
    kinds = [e["kind"] for e in second["events"]]
    assert kinds == ["report", "filing", "valuation", "move"]          # 不重要的公告被滤掉
    assert "2026三季报" in second["events"][0]["text"] and "减持" in second["events"][1]["text"]
    assert "低位" in second["events"][2]["text"] and "高位" in second["events"][2]["text"]

    world["change"] = 0.3
    third = await watcher.run(db, UID, today=date(2026, 10, 30))
    assert third["events"] == []                                         # 同样的事不重复报
    assert [d["day"] for d in watcher.recent(db, UID)] == ["2026-10-30", "2026-10-29", "2026-10-08"]


def test_report_excerpt_skips_table_of_contents_and_cross_references():
    text = ("重要提示 详见“管理层讨论与分析”章节。\n目录\n第三节 管理层讨论与分析......6\n第四节 公司治理......13\n" + "释义" * 50
            + "\n第三节 管理层讨论与分析\n一、报告期内公司主营业务情况\n公司主要业务是白酒的生产与销售。" + "正文" * 100
            + "\n可能面对的风险\n一是宏观经济风险；二是安全风险。")
    heading, body = filings.excerpt(text, filings.TOPICS["管理层讨论"], size=60)
    assert heading == "管理层讨论与分析" and "公司主要业务是白酒" in body and "......6" not in body
    assert "宏观经济风险" in filings.excerpt(text, filings.TOPICS["风险"])[1]
    assert filings.excerpt(text, filings.TOPICS["展望"]) == ("", "")
    assert filings.is_important({"title": "关于股东减持计划的公告"}) and not filings.is_important({"title": "关于召开投资者交流会的通知"})


def test_roe_is_annualized_for_screening():
    assert screener.annualized_roe({"WEIGHTAVG_ROE": 4.0, "REPORTDATE": "2026-03-31 00:00:00"}) == 16.0
    assert screener.annualized_roe({"WEIGHTAVG_ROE": 9.0, "REPORTDATE": "2026-06-30"}) == 18.0
    assert screener.annualized_roe({"WEIGHTAVG_ROE": 16.0, "REPORTDATE": "2025-12-31"}) == 16.0
    assert screener.annualized_roe({}) is None
    snap = {"stocks": [{"code": "1", "name": "甲", "industry": "", "total_mv_yi": 100, "pe_ttm": 10, "pb": 1, "roe_pct": 9.0, "roe_annual_pct": 18.0,
                        "revenue_yoy_pct": 1, "profit_yoy_pct": 1, "change_pct": 0, "price": 1}]}
    assert screener.screen(snap, {"roe_min": 15})["matched"] == 1    # 中报 ROE 9% 相当于全年 18%


async def test_screen_backtest_uses_point_in_time_picks_and_cash_when_nothing_qualifies(monkeypatch):
    def stock(code, pe):
        return {"code": code, "name": code, "industry": "", "total_mv_yi": 500, "pe_ttm": pe, "pb": 1, "roe_pct": 20, "roe_annual_pct": 20,
                "revenue_yoy_pct": 5, "profit_yoy_pct": 5, "change_pct": 0, "price": 10}

    sections = {"2025-05-06": [stock("AAA", 10), stock("BBB", 30)], "2025-09-03": [stock("AAA", 40), stock("BBB", 40)],
                "2025-11-03": [stock("BBB", 8)]}

    async def cross_section(day):
        return {"trade_date": day, "stocks": sections[day]} if day in sections else {}

    prices = {"AAA": {"2025-05-06": 10, "2025-09-03": 12, "2025-11-03": 6, "2026-03-31": 6},
              "BBB": {"2025-05-06": 10, "2025-09-03": 5, "2025-11-03": 10, "2026-03-31": 11},
              screener.BENCHMARK: {"2025-05-06": 4.0, "2025-09-03": 4.4, "2025-11-03": 4.4, "2026-03-31": 4.4}}

    async def kline(code, days=640):
        return [{"nav_date": d, "nav": v} for d, v in prices[code].items()]

    monkeypatch.setattr(screener, "cross_section", cross_section)
    monkeypatch.setattr("wealthpilot.services.stocks.fetch_stock_kline", kline)
    out = await screener.backtest_screen({"pe_max": 15}, years=1, top_n=3, fee_pct=0, today=date(2026, 4, 1))
    assert [(p["picked"], p["return_pct"], p["benchmark_pct"]) for p in out["periods"]] == [(1, 20.0, 10.0), (0, 0.0, 0.0), (1, 10.0, 0.0)]
    assert (out["total_return_pct"], out["benchmark_return_pct"], out["periods_beating_benchmark"]) == (32.0, 10.0, 2)
    assert any("幸存者偏差" in x for x in out["limitations"])
    json.dumps(out)


def test_desk_puts_what_needs_attention_first_and_thesis_card_reads_the_conclusion(db, monkeypatch):
    from wealthpilot.models.chat import ChatMessage
    from wealthpilot.routes import research

    async def quotes(codes):
        return {"600519": {"price": 1250.0, "change_pct": 1.0}, "300750": {"price": 290.0, "change_pct": -3.0}}

    monkeypatch.setattr(research, "fetch_sina_quotes", quotes)
    for row in db.exec(select(ChatMessage)).all():
        db.delete(row)
    db.add(WatchItem(user_id=0, code="600519", name="贵州茅台", asset_type="stock"))
    db.add(PortfolioHolding(user_id=0, asset_type="stock", fund_code="300750", fund_name="宁德时代", shares=100, cost_price=250.0, buy_date=date(2025, 1, 1)))
    db.add(Checkpoint(user_id=0, code="600519", name="贵州茅台", metric="revenue_yoy_pct", op=">=", threshold=0, status="broken", actual_value=-2.0, actual_as_of="2026-09-30"))
    db.add(ChatMessage(user_id=0, conversation_id="c1", role="assistant",
                       content="## 结论\n增长失速但盈利质量仍高 [E-abcd1234]。\n## 建议\n**立场：中性。**",
                       metadata_json=json.dumps({"status": "passed", "playbook": "stock_deep", "securities": [{"code": "600519", "name": "贵州茅台"}]})))
    db.commit()
    with TestClient(app) as client:
        desk = client.get("/api/desk").json()
        assert [s["code"] for s in desk["stocks"]] == ["600519", "300750"]      # 有被证伪验证点的排在持仓前面
        assert desk["stocks"][1]["return_pct"] == 16.0 and desk["stocks"][1]["last_research"] is None
        assert desk["todo"] == {"proposals": 0, "broken": 1, "pending": 0, "unresearched": 1}
        card = client.get("/api/research/latest", params={"code": "600519"}).json()
        assert card["latest"]["conclusion"] == "增长失速但盈利质量仍高。" and card["latest"]["stance"] == "中性"
        assert card["checkpoints"]["broken"] == 1 and len(card["research_dates"]) == 1
        assert client.get("/api/research/latest", params={"code": "000001"}).json()["latest"] is None


def test_stance_is_read_per_stock_in_a_comparison():
    from wealthpilot.routes.research import _stance
    line = "立场：贵州茅台——看多（持有，不加仓）；五粮液——中性（持有观察）。"
    assert (_stance(line, "贵州茅台"), _stance(line, "五粮液"), _stance("**立场：看空。**"), _stance("没有写")) == ("看多", "中性", "看空", "")
