"""大盘复盘、宏观、反向 DCF、立场成绩单、交易体检：都是取数之后的计算，这里用造的数据把算法钉住。不联网，不调模型。"""

import json
from datetime import date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from wealthpilot.models.chat import ChatMessage
from wealthpilot.services import macro, recap, stance, trades
from wealthpilot.services import valuation_models as vm
from wealthpilot.storage.db import get_engine

# ── 大盘复盘 ────────────────────────────────────────────

UP = {"qdate": 20261008, "pool": [
    {"c": "600825", "n": "新华传媒", "lbc": 8, "fbt": 92500, "zbc": 0, "fund": 3.2e8, "hs": 5.1, "hybk": "文化传媒"},
    {"c": "002058", "n": "紫竹高科", "lbc": 3, "fbt": 93042, "zbc": 1, "fund": 1.4e8, "hs": 3.3, "hybk": "电池"},
    {"c": "002866", "n": "传艺科技", "lbc": 3, "fbt": 100500, "zbc": 0, "fund": 0.9e8, "hs": 8.0, "hybk": "电池"},
    {"c": "002733", "n": "雄韬股份", "lbc": 1, "fbt": 131000, "zbc": 2, "fund": 0.5e8, "hs": 12.0, "hybk": "电池"},
    {"c": "600617", "n": "国新能源", "lbc": 1, "fbt": 94500, "zbc": 0, "fund": 0.7e8, "hs": 2.0, "hybk": "燃气"}]}
REASONS = {"002058": {"reason": "固态电池+锂电池"}, "002866": {"reason": "固态电池+消费电子"}, "002733": {"reason": "固态电池+锂电池+储能"},
           "600617": {"reason": "业绩增长"}, "600825": {"reason": "传媒+国企改革"}}


def _board(broken=3, down=1, prior=(2.0, -1.0, 5.0)):
    return recap.limit_board(UP, {"pool": [{}] * broken}, {"pool": [{}] * down}, {"pool": [{"zdp": v} for v in prior]}, REASONS)


def test_the_ladder_and_seal_rate_are_counted_from_the_pools():
    board = _board()
    assert (board["limit_up"], board["broken"], board["limit_down"], board["first_board"], board["multi_board"], board["max_streak"]) == (5, 3, 1, 2, 3, 8)
    assert board["seal_rate_pct"] == 62.5 and board["yesterday_limit_up_today_pct"] == 2.0
    assert board["ladder"] == [{"boards": 8, "names": ["新华传媒"]}, {"boards": 3, "names": ["紫竹高科", "传艺科技"]}]      # 同一档里先封板的在前
    assert board["stocks"][1]["first_sealed"] == "09:30" and board["stocks"][1]["reason"] == "固态电池+锂电池"


def test_themes_come_from_reasons_and_fall_back_to_industry():
    by_reason = recap.themes(_board()["stocks"])
    assert by_reason[0] == {"theme": "固态电池", "count": 3, "names": ["紫竹高科", "传艺科技", "雄韬股份"], "basis": "涨停原因"}
    assert [t["theme"] for t in by_reason] == ["固态电池", "锂电池"]                              # 只出现一次的不算"集中"
    plain = recap.limit_board(UP, {}, {}, {}, {})["stocks"]
    assert recap.themes(plain) == [{"theme": "电池", "count": 3, "names": ["紫竹高科", "传艺科技", "雄韬股份"], "basis": "所属行业"}]


def test_the_mood_gauge_is_a_fixed_ruler_and_shows_its_numbers():
    cold = recap.gauge({"limit_up": 20, "limit_down": 45, "seal_rate_pct": 50, "yesterday_limit_up_today_pct": -2.5}, {"up": 800, "down": 4300})
    hot = recap.gauge({"limit_up": 110, "limit_down": 2, "seal_rate_pct": 85, "yesterday_limit_up_today_pct": 4.2}, {"up": 4200, "down": 900})
    middling = recap.gauge({"limit_up": 43, "limit_down": 13, "seal_rate_pct": 57.3, "yesterday_limit_up_today_pct": 0.1}, {"up": 1698, "down": 3748})
    assert (cold["label"], hot["label"], middling["label"]) == ("冰点", "高潮", "偏冷")
    assert "涨停 43 只" in middling["basis"] and "跌停 13 只" in middling["basis"] and "上涨家数占比 31.2%" in middling["basis"]
    assert recap.gauge({}, None)["label"] == "一般"                                           # 什么都没取到：不乱说


def test_seats_are_labelled_by_what_the_exchange_discloses():
    assert recap.seat_kind("机构专用") == "机构" and recap.seat_kind("深股通专用") == "北向" and recap.seat_kind("自然人") == "个人"
    assert recap.seat_kind("东方财富证券股份有限公司拉萨团结路第二证券营业部") == "散户集中的营业部"
    assert recap.seat_kind("开源证券股份有限公司西安西大街证券营业部") == "营业部"


def test_recap_text_reads_like_a_briefing_and_says_so_when_closed():
    board = _board()
    report = {"day": "2026-10-08", "indices": [{"name": "上证指数", "change": "-0.79%"}], "breadth": {"up": 1698, "down": 3748, "median_change_pct": -1.0},
              "limits": {k: v for k, v in board.items() if k != "stocks"}, "themes": recap.themes(board["stocks"]),
              "concepts": {"top": [{"name": "固态电池", "change_pct": 1.19}], "bottom": [{"name": "钙钛矿", "change_pct": -5.89}]},
              "billboard": {"count": 49, "institution_net_yi": 19.3, "northbound_net_yi": 9.1, "top_buy": [{"name": "东山精密", "net_yi": 3.7}], "top_sell": [],
                            "seats": [{"seat": "开源证券股份有限公司西安西大街证券营业部", "kind": "营业部", "net_yi": 1.86, "stocks": ["海欣食品"]}]},
              "mood": recap.gauge(board, {"up": 1698, "down": 3748})}
    out = recap.text(report)
    for piece in ("2026-10-08 大盘复盘", "上证指数 -0.79%", "涨停 5（首板 2，连板 3）", "8 连板：新华传媒", "固态电池 3 只", "机构席位合计净买 +19.30 亿", "开源证券西安西大街证券营业部 +1.86 亿"):
        assert piece in out, piece
    assert "休市" in recap.text(None)


# ── 宏观 ────────────────────────────────────────────────

def test_macro_points_skip_gaps_and_keep_a_short_series():
    rows = [{"REPORT_DATE": "2026-09-01 00:00:00", "MAKE_INDEX": 50.1}, {"REPORT_DATE": "2026-08-01 00:00:00", "MAKE_INDEX": None},
            {"REPORT_DATE": "2026-07-01 00:00:00", "MAKE_INDEX": 49.8}]
    point = macro._point(rows, "MAKE_INDEX")
    assert (point["value"], point["as_of"], point["previous"], point["change"]) == (50.1, "2026-09-01", 49.8, 0.3)
    assert [p["date"] for p in point["series"]] == ["2026-07-01", "2026-09-01"] and macro._point([], "X") is None
    snap = {"indicators": [{"key": "pmi", "label": "制造业 PMI", "unit": "", **point}],
            "rates": [{"key": "cn10y", "label": "中国 10 年期国债收益率", "unit": "%", "value": 1.68, "as_of": "2026-09-30", "change": 0.02}],
            "spread": {"label": "中美 10 年期利差", "value": -3.6, "unit": "个百分点"}, "missing": ["社会融资规模（暂时没有接上数据源）"]}
    out = macro.text(snap)
    assert "制造业 PMI 50.1（比上期升 0.3） · 2026-09" in out and "1.68%（比上期升 0.02） · 2026-09-30" in out and "利差 -3.6" in out and "没有的：社会融资规模" in out
    assert "取不到" in macro.text({"indicators": [], "rates": []})


# ── 反向 DCF ────────────────────────────────────────────

ROWS = [{"report_date": "2026-06-30", "net_profit_yi": 460.0}, {"report_date": "2025-12-31", "net_profit_yi": 800.0}, {"report_date": "2025-06-30", "net_profit_yi": 440.0},
        {"report_date": "2024-12-31", "net_profit_yi": 730.0}, {"report_date": "2023-12-31", "net_profit_yi": 670.0}, {"report_date": "2022-12-31", "net_profit_yi": 610.0}]


def test_reverse_dcf_recovers_the_growth_that_was_put_in():
    cap = vm.present_value(100, 0.12, 0.09)                   # 先按 12% 的增长正着算出一个"市值"
    assert vm.implied_growth(cap, 100, 0.09) == pytest.approx(0.12, abs=1e-6)       # 反着解，得回 12%
    assert vm.implied_growth(cap, 100, 0.10) > 0.12 > vm.implied_growth(cap, 100, 0.08)      # 折现率越高，需要的增长越高
    assert vm.implied_growth(cap, -5, 0.09) is None and vm.implied_growth(1e9, 1, 0.09) is None   # 亏损、或贵到模型解释不了：不硬算


def test_reverse_dcf_uses_the_last_four_quarters_and_compares_with_the_past():
    assert vm.ttm_profit(ROWS) == (820.0, "截至 2026-06-30 的近四个季度") and vm.ttm_profit(ROWS[1:]) == (800.0, "2025 年报")
    assert vm.ttm_profit(ROWS[:2]) is None                                           # 缺去年同期：拼不出来就不拼
    assert vm.annual_cagr(ROWS) == pytest.approx((800 / 610) ** (1 / 3) - 1)
    out = vm.reverse_dcf(15700, ROWS, name="贵州茅台", industry="白酒")
    assert out["ok"] and out["profit_ttm_yi"] == 820.0 and out["pe_ttm"] == 19.1 and [i["discount_pct"] for i in out["implied_growth"]] == [8.0, 9.0, 10.0]
    growths = [i["growth_pct"] for i in out["implied_growth"]]
    assert growths == sorted(growths) and out["past_profit_cagr_3y_pct"] == 9.5
    assert out["scenarios"]["rows"][0]["value_vs_market_cap"] < 1 < out["scenarios"]["rows"][-1]["value_vs_market_cap"]
    assert "不是目标价" in out["notes"][0] and any("过去三年" in n and "市场在为放缓定价" in n for n in out["notes"])
    assert any("金融类公司" in n for n in vm.reverse_dcf(15700, ROWS, industry="银行")["notes"])
    loss = vm.reverse_dcf(100, [{"report_date": "2025-12-31", "net_profit_yi": -3.0}])
    assert loss["ok"] is False and "亏损" in loss["reason"] and vm.reverse_dcf(0, ROWS)["ok"] is False


# ── 立场成绩单 ──────────────────────────────────────────

def _days(n, start=date(2026, 1, 5)):
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


DAYS = _days(80)
BENCH = [(d, 4000 * (1 + 0.001 * i)) for i, d in enumerate(DAYS)]            # 大盘每天涨千分之一
STRONG = [(d, 100 * (1 + 0.004 * i)) for i, d in enumerate(DAYS)]            # 这只每天涨千分之四


def test_a_stance_is_right_only_if_it_beats_or_trails_the_market_the_way_it_said():
    bull = stance.settle("看多", DAYS[0], STRONG, BENCH)
    assert bull[5]["settled"] and bull[5]["right"] and bull[5]["excess_pct"] == pytest.approx(2.0 - 0.5, abs=0.01) and bull[5]["from"] == DAYS[0]
    assert stance.settle("看空", DAYS[0], STRONG, BENCH)[20]["right"] is False              # 说看空，结果跑赢了大盘：错
    assert stance.settle("中性", DAYS[0], STRONG, BENCH)[5]["right"] and not stance.settle("中性", DAYS[0], STRONG, BENCH)[60]["right"]   # 差距超过 5 个点就不算中性
    late = stance.settle("看多", DAYS[70], STRONG, BENCH)
    assert late[5]["settled"] and not late[20]["settled"] and not late[60]["settled"]      # 没到日子的不提前下结论
    weekend = stance.settle("看多", "2026-01-10", STRONG, BENCH)                           # 周六问的：从下一个交易日算
    assert weekend[5]["from"] == "2026-01-12"


async def test_the_scorecard_counts_only_real_stances_and_admits_small_samples():
    def add(db, code, name, text, when, status="passed", securities=None):
        meta = {"status": status, "summary": {"conclusion": "x", "stance": text}, "securities": securities or [{"code": code, "name": name, "asset_type": "stock"}]}
        db.add(ChatMessage(user_id=77, conversation_id="c-stance", role="assistant", content="…", metadata_json=json.dumps(meta, ensure_ascii=False),
                           created_at=datetime.fromisoformat(when + "T10:00:00")))
    with Session(get_engine()) as db:
        add(db, "600519", "贵州茅台", "看多", DAYS[0])
        add(db, "600519", "贵州茅台", "看空", DAYS[0])                      # 同一天又问了一次：以后一次为准
        add(db, "300750", "宁德时代", "看空", DAYS[2])
        add(db, "000001", "平安银行", "", DAYS[3])                          # 没给立场：不算
        add(db, "600036", "招商银行", "看多", DAYS[3], status="rejected")   # 没发布的：不算
        add(db, "x", "对比", "看多", DAYS[3], securities=[{"code": "600519"}, {"code": "000858"}])   # 一次看两只：分不清说的是谁，不算
        db.commit()

    async def kline(code, days):
        series = BENCH if code == stance.BENCHMARK else STRONG
        return [{"nav_date": d, "nav": v} for d, v in series]
    try:
        with Session(get_engine()) as db:
            card = await stance.scorecard(db, 77, today=date(2026, 5, 1), kline=kline)
        assert card["total"] == 2 and {c["code"]: c["stance"] for c in card["calls"]} == {"600519": "看空", "300750": "看空"}
        five = card["horizons"][5]
        assert (five["settled"], five["right"], five["hit_rate_pct"], five["看空_count"]) == (2, 0, 0.0, 2) and five["看空_avg_excess_pct"] > 0
        assert "样本太少" in card["note"]
        out = stance.text(card)
        assert "方向正确 0 条（胜率 0%）" in out and "看空的 2 只平均超额收益 +" in out and "样本太少" in out
        with Session(get_engine()) as db:
            empty = await stance.scorecard(db, 78, kline=kline)
        assert empty["total"] == 0 and "个人模式" in stance.text(empty)
    finally:
        with Session(get_engine()) as db:
            for row in db.exec(select(ChatMessage).where(ChatMessage.user_id == 77)).all():
                db.delete(row)
            db.commit()


# ── 交易体检 ────────────────────────────────────────────

CSV = """成交日期,证券代码,证券名称,操作,成交均价,成交数量,成交金额
20260112,600001,追高股,证券买入,13.00,1000,13000
20260114,600001,追高股,证券卖出,12.00,1000,12000
20260115,600002,摊平股,证券买入,20.00,500,10000
20260126,600002,摊平股,证券买入,18.00,500,9000
20260205,600002,摊平股,证券买入,16.00,500,8000
20260216,600002,摊平股,证券买入,14.50,500,7250
20260305,600002,摊平股,证券卖出,13.00,2000,26000
20260120,600003,赚钱股,买入,10.00,1000,10000
20260122,600003,赚钱股,卖出,10.60,1000,10600
20260121,600003,赚钱股,红利入账,0,0,120
"""


def _series(prices_by_day):
    return [{"nav_date": d, "nav": v} for d, v in prices_by_day]


async def _kline(code, days):
    days_ = _days(70, date(2025, 12, 22))
    if code == "600001":       # 买入前五天从 10 涨到 12.5，之后阴跌
        return _series([(d, 10.0 if i < 10 else min(12.5, 10 + (i - 9) * 0.5) if i < 15 else 12.5 - (i - 15) * 0.05) for i, d in enumerate(days_)])
    if code == "600003":       # 卖出之后又涨了一大截
        return _series([(d, 10.0 + max(0, i - 22) * 0.15) for i, d in enumerate(days_)])
    return _series([(d, 20.0 - i * 0.1) for i, d in enumerate(days_)])


def test_broker_exports_and_hand_typed_lines_are_both_understood():
    parsed = trades.parse(CSV)
    assert len(parsed["trades"]) == 9 and parsed["problems"] == []                       # 红利那一行不是买卖，跳过，也不算认不出来
    assert parsed["trades"][0] == {"date": "2026-01-12", "code": "600001", "name": "追高股", "side": "buy", "price": 13.0, "shares": 1000.0}
    typed = trades.parse("日期 代码 方向 价格 数量\n2026-01-12 600001 买 13 1000\n2026/01/14 600001 卖 12 1000\n这一行是乱写的")
    assert [t["side"] for t in typed["trades"]] == ["buy", "sell"] and len(typed["problems"]) == 1 and "乱写" in typed["problems"][0]
    assert trades.parse("")["problems"] == ["没有内容"]


def test_round_trips_are_matched_first_in_first_out():
    closed, adds = trades.round_trips(trades.parse(CSV)["trades"])
    assert len(closed) == 6 and sum(c["shares"] for c in closed if c["code"] == "600002") == 2000
    first = next(c for c in closed if c["code"] == "600002")
    assert (first["bought"], first["buy_price"], first["sell_price"], first["return_pct"]) == ("2026-01-15", 20.0, 13.0, -35.0)
    assert [a["below_cost_pct"] for a in adds] == [-10.0, -15.79, pytest.approx(-19.44, abs=0.01)]       # 每次加仓都在成本下方，而且越补越低


async def test_the_check_names_the_habits_with_numbers_and_examples():
    report = await trades.check(CSV, kline=_kline, today=date(2026, 4, 1))
    by_key = {f["key"]: f for f in report["findings"]}
    assert report["ok"] and report["trades"] == 9 and report["stocks"] == 3 and report["closed"] == 6
    # 6 次买入里只有 1 次追高：把那一次点出来，但不说成"毛病" —— 要占到三成才算反复出现
    assert not by_key["chasing"]["flag"] and "6 次买入里有 1 次（17%）" in by_key["chasing"]["text"] and "追高股 买入前 5 日 +25.0%" in by_key["chasing"]["examples"][0]
    assert by_key["averaging_down"]["flag"] and "3 次加仓里有 3 次" in by_key["averaging_down"]["text"]
    assert by_key["disposition"]["flag"] and "盈利的 1 笔持有天数的中位数是 2 天，亏损的 5 笔是 28 天——赚的急着卖，亏的一直拿着。" in by_key["disposition"]["text"]
    assert by_key["payoff"]["flag"] and "胜率 17%" in by_key["payoff"]["text"]
    assert report["worst_stocks"][0]["name"] == "摊平股" and report["worst_stocks"][0]["pnl"] == -8250.0
    out = trades.text(report)
    assert "需要留意：亏损加仓、处置效应、胜率和盈亏比" in out and "· 追涨：" in out and "! 亏损加仓：" in out
    assert "亏得最多的：摊平股 -8,250 元" in out and "不评价选股" in out


async def test_too_few_trades_or_missing_prices_are_said_plainly():
    few = await trades.check("2026-01-12 600001 买 13 1000\n2026-01-14 600001 卖 12 1000", kline=_kline)
    assert few["ok"] is False and "不到 4 笔" in few["reason"]

    async def nothing(code, days):
        return []
    report = await trades.check(CSV, kline=nothing, today=date(2026, 4, 1))
    assert report["ok"] and report["missing_prices"] == ["600001", "600002", "600003"] and "chasing" not in {f["key"] for f in report["findings"]}
    assert "没取到行情" in trades.text(report)


# ── 接到工具、接口、命令、推送上 ─────────────────────────

RECAP = {"day": "2026-10-08", "indices": [{"name": "上证指数", "change": "-0.79%"}], "breadth": {"up": 1698, "down": 3748, "median_change_pct": -1.0},
         "limits": {"limit_up": 5, "broken": 3, "limit_down": 1, "seal_rate_pct": 62.5, "first_board": 2, "multi_board": 3, "max_streak": 8,
                    "ladder": [{"boards": 8, "names": ["新华传媒"]}], "yesterday_limit_up_today_pct": 2.0, "yesterday_limit_up_count": 3},
         "limit_up_stocks": [{"code": "002058", "name": "紫竹高科", "streak": 3, "reason": "固态电池+锂电池", "industry": "电池"}],
         "themes": [{"theme": "固态电池", "count": 3, "names": ["紫竹高科"], "basis": "涨停原因"}], "concepts": None, "billboard": None,
         "mood": {"label": "一般", "points": 0, "basis": ["涨停 5 只"]}}


def _patch_recap(monkeypatch, report=RECAP):
    async def build(day=None):
        return report
    monkeypatch.setattr(recap, "build", build)


async def test_agents_get_the_new_tools_with_their_caveats(monkeypatch):
    from wealthpilot.services.agents import depth_tools, registry
    from wealthpilot.services.agents.tools import AGENT_TOOLS, execute_tool
    names = lambda agent: {t["name"] for t in AGENT_TOOLS[agent]}  # noqa: E731
    assert "compute_reverse_dcf" in names("valuation") and {"get_market_recap", "get_macro_indicators", "get_concept_boards", "get_concept_stocks"} <= names("industry")
    assert "不得把它或情景表里的倍数说成目标价" in registry.build_prompt("valuation", [], {}, None, True)
    assert "不得据此预测明天涨跌" in registry.build_prompt("industry", [], {}, None, True)
    _patch_recap(monkeypatch)
    out = json.loads(await execute_tool("get_market_recap", {}, [], {}))
    assert out["limits"]["limit_up"] == 5 and "不是预测" in out["note"] and out["themes"][0]["theme"] == "固态电池"
    _patch_recap(monkeypatch, None)
    assert (await execute_tool("get_market_recap", {}, [], {})).startswith("未获取到")

    async def quote(code):
        return {"name": "贵州茅台", "price": 1250.0, "total_mv_yi": 15700.0}

    async def indicators(code, periods=8):
        return ROWS

    async def profile(code):
        return {"industry": "白酒"}
    monkeypatch.setattr(depth_tools, "fetch_stock_quote", quote)
    monkeypatch.setattr(depth_tools, "fetch_financial_indicators", indicators)
    monkeypatch.setattr(depth_tools, "fetch_stock_profile", profile)
    dcf = json.loads(await execute_tool("compute_reverse_dcf", {"code": "sh600519"}, [], {}))
    assert dcf["code"] == "600519" and dcf["ok"] and dcf["implied_growth"][1]["discount_pct"] == 9.0 and "不是目标价" in dcf["notes"][0]

    async def losing(code, periods=8):
        return [{"report_date": "2025-12-31", "net_profit_yi": -2.0}]
    monkeypatch.setattr(depth_tools, "fetch_financial_indicators", losing)
    assert "亏损" in await execute_tool("compute_reverse_dcf", {"code": "600519"}, [], {})

    async def boards():
        return [{"node": "gn_a", "name": "固态电池", "stocks": 40, "change_pct": 1.2, "leader": {"code": "002058", "name": "紫竹高科", "change_pct": 10.0}},
                {"node": "gn_b", "name": "钙钛矿", "stocks": 30, "change_pct": -5.9, "leader": {"code": "1", "name": "x", "change_pct": 0.1}}]
    monkeypatch.setattr(recap, "concept_boards", boards)
    ranked = json.loads(await execute_tool("get_concept_boards", {"top": 1}, [], {}))
    assert ranked["top"][0]["name"] == "固态电池" and ranked["bottom"][0]["name"] == "钙钛矿" and "node" not in ranked["top"][0]

    async def none(name, limit=40):
        return None
    monkeypatch.setattr(recap, "concept_stocks", none)
    assert "get_concept_boards" in await execute_tool("get_concept_stocks", {"name": "不存在的题材"}, [], {})


def test_routes_and_commands(monkeypatch):
    import argparse

    from fastapi.testclient import TestClient

    from wealthpilot import cli
    from wealthpilot.main import app
    client = TestClient(app)
    _patch_recap(monkeypatch)
    assert client.get("/api/market/recap").json()["limits"]["max_streak"] == 8
    out: list[str] = []
    assert cli.cmd_recap(argparse.Namespace(), out=out.append) == 0 and "8 连板：新华传媒" in out[0]
    _patch_recap(monkeypatch, None)
    assert client.get("/api/market/recap").status_code == 404 and cli.cmd_recap(argparse.Namespace(), out=out.append) == 1

    async def check(text, **kw):
        return {"ok": False, "reason": "认出来的成交不到 4 笔，看不出规律。", "problems": [], "trades": 0}
    monkeypatch.setattr(trades, "check", check)
    assert client.post("/api/trades/check", json={"text": "x"}).json()["ok"] is False
    assert client.get("/api/stances").json()["total"] >= 0


async def test_the_stateless_daily_brief_needs_no_database_and_skips_holidays(monkeypatch):
    from wealthpilot import cli
    from wealthpilot.services import channels
    _patch_recap(monkeypatch)

    async def find(word, limit=1):
        return {"茅台": [{"code": "600519", "name": "贵州茅台"}], "002058": [{"code": "002058", "name": "紫竹高科"}]}.get(word, [])

    async def quotes(codes):
        return {"600519": {"price": 1255.79, "change_pct": -0.22}, "002058": {"price": 22.22, "change_pct": 10.0}}
    text = await cli.daily_brief(["茅台", "002058", "不存在"], quotes=quotes, find=find)
    assert "2026-10-08 大盘复盘" in text and "· 贵州茅台 600519  1255.79  -0.22%" in text
    assert "· 紫竹高科 002058  22.22  +10.00%，涨停（固态电池+锂电池）" in text and "不存在" not in text
    _patch_recap(monkeypatch, None)
    assert await cli.daily_brief(["茅台"], quotes=quotes, find=find) == ""             # 休市：什么都不发
    assert await channels.push_stateless("x") == []                                    # 没配地址：不发，也不报错


def test_generic_skill_packages_can_be_installed_as_methods():
    from wealthpilot.services import skills
    generic = "---\nname: Buffett Moat\ndescription: Judge whether a company has a durable moat.\n---\n# Moat\n\nAsk what stops a competitor.\n\n```bash\npython run.py\n```\n" + "细则。" * 3000
    content, skill, problems, adapted = skills.prepare(generic, "https://github.com/x/y")
    assert adapted and problems == [] and skill.name == "buffett-moat" and skill.agents == ["fundamental", "valuation", "industry", "expectation"]
    assert "python run.py" not in content and "不会执行" in content and "后面的部分没有导入" in content and "imported_from: https://github.com/x/y" in content
    from pathlib import Path
    native = (Path(__file__).resolve().parents[1] / "skills-gallery" / "theme-chain.md").read_text(encoding="utf-8")
    same, parsed, _, touched = skills.prepare(native)
    assert same == native and touched is False and parsed.needs == "none" and parsed.agents == ["industry", "fundamental", "expectation"]
    assert skills.prepare("just some text")[1] is None and skills.prepare("---\nname: x\n---\nno description")[1] is None
    assert skills.raw_url("https://github.com/muxuuu/serenity-skill") == "https://raw.githubusercontent.com/muxuuu/serenity-skill/HEAD/SKILL.md"
    assert skills.raw_url("https://github.com/a/b/tree/main/skills/buffett/") == "https://raw.githubusercontent.com/a/b/main/skills/buffett/SKILL.md"
    assert skills.raw_url("https://github.com/a/b/blob/main/x.md") == "https://raw.githubusercontent.com/a/b/main/x.md"
    assert skills.adapt_generic("---\nname: 巴菲特护城河\ndescription: 判断护城河\n---\n正文").startswith("---\nname: imported-")
