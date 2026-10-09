"""外部 MCP 连接器路由 —— 只读：查看已配置的连接器、测试连通性。

没有"新增 / 修改连接器"的接口，原因见 services/connectors.py 顶部说明。
"""

from fastapi import APIRouter, HTTPException

from wealthpilot.services import connectors as svc

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("")
def list_connectors():
    """已配置的连接器，以及配置文件的位置。"""
    return {
        "config_file": str(svc.config_path()),
        "configured": svc.config_path().exists(),
        "connectors": [c.public() for c in svc.load_connectors()],
    }


@router.get("/presets")
def connector_presets():
    """现成的金融数据 MCP 服务：能不能接、要什么。接入只能在本机的命令行里做（wealthpilot connectors add）。"""
    from wealthpilot.services.connector_presets import PRESETS, STATUS_LABEL
    return [{k: p[k] for k in ("key", "label", "official", "status", "provides", "needs", "links", "caveat")} | {"status_label": STATUS_LABEL[p["status"]]} for p in PRESETS]


@router.post("/{name}/test")
async def test_connector(name: str):
    """连接一次并列出它提供的工具，标明哪些可用、哪些被屏蔽。"""
    connector = next((c for c in svc.load_connectors() if c.name == name), None)
    if connector is None:
        raise HTTPException(404, f"没有名为 {name} 的连接器")
    try:
        tools = await svc.list_tools(connector, refresh=True)
    except Exception as e:  # noqa: BLE001 — 外部服务什么错都可能抛，原样告诉用户
        return {"ok": False, "error": f"连接失败：{type(e).__name__}: {e}"[:300], "tools": []}
    return {
        "ok": True,
        "tools": [{k: t[k] for k in ("name", "description", "allowed", "reason")} for t in tools],
        "allowed_count": sum(t["allowed"] for t in tools),
        "blocked_count": sum(not t["allowed"] for t in tools),
    }
