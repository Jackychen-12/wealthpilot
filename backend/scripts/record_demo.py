"""录制工作台"在线演示"用的数据快照。

在线演示（GitHub Pages）没有后端。这里用一份示例组合真实跑一遍后端 ——
真实行情、真实工具、真实模型 —— 把各接口的返回和 AI 研究的事件流录下来，
工作台在演示模式下回放。录的是真实结果，不是手写的假数据。

用法（在 backend/ 下，需已配置模型 Key）：
    uv run python scripts/record_demo.py               # 全部重录
    uv run python scripts/record_demo.py --keep-chats  # 只刷新行情数据，研究过程沿用已有的
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="wp-demo-")) / "demo.db")

from fastapi.testclient import TestClient  # noqa: E402

from wealthpilot.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "workbench" / "src" / "demo" / "fixtures.json"

# 示例组合：股票和 ETF 为主，基金作为持仓的一种
HOLDINGS = [
    ("stock", "300750", "宁德时代", 100, 262.0, "2025-04-10", "equity", "电池"),
    ("stock", "600036", "招商银行", 600, 36.5, "2024-12-02", "equity", "银行"),
    ("stock", "000858", "五粮液", 200, 78.4, "2025-02-18", "equity", "白酒"),
    ("etf", "510300", "沪深300ETF华泰柏瑞", 5000, 3.95, "2024-10-08", "equity", "宽基"),
    ("fund", "110011", "易方达优质精选混合", 2500, 4.35, "2025-03-10", "equity", "消费"),
    ("fund", "161725", "招商中证白酒指数A", 8000, 0.92, "2024-11-20", "equity", "白酒"),
    ("fund", "110017", "易方达增强回报债券A", 9000, 1.38, "2024-09-01", "bond", "债券"),
]
WATCHLIST = [
    ("600519", "贵州茅台", "stock", "白酒龙头，等估值分位和业绩拐点"),
    ("300750", "宁德时代", "stock", "已持有，跟踪季度毛利率"),
    ("601899", "紫金矿业", "stock", ""),
    ("510300", "沪深300ETF华泰柏瑞", "etf", "宽基底仓"),
]
PROFILE = {"risk_level": 3, "horizon_months": 36, "max_drawdown_tolerance": 0.2,
           "liquidity_reserve": 20000, "experience_years": 4, "available_cash": 50000,
           "excluded_industries": []}
GETS = [
    "/health", "/api/portfolio", "/api/analysis/overview", "/api/analysis/attribution?by=fund",
    "/api/analysis/attribution?by=industry", "/api/analysis/attribution?by=category",
    "/api/analysis/drawdown", "/api/analysis/health", "/api/analysis/correlation",
    "/api/analysis/suggestions", "/api/market/indices", "/api/market/news", "/api/alerts",
    "/api/scenario", "/api/profile", "/api/report/weekly",
    *[f"/api/market/fund/110011/nav?days={d}" for d in (21, 63, 125, 250)],
    *[f"/api/market/stock/600519/kline?days={d}" for d in (21, 63, 125, 250)],
    "/api/connectors", "/api/screener/industries",
    *[f"/api/securities/search?q={q}" for q in ("600519", "300750", "600036", "000858", "510300", "110011", "161725")],
]
# 非工具类的只读 POST（选股）。入参必须与工作台演示模式预填的条件一致
POSTS = {
    "/api/screener": {"limit": 50, "sort_by": "total_mv_yi", "descending": True, "pe_max": 15, "roe_min": 15, "mv_min_yi": 200},
}
TOOLS = {
    "compute_concentration": {},
    "lookthrough_portfolio": {},
    "compute_stock_overlap": {"fund_code_a": "110011", "fund_code_b": "161725"},
    "get_fund_info": {"fund_code": "110011"},
    "simulate_portfolio_change": {"changes": [{"fund_code": "161725", "target_pct": 15}]},
    "check_profile_constraint": {"changes": [{"fund_code": "161725", "target_pct": 15}]},
    "get_stock_quote": {"code": "600519"},
    "get_stock_valuation": {"code": "600519"},
    "get_stock_profile": {"code": "600519"},
    "get_technical_indicators": {"code": "600519"},
    "get_financial_indicators": {"code": "600519"},
    "get_dividend_history": {"code": "600519"},
    "get_valuation_history": {"code": "600519"},
    "compare_peers_valuation": {"code": "600519"},
    "get_industry_peers": {"code": "600519"},
    "get_stock_announcements": {"code": "600519"},
    "get_market_overview": {},
    "get_sector_ranking": {"top": 5},
    "backtest_rule": {"fund_code": "110011", "days": 250,
                      "triggers": [{"drawdown_pct": 5, "add_pct": 30}, {"drawdown_pct": 10, "add_pct": 70}]},
}
# 四个研究模板各一题，外加一个自由问答。第一题的措辞与个股页"深度研究"按钮一致，演示里点按钮即可回放
QUESTIONS = [
    "帮我深度分析一下贵州茅台（600519）",
    "对比一下贵州茅台和五粮液的基本面和估值",
    "帮我诊断一下我的持仓",
    "帮我筛选市盈率低于15、ROE高于15%的大市值股票",
    "110011 最新净值多少，近一个月表现如何",
    # 放在最后：复盘的是前面几次研究设下的验证点
    "复盘一下之前的研究：验证点成立了多少，哪些判断被证伪了",
]
# 研究录完之后才有内容的接口
AFTER_CHATS = ["/api/checkpoints", "/api/checkpoints?code=600519", "/api/checkpoints/scorecard", "/api/proposals"]
HISTORY = "/api/research/history"


def record_chat(client: TestClient, question: str) -> list[dict]:
    events, started = [], time.time()
    # 带上会话 ID，后端才会把这一轮存进研究记录
    with client.stream("POST", "/api/chat", json={"message": question, "history": [], "conversation_id": f"demo-{QUESTIONS.index(question)}"}) as resp:
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "delta":
                continue  # 回放时由 done 事件一次给出正文
            if event["type"] == "evidence":
                event["evidence"]["output"] = str(event["evidence"]["output"])[:1500]
            if event["type"] == "done":
                event["meta"].pop("evidence", None)
            events.append({"t": round(time.time() - started, 1), **event})
    return events


def main() -> None:
    client = TestClient(app)
    for asset_type, code, name, shares, cost, date, category, industry in HOLDINGS:
        client.post("/api/portfolio", json={
            "asset_type": asset_type, "fund_code": code, "fund_name": name, "shares": shares, "cost_price": cost,
            "buy_date": date, "category": category, "industry": industry}).raise_for_status()
    client.put("/api/profile", json=PROFILE).raise_for_status()
    for code, name, asset_type, note in reversed(WATCHLIST):
        client.post("/api/watchlist", json={"code": code, "name": name, "asset_type": asset_type, "note": note}).raise_for_status()

    fixtures: dict = {"recorded_at": time.strftime("%Y-%m-%d"), "get": {}, "post": {}, "tools": {}, "chats": {}}
    for path in [*GETS, "/api/watchlist"]:
        print("GET", path)
        fixtures["get"][path] = client.get(path).json()
    for key in [s["scenario_key"] for s in fixtures["get"]["/api/scenario"]["scenarios"]]:
        fixtures["get"][f"/api/scenario/{key}"] = client.get(f"/api/scenario/{key}").json()
    for name, inputs in TOOLS.items():
        print("TOOL", name)
        # 入参一并存下：演示模式只在参数与录制时一致才回放，免得"填的是 A、显示的是 B"
        fixtures["tools"][name] = {"inputs": inputs, "result": client.post(f"/api/tools/{name}", json=inputs).json()}
    for path, body in POSTS.items():
        print("POST", path)
        fixtures["post"][path] = {"inputs": body, "result": client.post(path, json=body).json()}
    # --keep-chats：已录过的研究过程原样保留，只补录新增的问题（省模型调用）
    old = json.loads(OUT.read_text()) if "--keep-chats" in sys.argv and OUT.exists() else {}
    previous = old.get("chats", {})
    for question in QUESTIONS:
        if question in previous:
            fixtures["chats"][question] = previous[question]
            print("CHAT", question, "-> 沿用已有录制")
            continue
        events = record_chat(client, question)
        status = events[-1].get("meta", {}).get("status")
        print("CHAT", question, "->", status)
        if status not in ("passed", "partial"):
            sys.exit(f"这个问题没有跑出可发布的回答（{status}），不写入快照；请重试")
        fixtures["chats"][question] = events

    for path in AFTER_CHATS:
        fixtures["get"][path] = client.get(path).json()
    # 研究记录：本次新录的由后端存下；沿用旧录制时，把旧快照里对应的记录带过来
    records = client.get(HISTORY).json()
    fixtures["get"][HISTORY] = records
    for r in records:
        fixtures["get"][f"{HISTORY}/{r['id']}"] = client.get(f"{HISTORY}/{r['id']}").json()
    kept = [r for r in old.get("get", {}).get(HISTORY, []) if r["question"] in previous and r["question"] not in {x["question"] for x in records}]
    for r in kept:
        fixtures["get"][HISTORY].append(r)
        fixtures["get"][f"{HISTORY}/{r['id']}"] = old["get"][f"{HISTORY}/{r['id']}"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")))
    print(f"已写入 {OUT}（{OUT.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
