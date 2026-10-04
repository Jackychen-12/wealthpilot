"""录制工作台"在线演示"用的数据快照。

在线演示（GitHub Pages）没有后端。这里用一份示例组合真实跑一遍后端 ——
真实行情、真实工具、真实模型 —— 把各接口的返回和 AI 研究的事件流录下来，
工作台在演示模式下回放。录的是真实结果，不是手写的假数据。

用法（在 backend/ 下，需已配置模型 Key）：
    uv run python scripts/record_demo.py
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

HOLDINGS = [
    ("110011", "易方达优质精选混合", 2500, 4.35, "2025-03-10", "equity", "消费"),
    ("007340", "南方科技创新混合A", 6000, 2.10, "2025-01-15", "equity", "科技"),
    ("161725", "招商中证白酒指数A", 8000, 0.92, "2024-11-20", "equity", "白酒"),
    ("000216", "华安黄金ETF联接A", 5000, 2.05, "2025-05-08", "hybrid", "黄金"),
    ("110017", "易方达增强回报债券A", 9000, 1.38, "2024-09-01", "bond", "债券"),
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
]
TOOLS = {
    "compute_concentration": {},
    "lookthrough_portfolio": {},
    "compute_stock_overlap": {"fund_code_a": "110011", "fund_code_b": "161725"},
    "get_fund_info": {"fund_code": "110011"},
    "simulate_portfolio_change": {"changes": [{"fund_code": "161725", "target_pct": 15}]},
    "check_profile_constraint": {"changes": [{"fund_code": "161725", "target_pct": 15}]},
    "backtest_rule": {"fund_code": "110011", "days": 250,
                      "triggers": [{"drawdown_pct": 5, "add_pct": 30}, {"drawdown_pct": 10, "add_pct": 70}]},
}
QUESTIONS = [
    "我的持仓集中度高吗？",
    "把我的组合穿透到个股，真实暴露集中在哪里？",
    "110011 最新净值多少，近一个月表现如何",
]


def record_chat(client: TestClient, question: str) -> list[dict]:
    events, started = [], time.time()
    with client.stream("POST", "/api/chat", json={"message": question, "history": []}) as resp:
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
    for code, name, shares, cost, date, category, industry in HOLDINGS:
        client.post("/api/portfolio", json={
            "fund_code": code, "fund_name": name, "shares": shares, "cost_price": cost,
            "buy_date": date, "category": category, "industry": industry}).raise_for_status()
    client.put("/api/profile", json=PROFILE).raise_for_status()

    fixtures: dict = {"recorded_at": time.strftime("%Y-%m-%d"), "get": {}, "tools": {}, "chats": {}}
    for path in GETS:
        print("GET", path)
        fixtures["get"][path] = client.get(path).json()
    for key in [s["scenario_key"] for s in fixtures["get"]["/api/scenario"]["scenarios"]]:
        fixtures["get"][f"/api/scenario/{key}"] = client.get(f"/api/scenario/{key}").json()
    for name, inputs in TOOLS.items():
        print("TOOL", name)
        # 入参一并存下：演示模式只在参数与录制时一致才回放，免得"填的是 A、显示的是 B"
        fixtures["tools"][name] = {"inputs": inputs, "result": client.post(f"/api/tools/{name}", json=inputs).json()}
    for question in QUESTIONS:
        events = record_chat(client, question)
        status = events[-1].get("meta", {}).get("status")
        print("CHAT", question, "->", status)
        if status not in ("passed", "partial"):
            sys.exit(f"这个问题没有跑出可发布的回答（{status}），不写入快照；请重试")
        fixtures["chats"][question] = events

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixtures, ensure_ascii=False, separators=(",", ":")))
    print(f"已写入 {OUT}（{OUT.stat().st_size // 1024} KB）")


if __name__ == "__main__":
    main()
