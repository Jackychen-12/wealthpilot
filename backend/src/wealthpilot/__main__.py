"""WealthPilot CLI — python -m wealthpilot [command]"""

import argparse
import os
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

    from wealthpilot.services.context import load_local_user, load_market_context
    from wealthpilot.settings import get_settings

    holdings, profile = load_local_user(get_settings().local_user_id)
    nav_data, nav_history = asyncio.run(load_market_context(holdings))
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
            ok = data.get("status", "completed") == "completed"
            print(f"   {'✓ 完成' if ok else '✗ ' + data['status']}（工具：{tools}）", file=info)
        elif kind == "replan":
            print(f"\n🔁 证据不足，补充 {len(data.get('tasks', []))} 个任务", file=info)
        elif kind == "critic" and not data.get("passed"):
            issues = "；".join(data.get("issues", []))
            print(f"\n🧐 校验未通过（{data.get('gate')}）：{issues}", file=info)
        elif kind == "done":
            status = data.get("meta", {}).get("status", "passed")
            if status == "partial":
                gaps = "；".join(data.get("meta", {}).get("missing_evidence", []))
                print(f"\n\n⚠️  部分证据未取得，回答不完整：{gaps}", file=sys.stderr)
            elif status != "passed":
                print(f"\n\n⚠️  本次研究状态：{status}", file=sys.stderr)
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
    if not holdings:
        print(f"提示：用户 {settings.local_user_id} 没有持仓，持仓类问题无法分析（可用 LOCAL_USER_ID 切换）。")

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


def cmd_tui(args: argparse.Namespace) -> None:
    from wealthpilot.tui import main as tui_main
    tui_main(getattr(args, "server", ""), getattr(args, "token", ""), web=not getattr(args, "no_web", False),
             port=getattr(args, "port", 8000))


def cmd_watch(_args: argparse.Namespace) -> None:
    """跑一次盯盘并打印简报。适合挂 cron；后端开着时会自己定时跑。"""
    import asyncio

    from sqlmodel import Session

    from wealthpilot.services import watcher
    from wealthpilot.settings import get_settings
    from wealthpilot.storage.db import get_engine

    with Session(get_engine()) as db:
        digest = asyncio.run(watcher.run(db, get_settings().local_user_id))
    print(f"{digest['day']} · {digest['summary']}")
    for e in digest["events"]:
        print(f"  - {e['name']} {e['code']}：{e['text']}".replace("  ：", "："))


def cmd_update(_args: argparse.Namespace) -> None:
    """把 WealthPilot 升到最新：备份数据库、拉代码、装依赖、重建网页版。"""
    from wealthpilot.services import upgrade

    sys.exit(0 if upgrade.update() else 1)


def cmd_doctor(args: argparse.Namespace) -> None:
    """自检：哪一环不通、怎么修。"""
    import asyncio

    from wealthpilot import __version__
    from wealthpilot.services import doctor

    print(f"WealthPilot v{__version__} 自检" + ("" if not args.offline else "（不实测模型）"))
    items = asyncio.run(doctor.run(online=not args.offline, port=args.port))
    print(doctor.render(items))
    sys.exit(1 if any(i["status"] == "fail" for i in items) else 0)


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
    from wealthpilot import __version__
    parser.add_argument("-V", "--version", action="version", version=f"wealthpilot {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="启动 API 服务")
    run_p.add_argument("--reload", action="store_true", help="热重载（开发模式）")

    sub.add_parser("init", help="初始化 .env 和数据库")
    sub.add_parser("config", help="查看当前配置")
    sub.add_parser("chat", help="终端交互式 AI 对话（旧版，建议直接运行 wealthpilot）")
    for p in (parser, sub.add_parser("tui", help="终端入口（默认）：研究、行情、选股、复盘")):
        p.add_argument("--server", default=os.environ.get("WEALTHPILOT_SERVER", ""),
                       help="连接远程后端，如 http://192.168.1.10:8000；不填则在本机进程内运行")
        p.add_argument("--token", default=os.environ.get("WEALTHPILOT_TOKEN", ""), help="远程后端的登录令牌（也可进入后用 /login）")
        p.add_argument("--no-web", action="store_true", help="只用终端，不在后台启动网页版")
        p.add_argument("--port", type=int, default=8000, help="网页版和接口的端口，默认 8000")
    sub.add_parser("watch", help="跑一次每日盯盘并打印简报（可挂 cron）")
    sub.add_parser("update", help="升级到最新版本（先备份数据库；有本地改动会停下来问）")
    doctor_p = sub.add_parser("doctor", help="自检：模型、数据源、数据库、手机触达、版本，哪一环不通、怎么修")
    doctor_p.add_argument("--offline", action="store_true", help="不实测模型调用")
    doctor_p.add_argument("--port", type=int, default=8000)
    sub.add_parser("mcp", help="启动 MCP Server (stdio, for Claude Code)")

    ask_p = sub.add_parser("ask", help="非交互式 AI 查询（支持管道输入）")
    ask_p.add_argument("query", help="查询内容，传 '-' 从 stdin 读取")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "init": cmd_init,
        "config": cmd_config,
        "chat": cmd_chat,
        "tui": cmd_tui,
        "watch": cmd_watch,
        "update": cmd_update,
        "doctor": cmd_doctor,
        "mcp": cmd_mcp,
        "ask": cmd_ask,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        cmd_tui(args)  # 不带子命令：直接进终端入口


if __name__ == "__main__":
    main()
