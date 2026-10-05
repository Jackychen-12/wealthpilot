"""回答质量评测：用真实模型跑一组固定问题，统计通过率、被打回次数、耗时。

用来回答"改了架构之后到底有没有变好"。同一份题目可以对着不同版本的代码跑
（PYTHONPATH 指向另一份 src 即可），再把两份结果放在一起比。

用法（在 backend/ 下，需已配置模型 Key，会产生真实调用费用）：
    uv run python scripts/eval.py --out eval-new.json
    PYTHONPATH=/path/to/old/src uv run python scripts/eval.py --out eval-old.json
    uv run python scripts/eval.py --compare eval-old.json eval-new.json
"""

import argparse
import asyncio
import faulthandler
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

QUESTIONS = [
    ("个股", "帮我分析一下贵州茅台"),
    ("个股", "宁德时代现在估值贵不贵"),
    ("个股", "比亚迪最近业绩怎么样"),
    ("个股", "招商银行最近走势如何"),
    ("个股", "贵州茅台现在多少钱"),
    ("对比", "贵州茅台和五粮液哪个估值更低"),
    ("持仓", "我的持仓整体怎么样"),
    ("持仓", "我的持仓集中度高吗"),
    ("持仓", "我的组合回撤风险大吗"),
    ("选股", "帮我找出市盈率低于15、ROE高于15的大盘股"),
    ("基金", "110011 最新净值多少，近一个月表现如何"),
    ("市场", "今天市场表现怎么样，哪些行业领涨"),
]
HOLDINGS = [
    ("stock", "600519", "贵州茅台", 20, 1400.0, "equity", "白酒"),
    ("stock", "300750", "宁德时代", 100, 330.0, "equity", "电池"),
    ("fund", "110011", "易方达优质精选混合", 2500, 4.35, "equity", "消费"),
    ("fund", "161725", "招商中证白酒指数A", 8000, 0.92, "equity", "白酒"),
    ("fund", "110017", "易方达增强回报债券A", 9000, 1.38, "bond", "债券"),
]


async def run_all(out: Path) -> None:
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="wp-eval-")) / "eval.db")
    from wealthpilot.models.portfolio import PortfolioHolding
    from wealthpilot.models.profile import InvestorProfile
    from wealthpilot.services.agents.orchestrator import chat_stream
    from wealthpilot.services.context import load_market_context

    holdings = [PortfolioHolding(user_id=0, asset_type=t, fund_code=c, fund_name=n, shares=s, cost_price=p,
                                 buy_date=date(2025, 1, 2), category=cat, industry=ind)
                for t, c, n, s, p, cat, ind in HOLDINGS]
    profile = InvestorProfile(user_id=0, risk_level=3, horizon_months=36, max_drawdown_tolerance=0.2,
                              liquidity_reserve=20000, experience_years=4)
    nav_data, nav_history = await load_market_context(holdings)

    rows = []
    for kind, question in QUESTIONS:
        started, events = time.time(), []
        async def consume(q=question, sink=events):
            async for line in chat_stream(q, [], holdings, nav_data, nav_history, profile=profile):
                event = json.loads(line[6:])
                if event["type"] != "delta":
                    sink.append(event)

        # 卡住超过 4 分钟就把各线程的调用栈打出来（下次能知道卡在哪），并放弃这一题
        faulthandler.dump_traceback_later(240, file=sys.stderr)
        try:
            await asyncio.wait_for(consume(), 300)
        except TimeoutError:
            events.append({"type": "done", "content": "超时", "meta": {"status": "timeout"}})
        except Exception as e:  # noqa: BLE001
            events.append({"type": "done", "content": f"异常：{e}", "meta": {"status": "crashed"}})
        done = next((e for e in reversed(events) if e["type"] == "done"), {"content": "", "meta": {"status": "no_done"}})
        plan = next((e for e in events if e["type"] == "plan"), {})
        row = {
            "kind": kind, "question": question, "status": done["meta"].get("status"),
            "seconds": round(time.time() - started, 1),
            "tasks": [t["agent"] for t in plan.get("tasks", [])], "playbook": plan.get("playbook", ""),
            "tool_calls": sum(e["type"] == "evidence" for e in events),
            "rewrites": sum(e["type"] == "critic" and e.get("gate") == "answer" and not e["passed"] for e in events),
            "replans": sum(e["type"] == "replan" for e in events),
            "grounding_rate": done["meta"].get("grounding_rate"),
            "answer_chars": len(done.get("content", "")),
            "input_tokens": ((done.get("meta") or {}).get("usage") or {}).get("input_tokens", 0),
            "cached_tokens": ((done.get("meta") or {}).get("usage") or {}).get("cached_tokens", 0),
            "output_tokens": ((done.get("meta") or {}).get("usage") or {}).get("output_tokens", 0),
            "rejected_reasons": [i for e in events if e["type"] == "critic" and not e["passed"] for i in e.get("issues", [])][:6],
            "answer": done.get("content", ""),
        }
        rows.append(row)
        faulthandler.cancel_dump_traceback_later()
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))   # 每题都落盘，中途断了也不白跑
        print(f"[{kind}] {question} -> {row['status']}  {row['seconds']}s  工具{row['tool_calls']}  打回{row['rewrites']}", flush=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    published = [r for r in rows if r["status"] in ("passed", "partial")]
    return {
        "题数": n,
        "通过": sum(r["status"] == "passed" for r in rows),
        "带标注发布": sum(r["status"] == "partial" for r in rows),
        "未发布": n - len(published),
        "平均耗时(秒)": round(sum(r["seconds"] for r in rows) / n, 1),
        "平均工具调用": round(sum(r["tool_calls"] for r in rows) / n, 1),
        "平均被打回次数": round(sum(r["rewrites"] for r in rows) / n, 2),
        "平均回答字数": round(sum(r["answer_chars"] for r in published) / max(1, len(published))),
        "平均输入token": round(sum(r.get("input_tokens", 0) for r in rows) / n),
        "平均未命中缓存的输入token": round(sum(r.get("input_tokens", 0) - r.get("cached_tokens", 0) for r in rows) / n),
        "平均输出token": round(sum(r.get("output_tokens", 0) for r in rows) / n),
    }


def compare(old_path: Path, new_path: Path) -> None:
    old, new = json.loads(old_path.read_text()), json.loads(new_path.read_text())
    so, sn = summarize(old), summarize(new)
    print("| 指标 | 旧架构 | 新架构 |\n|---|---|---|")
    for key in so:
        print(f"| {key} | {so[key]} | {sn[key]} |")
    print("\n| 类别 | 问题 | 旧：状态 / 秒 / 工具 / 打回 | 新：状态 / 秒 / 工具 / 打回 |\n|---|---|---|---|")
    by_question = {r["question"]: r for r in old}
    for r in new:
        o = by_question.get(r["question"])
        cell = lambda x: f"{x['status']} / {x['seconds']} / {x['tool_calls']} / {x['rewrites']}" if x else "—"  # noqa: E731
        print(f"| {r['kind']} | {r['question']} | {cell(o)} | {cell(r)} |")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("eval-result.json"))
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("OLD", "NEW"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
        sys.exit(0)
    asyncio.run(run_all(args.out))
    print(json.dumps(summarize(json.loads(args.out.read_text())), ensure_ascii=False))
