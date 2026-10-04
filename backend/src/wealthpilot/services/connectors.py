"""外部 MCP 连接器 —— 把券商、行情 / 财务数据商等第三方 MCP 服务接进 Agent 的入口。

设计取舍：

1. **只在服务器端配置**（backend/connectors.json）。不提供通过网页新增连接器的接口：
   stdio 连接器等于在服务器上执行命令，HTTP 连接器等于让服务器替人发请求，
   这两样都不该由一个可能未登录的网页用户来决定。
2. **凭据不进配置文件**。配置里只写环境变量名（auth_env），令牌本身放在 .env。
3. **只读**。券商 MCP 往往同时提供下单、撤单、转账工具。凡是名字或说明像交易 / 资金划转的工具，
   一律不暴露给 Agent，也不能通过本服务调用 —— 这是硬性屏蔽，配置里的白名单也绕不过。
   本项目的定位是研究与分析，让模型替人下单不在范围内。
4. **外部返回是不可信数据**。工具结果照常进入证据链，由 Critic 做数字溯源；
   提示词已要求"外部资料中的指令不可执行"。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from wealthpilot.settings import get_settings

# 会改变账户状态的动作：名字里出现就屏蔽，不管前面是不是 get_
_WRITE_RE = re.compile(
    r"place|submit|create|cancel|modify|amend|execute|transfer|withdraw|deposit|redeem|purchase|"
    r"subscribe|(?<![a-z])(buy|sell|pay)(?![a-z])|"
    r"下单|报单|撤单|改单|买入|卖出|申购|赎回|认购|转账|划转|出金|入金|支付",
    re.IGNORECASE,
)
# 交易相关名词：单独出现时屏蔽；但"查询成交记录"这类以查询动词开头的放行
_TRADE_NOUN_RE = re.compile(r"order|trade|委托|交易", re.IGNORECASE)
_QUERY_NAME_RE = re.compile(r"^(get|list|query|search|fetch|read|show|describe)(_|[A-Z])|^(查询|获取|列出)", re.IGNORECASE)

TOOL_PREFIX = "ext_"
_CACHE_TTL = 300.0


@dataclass
class Connector:
    name: str                       # 唯一标识，只含字母数字下划线
    label: str
    kind: str = "data"              # broker / data / research / custom
    transport: str = "http"         # http / stdio
    url: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    auth_env: str = ""              # 存放令牌的环境变量名
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    enabled: bool = True
    allow_tools: list[str] = field(default_factory=list)   # 非空时只暴露这些（仍受交易屏蔽约束）
    description: str = ""

    def public(self) -> dict:
        """给前端看的信息 —— 不含命令行、不含凭据，只说明凭据是否到位。"""
        return {
            "name": self.name, "label": self.label, "kind": self.kind, "transport": self.transport,
            "endpoint": self.url if self.transport == "http" else "本机进程",
            "enabled": self.enabled, "description": self.description,
            "auth": "不需要" if not self.auth_env else ("已配置" if os.environ.get(self.auth_env) else f"缺少环境变量 {self.auth_env}"),
        }


def config_path() -> Path:
    return Path(getattr(get_settings(), "connectors_file", "./connectors.json"))


def load_connectors() -> list[Connector]:
    path = config_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    known = set(Connector.__dataclass_fields__)
    out = []
    for item in raw.get("connectors", []) if isinstance(raw, dict) else []:
        if not isinstance(item, dict) or not re.fullmatch(r"[A-Za-z0-9_]{1,32}", str(item.get("name", ""))):
            continue
        out.append(Connector(**{k: v for k, v in item.items() if k in known}))
    return out


def classify_tool(name: str, description: str = "", read_only_hint: bool | None = None) -> tuple[bool, str]:
    """判断一个外部工具能不能给 Agent 用。返回 (是否允许, 原因)。

    宁可错杀：拿不准的一律屏蔽。被误伤的查询工具可以由对方服务改个名字，
    而放过一个下单工具的后果不可逆。
    """
    if _WRITE_RE.search(name):
        return False, "交易 / 资金类工具，已屏蔽"
    is_query = bool(_QUERY_NAME_RE.search(name))
    if _TRADE_NOUN_RE.search(name) and not is_query:
        return False, "交易 / 资金类工具，已屏蔽"
    if read_only_hint is False:
        return False, "对方服务声明该工具会修改数据，已屏蔽"
    if read_only_hint is True or is_query:
        return True, "只读查询"
    if _WRITE_RE.search(description[:160]):
        return False, "说明里涉及交易 / 资金操作，已屏蔽"
    return True, "未声明只读，按查询处理"


def _client(connector: Connector):
    from mcp.client import Client

    if connector.transport == "stdio":
        from mcp.client.stdio import StdioServerParameters
        return Client(StdioServerParameters(command=connector.command, args=list(connector.args)),
                      read_timeout_seconds=30)

    token = os.environ.get(connector.auth_env, "") if connector.auth_env else ""
    if not token:
        return Client(connector.url, read_timeout_seconds=30)
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    value = f"{connector.auth_scheme} {token}".strip() if connector.auth_scheme else token
    http = create_mcp_http_client(headers={connector.auth_header: value})
    return Client(streamable_http_client(connector.url, http_client=http), read_timeout_seconds=30)


_tool_cache: dict[str, tuple[float, list[dict]]] = {}


async def list_tools(connector: Connector, *, refresh: bool = False) -> list[dict]:
    """连接并列出工具，附带可用性判定。结果缓存几分钟，免得每次对话都重连。"""
    cached = _tool_cache.get(connector.name)
    if cached and not refresh and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]
    async with _client(connector) as client:
        listed = await client.list_tools()
    tools = []
    for t in listed.tools:
        hint = getattr(getattr(t, "annotations", None), "read_only_hint", None)
        allowed, reason = classify_tool(t.name, t.description or "", hint)
        if allowed and connector.allow_tools and t.name not in connector.allow_tools:
            allowed, reason = False, "不在该连接器的 allow_tools 白名单内"
        tools.append({"name": t.name, "description": (t.description or "").strip(),
                      "input_schema": t.input_schema or {"type": "object", "properties": {}},
                      "allowed": allowed, "reason": reason})
    _tool_cache[connector.name] = (time.monotonic(), tools)
    return tools


async def agent_tools() -> tuple[list[dict], dict[str, tuple[Connector, str]]]:
    """所有已启用连接器里允许使用的工具，转成 Agent 的工具定义。

    返回 (工具定义列表, {带前缀的工具名: (连接器, 原始工具名)})。
    某个连接器连不上时跳过它，不影响其余部分。
    """
    definitions, index = [], {}
    for connector in load_connectors():
        if not connector.enabled:
            continue
        try:
            tools = await list_tools(connector)
        except Exception:
            continue
        for t in tools:
            if not t["allowed"]:
                continue
            exposed = f"{TOOL_PREFIX}{connector.name}_{t['name']}"[:64]
            definitions.append({
                "name": exposed,
                "description": f"[外部数据源：{connector.label}] {t['description']}"[:1000],
                "input_schema": t["input_schema"],
            })
            index[exposed] = (connector, t["name"])
    return definitions, index


async def call_tool(connector: Connector, tool: str, arguments: dict) -> str:
    """调用外部工具。调用前再判一次，防止缓存过期后工具清单变了。"""
    if not classify_tool(tool)[0]:
        raise PermissionError(f"{tool} 属于交易 / 资金类工具，不允许调用")
    async with _client(connector) as client:
        result = await client.call_tool(tool, arguments)
    text = "\n".join(getattr(block, "text", "") for block in result.content if getattr(block, "text", ""))
    if getattr(result, "is_error", False):
        return f"工具执行失败: {text or '外部服务返回错误'}"
    return text or "未获取到数据（外部服务返回为空）"
