"""在网页上改配置 —— 不用再去编辑 .env。

写的就是 backend/.env：改完立即生效（重新读取配置），重启后也还在。
只允许本机访问：这个接口能改模型 Key，不能暴露给网络上的其他人。Key 只写不读，读取时只返回是否已配置和末四位。
"""

import os
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from sqlmodel import Session

from wealthpilot.services import memory, providers
from wealthpilot.settings import HOME, Settings, get_settings, reload_settings
from wealthpilot.storage.db import get_engine

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE = HOME / ".env"
_SECRETS = ("anthropic_api_key", "deepseek_api_key", "openai_api_key", "telegram_bot_token", "feishu_app_secret", "wecom_secret", "wecom_token", "wecom_aes_key")
# 网页上能改的项：字段名 -> 说明。其余配置（JWT 密钥、数据库路径等）仍只能改文件
EDITABLE = (
    "ai_provider", "anthropic_api_key", "anthropic_model", "deepseek_api_key", "deepseek_model",
    "openai_api_key", "openai_model", "openai_base_url", "openai_json_mode", "openai_max_tokens",
    "advice_mode", "checkpoints_enabled", "broker", "paper_initial_cash",
    "watch_enabled", "watch_time", "watch_move_pct", "alert_webhook_url",
    "telegram_bot_token", "telegram_api_base", "auto_daily_runs_max", "update_check",
    "feishu_app_id", "feishu_app_secret", "feishu_api_base", "wecom_corp_id", "wecom_agent_id", "wecom_secret", "wecom_token", "wecom_aes_key",
    "daily_token_budget", "token_price_input", "token_price_output", "research_reuse_hours", "debate_enabled",
)
_LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}


def _local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL:
        raise HTTPException(403, "配置只能在运行后端的这台机器上修改")


def _mask(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 8 else ("已配置" if value else "")


def _view() -> dict:
    s = get_settings()
    values = {k: getattr(s, k) for k in EDITABLE if k not in _SECRETS}
    return {
        "values": values,
        "secrets": {k: {"set": bool(getattr(s, k)) and not getattr(s, k).endswith("xxx"), "hint": _mask(getattr(s, k))} for k in _SECRETS},
        # 进程环境变量（Docker、shell 里 export 的）优先级高于 .env，这些项在网页上改了也不会生效
        "overridden": [k for k in EDITABLE if k.upper() in os.environ],
        "active_model": s.active_model, "env_file": str(ENV_FILE.resolve()),
        "presets": [p for p in providers.PRESETS if p["provider"] == "openai"],
    }


@router.get("")
def read_settings(request: Request):
    _local_only(request)
    return _view()


def _write_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    left = dict(updates)
    for i, line in enumerate(lines):
        match = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if match and match.group(1) in left:
            lines[i] = f"{match.group(1)}={left.pop(match.group(1))}"
    lines += [f"{k}={v}" for k, v in left.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV_FILE.chmod(0o600)


@router.get("/version")
async def version(request: Request, refresh: bool = False):
    """现在是哪一版、有没有新的。默认读缓存；refresh=1 时去远端看一眼。"""
    import asyncio

    from wealthpilot.services import upgrade

    _local_only(request)
    # 平时只读缓存（后台每半天检查一次）；用户点了「检查更新」才去远端看
    return await asyncio.to_thread(upgrade.check, force=True) if refresh else await asyncio.to_thread(upgrade.status)


@router.get("/usage")
def usage(request: Request):
    """模型用量：今天、近 7 天、近 30 天，按天、按用途。"""
    from wealthpilot.services import budget

    _local_only(request)
    return budget.summary(get_settings().local_user_id)


@router.get("/doctor")
async def doctor(request: Request, model: bool = False):
    """自检：数据源、模型、数据库、手机触达、版本，各自通不通、不通怎么修。model=1 时实测一次模型调用。"""
    from wealthpilot.services import doctor as checks

    _local_only(request)
    port = request.url.port or get_settings().port
    return {"items": await checks.run(online=model, port=port, serving=True)}


def apply_changes(body: dict) -> list[str]:
    """校验并写入配置，返回改了哪些项。网页设置和命令行（wealthpilot setup / config set）都走这里。

    不合法时抛 ValueError（带一句人话），什么都不写。Key 留空表示"不改"，而不是清空。
    """
    changes = {k: v for k, v in body.items() if k in EDITABLE}
    changes = {k: v for k, v in changes.items() if not (k in _SECRETS and not str(v).strip())}
    if not changes:
        return []
    for k, v in changes.items():
        if isinstance(v, str) and re.search(r"[\r\n]", v):
            raise ValueError(f"{k} 不能包含换行")
    if changes.get("ai_provider") not in (None, "anthropic", "deepseek", "openai") or changes.get("broker") not in (None, "none", "paper"):
        raise ValueError("取值不合法")
    try:   # 先用模型校验一遍，别把写不合法的值落到文件里
        Settings(**{**get_settings().model_dump(), **changes})
    except ValidationError as e:
        raise ValueError("；".join(f"{err['loc'][0]}：{err['msg']}" for err in e.errors())) from e
    _write_env({k.upper(): str(v).lower() if isinstance(v, bool) else str(v).strip() for k, v in changes.items()})
    reload_settings()
    with Session(get_engine()) as db:   # 只记改了哪些项，不记值（里面可能有 Key）
        memory.record(db, get_settings().local_user_id, "settings/changed", "、".join(sorted(changes)), {"keys": sorted(changes)}, actor="user")
    return sorted(changes)


@router.put("")
def update_settings(body: dict, request: Request):
    _local_only(request)
    try:
        apply_changes(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _view()
