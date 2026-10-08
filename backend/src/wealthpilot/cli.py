"""装好之后的那几条命令：setup、model、config、status、skills、import、sessions。

目标是和 OpenClaw、Hermes 这类工具一样：装完敲 `wealthpilot setup`，选一家模型、贴一个 Key 就能用；
之后想换模型、改配置、看现状，都有一条不用进界面的命令。交互式的提问都可以用参数代替，方便写进脚本。

这里的输入输出都能替换（ask / secret / out），测试时不需要真的终端，也不会真的调用模型。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

from wealthpilot.services import providers

Ask = Callable[[str], str]
Out = Callable[[str], None]


def _pad(text: str, width: int) -> str:
    """按显示宽度补空格：一个汉字占两格，直接用 ljust 中英混排的列对不齐。"""
    shown = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - shown)


def _settings():
    from wealthpilot.settings import get_settings
    return get_settings()


def _apply(changes: dict) -> list[str]:
    from wealthpilot.routes.config import apply_changes
    from wealthpilot.storage.db import get_engine

    _settings().ensure_dirs()
    get_engine()   # 第一次用：把数据库建出来
    return apply_changes(changes)


def test_model() -> tuple[bool, str]:
    """用当前配置真的调用一次模型（几十个 token）。返回（通不通, 给人看的一句话）。"""
    from wealthpilot.services.ai_client import create_ai_client, diagnose

    settings = _settings()
    try:
        client = create_ai_client(settings)
        client.create(model=settings.active_model, max_tokens=2000, system="只回复两个字：正常", messages=[{"role": "user", "content": "测试"}])
    except Exception as e:  # noqa: BLE001 — 认得出的说人话，认不出的原样给
        known = diagnose(e)
        return False, known.message if known else str(e)[:200]
    return True, f"{settings.ai_provider} · {settings.active_model}"


# ── setup：三步配好 ─────────────────────────────────────

def _choose_provider(ask: Ask, out: Out) -> dict | None:
    out("\n1/3 用哪家的模型（回车选 1，输入 0 跳过）")
    for i, p in enumerate(providers.PRESETS, 1):
        out(f"  {i:>2}) {p['label']}" + (f"  — {p['note']}" if p["note"] else ""))
    out(f"  {len(providers.PRESETS) + 1:>2}) 其他兼容 OpenAI 接口的服务（自己填地址）")
    choice = ask("选哪个：").strip() or "1"
    if choice == "0":
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(providers.PRESETS):
        return providers.PRESETS[int(choice) - 1]
    if choice.isdigit() and int(choice) == len(providers.PRESETS) + 1:
        base = ask("接口地址（以 /v1 结尾的那种）：").strip()
        return providers.custom(base) if base else None
    return providers.find(choice)


def _configure_model(args, ask: Ask, secret: Ask, out: Out, interactive: bool) -> bool:
    """选服务、填 Key、定模型。返回有没有写入配置。"""
    preset = providers.find(args.provider) if args.provider else None
    if args.provider and preset is None:
        out(f"不认识「{args.provider}」。可选：{'、'.join(p['key'] for p in providers.PRESETS)}")
        return False
    key = (args.key or "").strip()
    if preset is None and key:
        preset = providers.guess_from_key(key)     # 只给了 Key：按前缀猜是哪家
    if preset is None and args.base_url:
        preset = providers.custom(args.base_url)
    if preset is None:
        if not interactive:
            return False
        preset = _choose_provider(ask, out)
        if preset is None:
            out("跳过了模型。不配也能看行情、选股、管持仓，只是不能让 AI 研究；之后随时运行 wealthpilot setup。")
            return False
    if not key and interactive and (preset["needs_key"] or preset["key"] == "custom"):
        if preset["key_page"]:
            out(f"  去这里拿 Key：{preset['key_page']}")
        key = secret("  粘贴 API Key（输入不会显示，只存在这台电脑上" + ("）：" if preset["needs_key"] else "；这个服务不要 Key 就直接回车）：")).strip()
    if preset["needs_key"] and not key:
        out("没有填 Key，模型没有配置。")
        return False
    model = (args.model or "").strip()
    if not model and interactive:
        hint = f" [{preset['model']}]" if preset["model"] else ""
        model = ask(f"  模型名{hint}（回车用默认的，以服务商文档为准）：").strip()
    if not (model or preset["model"]):
        out("这家服务没有默认的模型名，请用 --model 指定（或重新运行 wealthpilot setup 填一个）。")
        return False
    _apply(providers.changes_for(preset, key, model, args.base_url or ""))
    out(f"✓ 已保存：{preset['label']} · {_settings().active_model}")
    return True


def _holdings(args, ask: Ask, out: Out, interactive: bool) -> None:
    from sqlmodel import Session

    from wealthpilot.routes import onboarding, research
    from wealthpilot.storage.db import get_engine

    uid = _settings().local_user_id
    if args.sample:
        with Session(get_engine()) as db:
            research.load_sample(db, uid)
        out("✓ 已载入示例持仓和自选（带示例标记，wealthpilot 里 /sample clear 一键清掉）")
        return
    if not interactive:
        return
    out("\n2/3 放进你的股票（一行一只：名称或代码 数量 成本价；多只用分号隔开）")
    line = ask("现在录入，或输入 s 用示例数据，回车跳过：").strip()
    if line.lower() == "s":
        with Session(get_engine()) as db:
            research.load_sample(db, uid)
        out("✓ 已载入示例数据")
        return
    if not line:
        return
    text = "\n".join(part.strip() for part in line.replace("；", ";").split(";") if part.strip())
    rows = asyncio.run(onboarding.parse_holdings({"text": text}))["rows"]
    good = [r for r in rows if r["ok"]]
    for r in rows:
        out(f"  {r['name']} {r['code']}  {r['shares']:g} 股  成本 {r['cost']:g}" if r["ok"] else f"  ✗ {r['line']}：{r['problem']}")
    if good and (ask(f"录入这 {len(good)} 条？[Y/n] ").strip().lower() or "y") in ("y", "yes", "是"):
        with Session(get_engine()) as db:
            done = asyncio.run(onboarding.add_holdings({"rows": good}, db, uid))
        out(f"✓ 已添加 {done['added']} 条" + "".join(f"\n  跳过：{s}" for s in done["skipped"]))


def cmd_setup(args, *, ask: Ask = input, secret: Ask = getpass.getpass, out: Out = print, interactive: bool | None = None,
              tester: Callable[[], tuple[bool, str]] = test_model) -> int:
    """配好就能用：选模型服务、填 Key、（可选）放进股票。每一步都可以跳过，参数给全了就一句话不问。"""
    interactive = sys.stdin.isatty() if interactive is None else interactive
    if not interactive and not (args.key or args.provider or args.base_url or args.sample):
        out("这条命令需要在终端里一步步回答；写进脚本时用参数代替，例如：\n"
            "  wealthpilot setup --key sk-xxxx                 # 只给 Key：自动认出是 DeepSeek 还是 Claude\n"
            "  wealthpilot setup --provider zhipu --key xxxx    # 指定服务（wealthpilot model list 看全部）\n"
            "  wealthpilot setup --provider ollama --model qwen2.5:14b")
        return 2
    if interactive:
        out("WealthPilot 配置：三步，每一步都可以回车跳过，之后随时能重来。")
    try:
        configured = _configure_model(args, ask, secret, out, interactive)
    except ValueError as e:
        out(f"✗ 没有保存：{e}")
        return 1
    if configured and not args.no_test:
        go = args.test or (interactive and (ask("  现在测一下能不能用？会调用一次模型，花几十个 token [Y/n] ").strip().lower() or "y") in ("y", "yes", "是"))
        if go:
            ok, message = tester()
            out(f"✓ 模型可用：{message}" if ok else f"✗ 调不通：{message}")
    _holdings(args, ask, out, interactive)
    if interactive:
        out("\n3/3 好了。接下来：\n"
            "  wealthpilot            开始用：终端里直接提问，网页版同时在 http://localhost:8000\n"
            "  wealthpilot doctor     哪里不通，它会告诉你卡在哪一环\n"
            "  想在手机上用：网页版「设置 → 手机触达」里接 Telegram、飞书或企业微信")
    return 0


# ── model：看现在用的、换一个 ───────────────────────────

def cmd_model(args, *, ask: Ask = input, secret: Ask = getpass.getpass, out: Out = print, tester: Callable[[], tuple[bool, str]] = test_model) -> int:
    s = _settings()
    action = args.action or "show"
    if action == "list":
        for p in providers.PRESETS:
            out(f"  {p['key']:<12} {_pad(p['label'], 20)} 默认模型 {p['model'] or '（需要自己填）'}" + (f"  — {p['note']}" if p["note"] else ""))
        out("换模型：wealthpilot model set <上面第一列> --key <Key> [--model <模型名>]")
        return 0
    if action == "test":
        ok, message = tester()
        out(f"✓ 模型可用：{message}" if ok else f"✗ 调不通：{message}")
        return 0 if ok else 1
    if action == "set":
        setup_args = argparse.Namespace(provider=args.name, key=args.key, model=args.model, base_url=args.base_url, sample=False, no_test=True, test=False)
        if not args.name and not args.key and not args.base_url:
            out("用法：wealthpilot model set <服务> --key <Key> [--model <模型名>]；wealthpilot model list 看有哪些服务")
            return 2
        try:
            return 0 if _configure_model(setup_args, ask, secret, out, sys.stdin.isatty() and not args.key) else 1
        except ValueError as e:
            out(f"✗ 没有保存：{e}")
            return 1
    if action == "fallback":
        return _fallback(args, out)
    from wealthpilot.routes.onboarding import model_ready
    where = f" @ {s.openai_base_url}" if s.ai_provider == "openai" else ""
    out(f"现在用的：{s.ai_provider} · {s.active_model or '（没填模型名）'}{where}" + ("" if model_ready() else "  ← 还没配好，运行 wealthpilot setup"))
    out(_fallback_line())
    out("wealthpilot model list  看能接哪些；wealthpilot model set <服务> --key <Key>  换一个；wealthpilot model test  实测一次")
    return 0


def _fallback_line() -> str:
    from wealthpilot.services.ai_client import PROVIDER_LABEL, _model_of, fallback_provider

    s = _settings()
    active = fallback_provider(s)
    if active:
        return f"备用模型：{PROVIDER_LABEL[active]} · {_model_of(s, active)}（主模型余额不足、Key 失效、限流、连不上时，这一轮自动换过去）"
    if s.ai_fallback:
        return f"备用模型：设成了 {s.ai_fallback}，但还没生效 —— 和主模型是同一家，或者那一家的 Key / 模型名没填全"
    return "备用模型：没有。主模型用不了时研究会直接停下。设一个：wealthpilot model fallback <服务> --key <Key>"


def _fallback(args, out: Out) -> int:
    """备用模型：主模型这一轮用不了时自动换过去。三个位置（DeepSeek / Claude / 兼容服务）里挑一个和主模型不同的。"""
    s = _settings()
    name = (args.name or "").strip()
    if not name:
        out(_fallback_line())
        return 0
    if name.lower() in ("off", "none", "关", "关掉"):
        _apply({"ai_fallback": ""})
        out("✓ 已关掉备用模型")
        return 0
    preset = providers.find(name)
    if preset is None:
        out(f"不认识「{name}」。可选：{'、'.join(p['key'] for p in providers.PRESETS)}；关掉用 off")
        return 2
    if preset["provider"] == s.ai_provider:
        out("备用模型要和主模型分属不同的位置：DeepSeek、Claude、兼容服务（其余几家和本机模型共用这一个位置）各算一个。"
            f"现在主模型用的就是「{preset['label']}」这个位置，换一家当备用。")
        return 1
    changes = {k: v for k, v in providers.changes_for(preset, (args.key or "").strip(), args.model or "", args.base_url or "").items()
               if k != "ai_provider" and v != ""}
    try:
        _apply({**changes, "ai_fallback": preset["provider"]})
    except ValueError as e:
        out(f"✗ 没有保存：{e}")
        return 1
    out(_fallback_line())
    return 0


# ── config：不进界面改配置 ──────────────────────────────

def cmd_config(args, *, out: Out = print) -> int:
    from wealthpilot.routes.config import _SECRETS, EDITABLE, ENV_FILE

    s = _settings()
    action = args.action or "list"
    if action == "path":
        out(str(ENV_FILE))
        return 0

    def show(key: str) -> str:
        value = getattr(_settings(), key)      # 每次现读：set 之后要显示的是新值
        if key in _SECRETS:
            return f"已配置（…{value[-4:]}）" if len(value) >= 8 else ("已配置" if value else "（空）")
        if isinstance(value, bool):
            return "开" if value else "关"
        return f"{value:g}" if isinstance(value, float) else str(value)
    if action == "list":
        for key in EDITABLE:
            out(f"  {key:<24} {show(key)}")
        out(f"配置文件：{ENV_FILE}\n改一项：wealthpilot config set <名字> <值>")
        return 0
    key = (args.key or "").lower()
    if key not in EDITABLE:
        out(f"没有「{args.key}」这一项。wealthpilot config list 看全部。")
        return 2
    if action == "get":
        out(show(key))
        return 0
    if args.value is None:
        out("用法：wealthpilot config set <名字> <值>")
        return 2
    value: object = args.value
    if isinstance(getattr(s, key), bool):
        value = args.value.strip().lower() in ("1", "true", "yes", "on", "开", "是")
    try:
        _apply({key: value})
    except ValueError as e:
        out(f"✗ 没有保存：{e}")
        return 1
    out(f"✓ {key} = {show(key)}（立即生效；正在运行的 wealthpilot 下一次读取时就会用上）")
    return 0


# ── status：现在是什么情况 ──────────────────────────────

def cmd_status(_args, *, out: Out = print) -> int:
    from sqlmodel import Session, select

    from wealthpilot import __version__
    from wealthpilot.models.automation import Automation
    from wealthpilot.models.portfolio import PortfolioHolding
    from wealthpilot.models.research import WatchItem
    from wealthpilot.routes.onboarding import model_ready
    from wealthpilot.services import budget, channels
    from wealthpilot.settings import HOME
    from wealthpilot.storage.db import get_engine

    s = _settings()
    s.ensure_dirs()
    uid = s.local_user_id
    with Session(get_engine()) as db:
        holdings = len(db.exec(select(PortfolioHolding).where(PortfolioHolding.user_id == uid)).all())
        watching = len(db.exec(select(WatchItem).where(WatchItem.user_id == uid)).all())
        autos = db.exec(select(Automation).where(Automation.user_id == uid, Automation.enabled == True)).all()  # noqa: E712
    ready = model_ready()
    paired = [c["label"] for c in channels.status_all() if c["paired"]]
    today = budget.summary(uid)["today"]
    out(f"WealthPilot v{__version__}")
    out(f"  数据目录   {HOME}")
    out(f"  模型       {s.ai_provider} · {s.active_model}" + ("" if ready else "  ← 还没配好：wealthpilot setup"))
    from wealthpilot.services.ai_client import PROVIDER_LABEL, _model_of, fallback_provider
    backup = fallback_provider(s)
    if backup:
        out(f"  备用模型   {PROVIDER_LABEL[backup]} · {_model_of(s, backup)}")
    out(f"  持仓与自选 {holdings} 只持仓，{watching} 只自选" + ("" if holdings or watching else "  ← 还是空的：wealthpilot setup 或 wealthpilot import"))
    out(f"  每日盯盘   {'开着，' + s.watch_time if s.watch_enabled else '关着'}；自动任务 {len(autos)} 条开着")
    out(f"  手机       {'、'.join(paired) + ' 已绑定' if paired else '没有绑定（网页版「设置 → 手机触达」）'}")
    limit = f"，上限 {s.daily_token_budget / 1e4:.0f} 万" if s.daily_token_budget else ""
    out(f"  今天用量   {today['tokens'] / 1e4:.1f} 万 token{limit}")
    out("开始用：wealthpilot    自检：wealthpilot doctor")
    return 0 if ready else 1


# ── skills / import / sessions ─────────────────────────

def cmd_skills(args, *, out: Out = print) -> int:
    from wealthpilot.services import skills

    action = args.action or "list"
    if action == "gallery":
        for item in skills.gallery():
            out(f"  {item['name']:<20} {_pad(item['label'], 16)} {'已装' if item['installed'] else '    '} {item['description'][:46]}")
        out("装一个：wealthpilot skills install <第一列的名字>；也可以给一个 https 链接")
        return 0
    if action == "install":
        target = args.name or ""
        try:
            if target.startswith("https://"):
                content = asyncio.run(skills.fetch_remote(target))
                parsed, problems = skills.parse(content)
                if parsed is None:
                    out("✗ 这个文件不是一个合格的方法：" + "；".join(problems))
                    return 1
                out(content)
                if not args.yes and (input(f"\n这是写给 AI 的指示，会决定它以后怎么研究。保存为「{parsed.label or parsed.name}」？[y/N] ").strip().lower() not in ("y", "yes", "是")):
                    out("没有保存")
                    return 1
                saved = skills.save(parsed.name, content)
            else:
                saved = skills.install_from_gallery(target)
        except ValueError as e:
            out(f"✗ {e}")
            return 1
        out(f"✓ 已装上「{saved.label or saved.name}」，触发词：{'、'.join(saved.triggers[:5])}")
        return 0
    if action == "remove":
        out("✓ 已删除" if skills.delete(args.name or "") else "没有这个方法")
        return 0
    found, bad = skills.discover()
    for item in found:
        out(f"  {item.name:<20} {item.label:<10} {'、'.join(item.triggers[:4])}")
    if not found:
        out("还没有方法。wealthpilot skills gallery 看现成可装的。")
    for b in bad:
        out(f"  未加载 {Path(b['path']).name}：{'；'.join(b['problems'])}")
    return 0


def cmd_import(args, *, out: Out = print) -> int:
    """从文件或管道录入持仓：每行"名称或代码 数量 成本价"。先显示识别结果，--yes 才不问。"""
    from sqlmodel import Session

    from wealthpilot.routes import onboarding
    from wealthpilot.storage.db import get_engine

    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    rows = asyncio.run(onboarding.parse_holdings({"text": text}))["rows"]
    good = [r for r in rows if r["ok"]]
    for r in rows:
        out(f"  {r['name']} {r['code']}  {r['shares']:g} 股  成本 {r['cost']:g}" if r["ok"] else f"  ✗ {r['line']}：{r['problem']}")
    if not good:
        out("一条也没认出来，没有写入。")
        return 1
    if not args.yes and (args.file == "-" or input(f"录入这 {len(good)} 条？[y/N] ").strip().lower() not in ("y", "yes", "是")):
        out("没有写入。确认无误后加 --yes 再来一次。" if args.file == "-" else "已取消")
        return 1
    _settings().ensure_dirs()
    with Session(get_engine()) as db:
        done = asyncio.run(onboarding.add_holdings({"rows": good}, db, _settings().local_user_id))
    out(f"✓ 已添加 {done['added']} 条" + "".join(f"\n  跳过：{s}" for s in done["skipped"]))
    return 0


_CHANNEL_FIELDS = {
    "telegram": (("token", "telegram_bot_token"),),
    "feishu": (("app_id", "feishu_app_id"), ("app_secret", "feishu_app_secret")),
    "wecom": (("corp_id", "wecom_corp_id"), ("agent_id", "wecom_agent_id"), ("secret", "wecom_secret"), ("token", "wecom_token"), ("aes_key", "wecom_aes_key")),
}
_CHANNEL_HOW = {
    "telegram": "找 @BotFather 建一个机器人，把它给的令牌填进来：wealthpilot channels setup telegram --token <令牌>",
    "feishu": "在飞书开放平台建一个企业自建应用，开通机器人和「接收消息」事件（长连接方式）：wealthpilot channels setup feishu --app-id <ID> --app-secret <密钥>",
    "wecom": "在企业微信后台建一个自建应用并配好接收消息：wealthpilot channels setup wecom --corp-id … --agent-id … --secret … --token … --aes-key …（要有公网能访问到的回调地址）",
}


def cmd_channels(args, *, out: Out = print) -> int:
    """手机上的渠道：配了没、绑了没；配置、生成配对码、发一条测试消息。"""
    from wealthpilot.services import channels

    action, name = args.action or "list", (args.name or "").lower()
    if action == "list":
        for c in channels.status_all():
            state = "已绑定，可以在里面提问和收简报" if c["paired"] else "配好了，还没绑定" if c["configured"] else "没有配置"
            out(f"  {c['channel']:<9} {_pad(c['label'], 10)} {state}")
            if not c["configured"]:
                out(f"            {_CHANNEL_HOW[c['channel']]}")
            elif not c["paired"]:
                out(f"            下一步：wealthpilot channels pair {c['channel']}")
        out("消息是 WealthPilot 开着的时候收发的：运行着 wealthpilot，手机上才有回应。")
        return 0
    if name not in channels.CHANNELS:
        out(f"要说是哪个渠道：{' / '.join(channels.CHANNELS)}")
        return 2
    label = channels.CHANNELS[name]
    if action == "setup":
        changes = {field: getattr(args, flag) for flag, field in _CHANNEL_FIELDS[name] if getattr(args, flag, None)}
        if not changes:
            out(_CHANNEL_HOW[name])
            return 2
        try:
            _apply(changes)
        except ValueError as e:
            out(f"✗ 没有保存：{e}")
            return 1
        if not channels.configured(name):
            missing = [f"--{flag.replace('_', '-')}" for flag, field in _CHANNEL_FIELDS[name] if not getattr(_settings(), field)]
            out(f"已保存，但{label}还缺：{' '.join(missing)}")
            return 1
        out(f"✓ {label}配好了。下一步：wealthpilot channels pair {name}")
        return 0
    if action == "pair":
        if not channels.configured(name):
            out(f"先把{label}配好。{_CHANNEL_HOW[name]}")
            return 1
        code = channels.new_pair_code(name)
        out(f"配对码：{code}（{channels.PAIR_TTL // 60} 分钟内有效）")
        out(f"保持 wealthpilot 开着，在{label}里给机器人发：/pair {code}")
        out("谁先发出这个码，谁就成为机器人的主人 —— 别把它给别人。")
        return 0
    if action == "unpair":
        channels.set_owner(None, name)
        out(f"✓ 已解除{label}的绑定。它不会再收到简报，也不再回应任何人。")
        return 0
    if action == "test":
        api, target = channels._api_for(name), channels.owner(name)
        if api is None or target is None:
            out(f"{label}还没有配置好或还没有绑定。wealthpilot channels 看卡在哪一步。")
            return 1
        try:
            asyncio.run(api.send(target, "这是 WealthPilot 发来的测试消息。收到就说明这个渠道已经通了。"))
        except Exception as e:  # noqa: BLE001 — 把对方返回的原因告诉用户
            out(f"✗ 没有发出去：{str(e)[:200]}")
            return 1
        out(f"✓ 已发到{label}，看一眼手机。")
        return 0
    return 2


def cmd_persona(args, *, out: Out = print) -> int:
    """说话方式：你希望它怎么跟你说话。只管语气和详略，不改变事实和校验规则。"""
    from wealthpilot.services import persona

    action = args.action or "show"
    try:
        if action == "path":
            out(str(persona.FILE))
        elif action == "clear":
            persona.write("")
            out("✓ 已清空。之后按默认的写法回答。")
        elif action == "use":
            if not args.text:
                for key, (label, text) in persona.PRESETS.items():
                    out(f"  {key:<8} {label}：{text.splitlines()[0]}")
                out("用其中一个：wealthpilot persona use <第一列>；用了之后可以再改，文件在 " + str(persona.FILE))
                return 0
            persona.use(args.text)
            out(f"✓ 已换成「{args.text}」。下一个问题起生效：\n\n{persona.read()}")
        elif action == "set":
            if not args.text:
                out('用法：wealthpilot persona set "先说结论，用大白话，别用套话"')
                return 2
            persona.write(args.text)
            out("✓ 已保存，下一个问题起生效。")
        else:
            text = persona.read()
            out(text or "还没有写。它现在按默认的写法回答。")
            out(f"\n现成的：wealthpilot persona use（{'、'.join(label for label, _ in persona.PRESETS.values())}）"
                f"\n自己写：wealthpilot persona set \"……\"，或直接编辑 {persona.FILE}"
                "\n它只管语气和详略；证据引用、数字核对、风险提示不会因为它被省掉。")
    except ValueError as e:
        out(f"✗ {e}")
        return 1
    return 0


def cmd_backup(args, *, out: Out = print) -> int:
    """把你的东西打成一个文件：数据库、配置、研究方法、数据连接。"""
    from wealthpilot.services import backup

    if args.list:
        found = backup.existing()
        for b in found:
            out(f"  {b['created_at'].replace('T', ' ')}  v{b['version']}  {b['size_kb']} KB  {'、'.join(b['contents'])}\n    {b['path']}")
        out("恢复其中一份：wealthpilot restore <路径>" if found else f"还没有备份（{backup.BACKUP_DIR}）。打一份：wealthpilot backup")
        return 0
    _settings().ensure_dirs()
    target = backup.create(args.dest, keys=not args.no_keys)
    info = backup.inspect(target)
    out(f"✓ 已备份到 {target}")
    out(f"  里面有：{'、'.join(info['contents']) or '（空的：还没有任何数据）'}")
    out("  没有带 Key，可以放心交给别人或放网盘。" if args.no_keys else
        "  里面带着模型 Key 和机器人令牌（文件只有你能读）。要交给别人或放网盘，用 --no-keys 重打一份。")
    out(f"  恢复：wealthpilot restore {target}")
    return 0


def cmd_restore(args, *, ask: Ask = input, out: Out = print) -> int:
    from wealthpilot.services import backup

    try:
        info = backup.inspect(args.file)
    except ValueError as e:
        out(f"✗ {e}")
        return 1
    out(f"这份备份打于 {info['created_at'].replace('T', ' ')}（v{info['version']}），里面有：{'、'.join(info['contents'])}")
    out("恢复会用它覆盖现在的数据库、配置和同名的研究方法。现在的状态会先自动备份一份，恢复错了能回去。")
    out("WealthPilot 正开着的话先退出，再恢复。")
    if not args.yes and ask("确定恢复？[y/N] ").strip().lower() not in ("y", "yes", "是"):
        out("已取消，什么都没动。")
        return 1
    done = backup.restore(args.file)
    out(f"✓ 已恢复：{'、'.join(done['restored'])}")
    out(f"  恢复之前的状态存在 {done['saved_current_to']}")
    if not info.get("with_keys"):
        out("  这份备份没有带 Key：这台机器上原有的 Key 保留着；没有的话运行 wealthpilot setup 填一个。")
    return 0


def cmd_logs(args, *, out: Out = print) -> int:
    """后台出的事：研究失败、推送没发出去、盯盘出错、模型换路。"""
    from wealthpilot.services import logs

    if args.path:
        out(str(logs.LOG_FILE))
        return 0
    lines = logs.tail(args.lines, errors=args.errors)
    if not lines:
        out("最近没有警告和错误。" if args.errors and logs.LOG_FILE.is_file() else f"还没有日志（{logs.LOG_FILE}）。WealthPilot 运行起来之后才会有。")
    for line in lines:
        out(line)
    if args.follow:
        try:
            for line in logs.follow():
                out(line)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_sessions(_args, *, out: Out = print) -> int:
    from sqlmodel import Session

    from wealthpilot.routes.research import conversations
    from wealthpilot.storage.db import get_engine

    _settings().ensure_dirs()
    query = (getattr(_args, "query", None) or "").strip()
    with Session(get_engine()) as db:
        rows = conversations(limit=30, q=query, db=db, user_id=_settings().local_user_id)
    for i, c in enumerate(rows, 1):
        out(f"  {i:>2}  {c['last_at'][5:16].replace('T', ' ')}  {c['turns']} 轮  {c['title'][:44]}" + (f"  [{c['source']}]" if c["source"] else ""))
        if c.get("match"):
            out(f"        …{c['match']}…")
    if query:
        out(f"回到其中一个接着聊：进 wealthpilot 后输入 /sessions {query}，再 /sessions <序号>" if rows else f"没有哪个会话提到过「{query}」。")
    else:
        out("回到某个会话接着聊：进 wealthpilot 后输入 /sessions <序号>；接着上一次聊：wealthpilot -c；找提到过某只股票的：wealthpilot sessions <关键词>"
            if rows else "还没有会话。运行 wealthpilot 开始提问。")
    return 0


def completion_script(shell: str, sub) -> str:
    """按 Tab 补全命令的脚本。命令表直接取自 argparse，所以加了新命令不用改这里。"""
    helps = {a.dest: (a.help or "").split("（")[0].replace("'", "").replace(":", "：") for a in sub._choices_actions}
    table: dict[str, list[str]] = {}
    for name, parser in sub.choices.items():
        choices = next((list(a.choices) for a in parser._actions if not a.option_strings and a.choices), [])
        table[name] = choices + [o for a in parser._actions for o in a.option_strings if o.startswith("--") and o != "--help"]
    rc = "zshrc" if shell == "zsh" else "bashrc"
    lines = ["# 用法：把这段存成文件，在 ~/." + rc + " 里 source 它，然后新开一个终端：",
             "#   wealthpilot completion " + shell + " > ~/.wealthpilot-completion." + shell,
             "#   echo 'source ~/.wealthpilot-completion." + shell + "' >> ~/." + rc]
    if shell == "zsh":
        lines += ["_wealthpilot() {", "  local -a commands",
                  "  commands=(" + " ".join("'" + name + ":" + helps.get(name, "") + "'" for name in table) + ")",
                  "  if (( CURRENT == 2 )); then", "    _describe 'command' commands", "  else", "    case $words[2] in"]
        lines += ["      " + name + ") compadd -- " + " ".join(words) + " ;;" for name, words in table.items() if words]
        lines += ["      *) _files ;;", "    esac", "  fi", "}",
                  "(( $+functions[compdef] )) || { autoload -Uz compinit && compinit; }", "compdef _wealthpilot wealthpilot"]
    else:
        lines += ["_wealthpilot() {", '  local cur="${COMP_WORDS[COMP_CWORD]}"',
                  '  if [ "$COMP_CWORD" -eq 1 ]; then COMPREPLY=($(compgen -W "' + " ".join(table) + '" -- "$cur")); return; fi',
                  '  case "${COMP_WORDS[1]}" in']
        lines += ["    " + name + ') COMPREPLY=($(compgen -W "' + " ".join(words) + '" -- "$cur")) ;;' for name, words in table.items() if words]
        lines += ['    *) COMPREPLY=($(compgen -f -- "$cur")) ;;', "  esac", "}", "complete -F _wealthpilot wealthpilot"]
    return "\n".join(lines) + "\n"


def register(sub) -> dict:
    """把这些命令挂到主程序的参数解析器上，返回 {命令名: 处理函数}。"""
    setup = sub.add_parser("setup", help="配好就能用：选模型服务、填 Key、放进股票（每步可跳过；参数给全了不提问）")
    setup.add_argument("--provider", help="模型服务：deepseek / claude / siliconflow / zhipu / moonshot / dashscope / ark / openrouter / openai / ollama")
    setup.add_argument("--key", help="API Key。只给这一个时，按前缀认出是 DeepSeek 还是 Claude")
    setup.add_argument("--model", help="模型名；不给就用这家服务的默认值")
    setup.add_argument("--base-url", dest="base_url", help="自定义的兼容接口地址")
    setup.add_argument("--sample", action="store_true", help="载入一份示例持仓和自选")
    setup.add_argument("--test", action="store_true", help="保存后实测一次模型（会花几十个 token）")
    setup.add_argument("--no-test", dest="no_test", action="store_true", help="不测试，也不问")

    model = sub.add_parser("model", help="现在用的是哪个模型；换一个；设备用模型（model list / set / test / fallback）")
    model.add_argument("action", nargs="?", choices=["show", "list", "set", "test", "fallback"])
    model.add_argument("name", nargs="?", help="set / fallback 时：服务的名字（fallback off 关掉备用）")
    model.add_argument("--key")
    model.add_argument("--model")
    model.add_argument("--base-url", dest="base_url")

    config = sub.add_parser("config", help="看和改配置，不用进界面（config list / get / set / path）")
    config.add_argument("action", nargs="?", choices=["list", "get", "set", "path"])
    config.add_argument("key", nargs="?")
    config.add_argument("value", nargs="?")

    sub.add_parser("status", help="现在是什么情况：模型、持仓、盯盘、手机、今天的用量")

    skills = sub.add_parser("skills", help="研究方法（skills list / gallery / install <名字或链接> / remove <名字>）")
    skills.add_argument("action", nargs="?", choices=["list", "gallery", "install", "remove"])
    skills.add_argument("name", nargs="?")
    skills.add_argument("--yes", action="store_true", help="从链接安装时不再确认")

    imp = sub.add_parser("import", help="从文件录入持仓（每行：名称或代码 数量 成本价；- 表示从管道读）")
    imp.add_argument("file")
    imp.add_argument("--yes", action="store_true", help="不再确认，直接写入认出来的")

    sessions = sub.add_parser("sessions", help="以前的会话；带关键词则只列提到过它的（sessions 宁德时代）")
    sessions.add_argument("query", nargs="?", help="关键词：问题、回答、研究过的股票名或代码里出现过")
    logs = sub.add_parser("logs", help="后台出了什么事：研究失败、推送没发出去、盯盘出错（logs --errors 只看出问题的）")
    logs.add_argument("-n", "--lines", type=int, default=40, help="看最近多少条，默认 40")
    logs.add_argument("--errors", action="store_true", help="只看警告和错误")
    logs.add_argument("-f", "--follow", action="store_true", help="一直跟着看新写进来的（Ctrl-C 停）")
    logs.add_argument("--path", action="store_true", help="只打印日志文件在哪")
    persona = sub.add_parser("persona", help="说话方式：你希望它怎么跟你说话（persona / use <预设> / set \"…\" / clear / path）")
    persona.add_argument("action", nargs="?", choices=["show", "use", "set", "clear", "path"])
    persona.add_argument("text", nargs="?", help="use 时是预设的名字，set 时是你写的那段话")
    ch = sub.add_parser("channels", help="手机上的渠道：Telegram / 飞书 / 企业微信（channels / setup / pair / unpair / test）")
    ch.add_argument("action", nargs="?", choices=["list", "setup", "pair", "unpair", "test"])
    ch.add_argument("name", nargs="?", help="telegram / feishu / wecom")
    for flag in ("token", "app-id", "app-secret", "corp-id", "agent-id", "secret", "aes-key"):
        ch.add_argument(f"--{flag}", dest=flag.replace("-", "_"))
    backup = sub.add_parser("backup", help="把你的东西打成一个文件：数据库、配置、研究方法（换电脑、重装时用）")
    backup.add_argument("dest", nargs="?", help="存到哪（文件或目录）；不给就放在数据目录的 backups/ 下")
    backup.add_argument("--no-keys", action="store_true", help="不带模型 Key 和机器人令牌（要交给别人或放网盘时用）")
    backup.add_argument("--list", action="store_true", help="看已有的备份")
    restore = sub.add_parser("restore", help="从备份恢复（会先把现在的状态自动备份一份）")
    restore.add_argument("file", help="备份文件")
    restore.add_argument("--yes", action="store_true", help="不再确认")
    return {"setup": cmd_setup, "model": cmd_model, "config": cmd_config, "status": cmd_status, "skills": cmd_skills,
            "import": cmd_import, "sessions": cmd_sessions, "logs": cmd_logs, "backup": cmd_backup, "restore": cmd_restore,
            "channels": cmd_channels, "persona": cmd_persona}
