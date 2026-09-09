"""WealthPilot CLI — python -m wealthpilot [command]"""

import argparse
import sys


def cmd_run(args: argparse.Namespace) -> None:
    import uvicorn
    from wealthpilot.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "wealthpilot.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


def cmd_init(_args: argparse.Namespace) -> None:
    import secrets
    from pathlib import Path

    env_path = Path(".env")
    example = Path(".env.example")

    if env_path.exists():
        print("⚠️  .env 已存在，跳过创建")
    elif example.exists():
        content = example.read_text()
        content = content.replace(
            "change-this-to-a-random-string-in-production",
            secrets.token_urlsafe(32),
        )

        print("选择 AI 提供商:")
        print("  1. Anthropic (Claude)")
        print("  2. DeepSeek")
        choice = input("请输入 1 或 2（默认 1）: ").strip()

        if choice == "2":
            content = content.replace("AI_PROVIDER=anthropic", "AI_PROVIDER=deepseek")
            api_key = input("请输入 DeepSeek API Key（留空跳过）: ").strip()
            if api_key:
                content = content.replace("DEEPSEEK_API_KEY=", f"DEEPSEEK_API_KEY={api_key}")
        else:
            api_key = input("请输入 Anthropic API Key（留空跳过）: ").strip()
            if api_key:
                content = content.replace("sk-ant-xxx", api_key)

        env_path.write_text(content)
        print(f"✅ 已创建 {env_path}")
    else:
        print("❌ 未找到 .env.example 模板")
        return

    from wealthpilot.storage.db import get_engine
    get_engine()
    print("✅ 数据库已初始化")


def _mask_key(key: str) -> str:
    if len(key) > 14:
        return key[:10] + "..." + key[-4:]
    if not key:
        return "(未设置)"
    return "***"


def cmd_config(_args: argparse.Namespace) -> None:
    from wealthpilot.settings import get_settings

    s = get_settings()
    provider = s.ai_provider.upper()
    if s.ai_provider == "deepseek":
        key_display = _mask_key(s.deepseek_api_key)
        model = s.deepseek_model
    else:
        key_display = _mask_key(s.anthropic_api_key)
        model = s.anthropic_model

    print("┌─ WealthPilot 配置 ─────────────────────┐")
    print(f"│ AI 提供商:      {provider:<24}│")
    print(f"│ AI 模型:        {model:<24}│")
    print(f"│ API Key:        {key_display:<24}│")
    print(f"│ 工具调用轮次:   {s.agent_max_tool_rounds:<24}│")
    print(f"│ 最大 Token:     {s.agent_max_tokens:<24}│")
    print(f"│ 数据库:         {str(s.db_path):<24}│")
    print(f"│ 服务地址:       {s.host}:{s.port:<18}│")
    print(f"│ 日志级别:       {s.log_level:<24}│")
    print(f"│ 前端地址:       {s.frontend_url:<24}│")
    print("└─────────────────────────────────────────┘")


def _load_context():
    """加载持仓、净值与风险画像 —— CLI 与 Web 走同一套上下文。"""
    import asyncio

    from sqlmodel import Session, select

    from wealthpilot.models.portfolio import PortfolioHolding
    from wealthpilot.routes.profile import load_profile
    from wealthpilot.services.market_data import fetch_fund_info, fetch_fund_nav
    from wealthpilot.storage.db import get_engine

    engine = get_engine()
    with Session(engine) as session:
        holdings = list(session.exec(select(PortfolioHolding)).all())
        profile = load_profile(session)

    async def load_nav():
        nav_data: dict[str, float] = {}
        nav_history: dict[str, list[dict]] = {}
        for h in holdings:
            info = await fetch_fund_info(h.fund_code)
            nav_data[h.fund_code] = info["nav"] if info else h.cost_price
            hist = await fetch_fund_nav(h.fund_code, 60)
            if hist:
                nav_history[h.fund_code] = hist
        return nav_data, nav_history

    nav_data, nav_history = asyncio.run(load_nav())
    return holdings, nav_data, nav_history, profile


async def _consume_stream(stream, *, verbose_to_stderr: bool = False) -> str:
    """消费 chat_stream 的 SSE 事件并打印。返回最终文本。"""
    import json

    info = sys.stderr if verbose_to_stderr else sys.stdout
    full_text = ""

    async for sse_line in stream:
        if not sse_line.startswith("data: "):
            continue
        data = json.loads(sse_line[6:].strip())
        kind = data.get("type")

        if kind == "plan":
            tasks = data.get("tasks", [])
            if len(tasks) > 1:
                print(f"\n🧭 规划 {len(tasks)} 个并行任务（{data.get('intent', '')}）：", file=info)
                for t in tasks:
                    print(f"   • {t.get('label', t['agent'])} — {t.get('goal', '')}", file=info)
        elif kind == "task_start":
            print(f"\n{data.get('label', data['agent'])} 开始：{data.get('goal', '')}", file=info)
        elif kind == "task_done":
            tools = "、".join(data.get("tools", [])) or "无"
            print(f"   ✓ 完成（工具：{tools}）", file=info)
        elif kind == "synthesizing":
            print("\n🧩 整合各方证据…\n", file=info)
        elif kind == "delta":
            print(data["content"], end="", flush=True)
            full_text += data["content"]
        elif kind == "tool_call":
            print(f"\n  🔧 {data['tool']}...", file=info, flush=True)
        elif kind == "grounding_warning":
            nums = "、".join(data.get("ungrounded", []))
            print(
                f"\n⚠️  数值溯源率 {data.get('rate')}，以下数字未在工具返回中找到：{nums}",
                file=sys.stderr,
            )
        elif kind == "error":
            print(f"\n  ❌ {data['content']}", file=sys.stderr)

    return full_text


def cmd_chat(_args: argparse.Namespace) -> None:
    import asyncio

    from wealthpilot.services.agents.orchestrator import chat_stream
    from wealthpilot.services.ai_client import create_ai_client
    from wealthpilot.settings import get_settings

    settings = get_settings()
    try:
        create_ai_client(settings)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    holdings, nav_data, nav_history, profile = _load_context()

    history: list[dict] = []
    provider = settings.ai_provider.upper()

    print("╔═══════════════════════════════════════╗")
    print(f"║  WealthPilot AI 终端对话 ({provider})     ║")
    print("║  输入 quit 退出 · 输入 clear 清空历史  ║")
    print("╚═══════════════════════════════════════╝")
    if profile is None:
        print("提示：尚未完成风险测评，涉及仓位的建议会被限制。")
    else:
        print(f"风险画像：{profile.risk_label} · 最大回撤容忍 {profile.max_drawdown_tolerance:.0%}")
    print()

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break
        if user_input.lower() == "clear":
            history.clear()
            print("历史已清空\n")
            continue

        stream = chat_stream(
            user_input, list(history), holdings, nav_data, nav_history, profile=profile
        )
        full_text = asyncio.run(_consume_stream(stream))

        print("\n")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": full_text})


def cmd_mcp(_args: argparse.Namespace) -> None:
    from wealthpilot.mcp_server import main as mcp_main
    mcp_main()


def cmd_ask(args: argparse.Namespace) -> None:
    import asyncio

    query = args.query
    if query == "-":
        query = sys.stdin.read().strip()
    if not query:
        print("❌ 查询内容不能为空", file=sys.stderr)
        sys.exit(1)

    from wealthpilot.services.agents.orchestrator import chat_stream
    from wealthpilot.services.ai_client import create_ai_client
    from wealthpilot.settings import get_settings

    settings = get_settings()
    try:
        create_ai_client(settings)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    holdings, nav_data, nav_history, profile = _load_context()

    stream = chat_stream(query, [], holdings, nav_data, nav_history, profile=profile)
    asyncio.run(_consume_stream(stream, verbose_to_stderr=True))

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="wealthpilot",
        description="WealthPilot — AI 智能投顾 Agent CLI",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="启动 API 服务")
    run_p.add_argument("--reload", action="store_true", help="热重载（开发模式）")

    sub.add_parser("init", help="初始化 .env 和数据库")
    sub.add_parser("config", help="查看当前配置")
    sub.add_parser("chat", help="终端交互式 AI 对话")
    sub.add_parser("mcp", help="启动 MCP Server (stdio, for Claude Code)")

    ask_p = sub.add_parser("ask", help="非交互式 AI 查询（支持管道输入）")
    ask_p.add_argument("query", help="查询内容，传 '-' 从 stdin 读取")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "init": cmd_init,
        "config": cmd_config,
        "chat": cmd_chat,
        "mcp": cmd_mcp,
        "ask": cmd_ask,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
