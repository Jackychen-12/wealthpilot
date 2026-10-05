"""在网页上改配置 —— 不用再去编辑 .env。

写的就是 backend/.env：改完立即生效（重新读取配置），重启后也还在。
只允许本机访问：这个接口能改模型 Key，不能暴露给网络上的其他人。Key 只写不读，读取时只返回是否已配置和末四位。
"""

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from wealthpilot.settings import Settings, get_settings, reload_settings

router = APIRouter(prefix="/settings", tags=["settings"])

ENV_FILE = Path(".env")
_SECRETS = ("anthropic_api_key", "deepseek_api_key")
# 网页上能改的项：字段名 -> 说明。其余配置（JWT 密钥、数据库路径等）仍只能改文件
EDITABLE = (
    "ai_provider", "anthropic_api_key", "anthropic_model", "deepseek_api_key", "deepseek_model",
    "advice_mode", "checkpoints_enabled", "broker", "paper_initial_cash",
    "watch_enabled", "watch_time", "watch_move_pct", "alert_webhook_url",
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


@router.put("")
def update_settings(body: dict, request: Request):
    _local_only(request)
    changes = {k: v for k, v in body.items() if k in EDITABLE}
    # Key 留空表示"不改"，而不是清空
    changes = {k: v for k, v in changes.items() if not (k in _SECRETS and not str(v).strip())}
    if not changes:
        return _view()
    for k, v in changes.items():
        if isinstance(v, str) and re.search(r"[\r\n]", v):
            raise HTTPException(422, f"{k} 不能包含换行")
    if changes.get("ai_provider") not in (None, "anthropic", "deepseek") or changes.get("broker") not in (None, "none", "paper"):
        raise HTTPException(422, "取值不合法")
    try:   # 先用模型校验一遍，别把写不合法的值落到文件里
        Settings(**{**get_settings().model_dump(), **changes})
    except ValidationError as e:
        raise HTTPException(422, "；".join(f"{err['loc'][0]}：{err['msg']}" for err in e.errors())) from e
    _write_env({k.upper(): str(v).lower() if isinstance(v, bool) else str(v).strip() for k, v in changes.items()})
    reload_settings()
    return _view()


@router.post("/test")
async def test_model(request: Request):
    """用当前配置向模型发一句话，确认 Key 和模型名可用。"""
    _local_only(request)
    import asyncio

    from wealthpilot.services.ai_client import create_ai_client

    settings = get_settings()
    try:
        client = create_ai_client(settings)
        result = await asyncio.to_thread(client.create, model=settings.active_model, max_tokens=2000,
                                         system="只回复两个字：正常", messages=[{"role": "user", "content": "测试"}])
    except Exception as e:  # noqa: BLE001 — 把供应商返回的原因原样告诉用户
        return {"ok": False, "provider": settings.ai_provider, "model": settings.active_model, "error": str(e)[:300]}
    return {"ok": True, "provider": settings.ai_provider, "model": settings.active_model, "reply": (result.text or "").strip()[:40]}
