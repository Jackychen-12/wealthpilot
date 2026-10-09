"""现成的金融数据 MCP 服务：能不能接、要什么、怎么接。

这张表是 2026 年 10 月查的公开资料整理出来的，**没有一家实际连过**（都要账号或 Key，我们没有）。
每一条都写明了是官方的还是社区的、要什么凭据、现在这里的连接器接不接得上。
接进来之后一律只读：下单、撤单、转账、增删自选这类工具会被屏蔽，这一条配置绕不过。
"""

from __future__ import annotations

PRESETS: list[dict] = [
    {
        "key": "mx", "label": "东方财富妙想", "official": False, "status": "ready",
        "provides": "诊股、财务、条件选股、热点板块、盈利预测，以及用一句话查行情财务、搜公告研报新闻（共 11 个工具）",
        "needs": "① 到妙想的申请页领一个 MX_APIKEY；② 在自己电脑上把社区项目 eastmoney-skills2mcp 跑起来（Node 项目，启动后默认在本机 9000 端口）",
        "links": ["https://marketing.dfcfs.com/views/finskillshub/indexZfdcxNpu?appfenxiang=1", "https://github.com/essos-bot/eastmoney-skills2mcp"],
        "caveat": "东方财富没有公开的官方 MCP 地址。这是社区项目对妙想接口的封装，不是东方财富出的；跑别人的代码之前自己看一眼。"
                  "它的 MX_APIKEY 填在那个项目自己的配置里，这里要的令牌是你给那个服务设的 AUTH_TOKEN（没设就不用填）。",
        "connector": {"name": "mx", "label": "妙想", "kind": "data", "transport": "http", "url": "http://localhost:9000/mcp", "auth_env": "MX_MCP_TOKEN",
                      "description": "东方财富妙想（社区封装）：诊股、财务、选股、热点、资讯搜索、自然语言查数。"},
        "token_optional": True,
    },
    {
        "key": "ifind", "label": "同花顺 iFinD", "official": True, "status": "needs_url",
        "provides": "A 股分析、公募基金分析、宏观与行业数据、公告与资讯四个模块，二十多个工具",
        "needs": "要有 iFinD 终端账号：登录终端后在里面拿“专属配置密钥”和服务地址",
        "links": ["https://stock.10jqka.com.cn/20260312/c675239015.shtml"],
        "caveat": "同花顺 2026 年 3 月发布。服务地址和密钥的格式没有公开，以终端里给你的为准；接不上的话找 iFinD 的客户经理。",
        "connector": {"name": "ifind", "label": "同花顺 iFinD", "kind": "data", "transport": "http", "url": "", "auth_env": "IFIND_MCP_TOKEN",
                      "description": "同花顺 iFinD：A 股、基金、宏观与行业、公告与资讯。"},
    },
    {
        "key": "tushare", "label": "Tushare（社区封装）", "official": False, "status": "needs_url",
        "provides": "A 股与港股的行情、财务报表、指数、宏观等，具体看你选的那个封装",
        "needs": "Tushare 的 token，加上自己跑一个社区的 Tushare MCP 服务（有好几个版本，按它的说明启动后把地址填进来）",
        "links": ["https://tushare.pro/"],
        "caveat": "都是个人维护的项目，能查到什么取决于你的 Tushare 积分等级。",
        "connector": {"name": "tushare", "label": "Tushare", "kind": "data", "transport": "http", "url": "", "auth_env": "TUSHARE_MCP_TOKEN",
                      "description": "Tushare（社区封装）：行情、财务报表、指数、宏观。"},
        "token_optional": True,
    },
    {
        "key": "longbridge", "label": "长桥 Longbridge", "official": True, "status": "unsupported",
        "provides": "港股、美股的实时行情、K 线、公司基本面、分红、估值、账户与持仓（官方说有一百多个工具）",
        "needs": "长桥账户，用浏览器登录授权（OAuth）",
        "links": ["https://open.longbridge.com/docs/mcp"],
        "caveat": "现在接不了：它只认浏览器登录授权，这里的连接器只会带一个固定令牌。"
                  "港股、美股的行情、日线和财务指标已经内置了，不接它也能研究；它多出来的是实时深度行情和你的券商账户。",
        "connector": None,
    },
    {
        "key": "custom", "label": "别的 MCP 服务", "official": False, "status": "needs_url",
        "provides": "任何提供 HTTP 接入的 MCP 服务：券商的只读查询、别的数据商、你自己写的",
        "needs": "服务地址；要鉴权的话再给一个令牌",
        "links": [],
        "caveat": "默认按 Authorization: Bearer <令牌> 发送。对方用别的请求头时，装完到 connectors.json 里改 auth_header 和 auth_scheme。",
        "connector": {"name": "custom", "label": "自定义服务", "kind": "custom", "transport": "http", "url": "", "auth_env": "CUSTOM_MCP_TOKEN", "description": ""},
        "token_optional": True,
    },
]
BY_KEY = {p["key"]: p for p in PRESETS}
STATUS_LABEL = {"ready": "可以接", "needs_url": "可以接，要你提供地址", "unsupported": "现在接不了"}
