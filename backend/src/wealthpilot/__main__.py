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


def cmd_chat(_args: argparse.Namespace) -> None:
    from wealthpilot.settings import get_settings
    from wealthpilot.services.ai_client import create_ai_client

    settings = get_settings()
    try:
        client = create_ai_client(settings)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    model = settings.active_model

    from wealthpilot.services.agents.router_agent import RouterAgent
    from wealthpilot.services.agents.market_agent import MarketAgent
    from wealthpilot.services.agents.portfolio_agent import PortfolioAgent
    from wealthpilot.services.agents.risk_agent import RiskAgent

    history: list[dict] = []

    agent_labels = {
        "market": "📊 市场分析",
        "portfolio": "💼 持仓分析",
        "risk": "🛡️ 风险评估",
    }

    provider = settings.ai_provider.upper()
    print("╔═══════════════════════════════════════╗")
    print(f"║  WealthPilot AI 终端对话 ({provider})     ║")
    print("║  输入 quit 退出 · 输入 clear 清空历史  ║")
    print("╚═══════════════════════════════════════╝")
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

        router = RouterAgent(client, model)
        agent_name, reason = router.route(user_input)
        print(f"\n{agent_labels.get(agent_name, agent_name)} — {reason}")

        if agent_name == "market":
            agent = MarketAgent(client, model)
        elif agent_name == "risk":
            agent = RiskAgent(client, model, [], {}, None)
        else:
            agent = PortfolioAgent(client, model, [], {}, None)

        messages = [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
        messages.append({"role": "user", "content": user_input})

        import json
        full_text = ""
        for sse_line in agent.run(messages):
            if not sse_line.startswith("data: "):
                continue
            data = json.loads(sse_line[6:].strip())
            if data["type"] == "delta":
                print(data["content"], end="", flush=True)
                full_text += data["content"]
            elif data["type"] == "tool_call":
                print(f"\n  🔧 {data['tool']}...", flush=True)
            elif data["type"] == "error":
                print(f"\n  ❌ {data['content']}")

        print("\n")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": full_text})


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

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "init": cmd_init,
        "config": cmd_config,
        "chat": cmd_chat,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
