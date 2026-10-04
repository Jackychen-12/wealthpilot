<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI 多智能体智能投顾系统</strong><br/>
  <sub>Multi-Agent Architecture · Claude & DeepSeek · 19 Real-time Tools · One-command Deploy</sub>
</p>

<p align="center">
  <a href="https://jackychen-12.github.io/wealthpilot/">Live Demo</a> &nbsp;|&nbsp;
  <a href="https://jackychen-12.github.io/wealthpilot/showcase.html">Showcase</a> &nbsp;|&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;|&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;|&nbsp;
  <a href="#api-reference">API Docs</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" alt="React 18" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude_AI-Multi--Agent-7C3AED?logo=anthropic&logoColor=white" alt="Claude AI" />
  <img src="https://img.shields.io/badge/DeepSeek-Supported-4F46E5" alt="DeepSeek" />
  <img src="https://img.shields.io/badge/AKShare-Free_Data-FF6B35" alt="AKShare" />
  <img src="https://img.shields.io/badge/MCP-Server-10B981" alt="MCP Server" />
  <img src="https://github.com/Jackychen-12/wealthpilot/actions/workflows/deploy.yml/badge.svg" alt="Deploy" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

---

## Why WealthPilot?

大多数投资分析工具只是简单地调用一次 LLM 生成文本。WealthPilot 不同——它是一个**完整的多智能体系统**，由 Planner 把问题拆成任务图，4 个专业 Agent 并发取证，Critic 双闸门审核证据与回答，通过后才发布结论 —— 每个数字都能追溯到一次工具调用。

### 核心优势

| | 优势 | 说明 |
|--|------|------|
| 🤖 | **Planner 多智能体架构** | Planner 拆解任务 DAG → 4 个专业 Agent 并发执行 → Critic 双闸门 → Synthesizer 整合并消解冲突 |
| 🎯 | **风险画像硬约束** | 风险测评结果注入 Planner/Agent/Synthesizer 三处；未测评时不得给出具体仓位比例 |
| 🔍 | **证据溯源 + Critic 闸门** | 每次工具调用生成证据 ID `[E-…]`，回答必须逐条引用；数字回查不到、证据不足或越过画像约束的草稿不会发布 |
| 🔧 | **19 个实时工具** | 行情、持仓、风险之外，还有持仓穿透、规则回测，以及把算术从 LLM 手里拿走的 compute/check 工具 |
| 🌐 | **双模型支持** | Claude & DeepSeek 一行配置切换，Provider 抽象层自动适配 Anthropic SDK / OpenAI SDK |
| 📊 | **免费实时数据** | AKShare + 东方财富 + 天天基金 + 新浪财经，无需付费数据源 |
| ⚡ | **过程可见的 SSE** | 规划、工具调用、证据、Critic 结论实时推送；正文在通过校验后才下发，未过审的草稿不会流到用户面前 |
| 🔌 | **MCP Server** | 19 个工具通过 MCP 协议暴露，Claude Code / Cursor 直接调用，无需自建 Agent |
| 💻 | **多入口调用** | Web UI / 终端交互 / CLI 管道 / MCP，任选其一接入分析能力 |
| 🎨 | **精致 Demo 体验** | 离线演示模式完整模拟多 Agent 流程（路由 → 工具调用 → 流式输出），SVG 图标系统，页面转场动画 |
| 🔐 | **多租户隔离** | JWT 认证 + 用户级数据隔离，对话历史持久化 |
| 🚀 | **一键部署** | `make setup` → 编辑 API Key → `make dev`，3 步启动完整系统 |

---

## Quick Start

### 方式一：Makefile（推荐）

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git
cd wealthpilot

make setup          # 安装依赖 + 复制 .env
# 编辑 backend/.env，填入 API Key（见下方配置说明）
make dev            # 启动后端(:8000) + 工作台(:5180)
```

打开 http://localhost:5180 即可使用。

### 方式二：CLI 交互式初始化

```bash
cd backend
uv sync
uv run python -m wealthpilot init   # 交互式选择 AI 提供商 + 输入 API Key
uv run python -m wealthpilot chat   # 终端对话模式，直接体验多智能体
```

### 方式三：Docker Compose

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git && cd wealthpilot
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 API Key
docker compose up --build -d
# Frontend: http://localhost:5173  |  Backend API: http://localhost:8000/docs
```

### 配置 AI 提供商

编辑 `backend/.env`，**只需改 2 行**即可启用 AI 能力：

**选项 A — Claude（默认，推荐）**
```env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx    # 从 https://console.anthropic.com/ 获取
```

**选项 B — DeepSeek（国内可用，成本更低）**
```env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx         # 从 https://platform.deepseek.com/ 获取
```

常用可选项（完整列表见 `backend/.env.example`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_MAX_TOKENS` | 16000 | 单次模型输出上限。默认开启思考的模型，思考 token 也计入此值，设太小回答会被截断 |
| `AGENT_MAX_TOOL_ROUNDS` | 3 | 每个 Agent 的工具调用轮次；用完后强制基于已有证据作答 |
| `CRITIC_ENABLED` | true | 关闭后跳过证据审核与回答校验（不建议） |
| `CRITIC_MIN_GROUNDING_RATE` | 0.9 | 重写用尽后，数字溯源率不低于此值的草稿带标注发布；设为 1 则一律拒答 |
| `RUN_TIMEOUT_SECONDS` / `AI_TIMEOUT_SECONDS` | 180 / 60 | 整轮研究 / 单次模型请求的超时 |
| `LOCAL_USER_ID` | 0 | CLI 与 MCP 读取哪个用户的持仓和画像（0 = 未登录的匿名档） |

配置完成后运行 `make config` 验证。占位值（`sk-ant-xxx`）会被视为未配置。

### 不配置 API Key 也能用

| 功能 | 无 API Key | 有 API Key |
|------|:----------:|:----------:|
| 持仓管理（增删改查 + CSV 导入） | ✅ | ✅ |
| 实时行情（指数、新闻、净值） | ✅ | ✅ |
| 量化分析（Sharpe、回撤、健康度） | ✅ | ✅ |
| AI 多智能体对话 | 前端演示模式（模拟流程）；后端直接提示未配置 Key | **多 Agent 实时分析** |
| 截图 OCR 导入 | ❌ | ✅（仅 Anthropic Key，Claude Vision） |
| MCP Server 的 19 个工具 | ✅（不调用 LLM） | ✅ |
| AI 周报 | 模板回退 | **LLM 智能生成** |

---

## Architecture

### 多智能体系统

WealthPilot 的 AI 核心是 **Planner + 4 个专业 Agent + Critic + Synthesizer** 的协作流程，不是单次 LLM 调用：

```
用户消息
   │
   ▼
┌──────────────────┐
│  Planner         │  任务拆解（LLM；不可用时关键词兜底）
│                  │  → TaskGraph(DAG) + success_criteria
└──────┬───────────┘
       │  无依赖的任务同波并发（asyncio.gather）
       ├──────────────┬───────────────┬──────────────┐
       ▼              ▼               ▼              ▼
  📊 Market      💼 Portfolio     🛡️ Risk        🔬 Quant
   3 工具         4 + 4 工具       5 + 4 工具      3 + 4 工具
   基金信息        总览/归因        回撤/相关性      持仓穿透
   净值走势        健康度/建议      区间收益/对比    重仓股重叠
   财经新闻                                        规则回测
                 └── 共享 4 个 compute/check 工具：集中度、变动推演、
                     画像约束校验、回撤约束下的仓位上限 ──┘
       │  每次工具调用 → 一条带 ID 的证据 [E-…]（来源、数据日期、口径）
       ▼
┌──────────────────┐   不足 → 补充任务重跑（最多 CRITIC_MAX_REPLANS 轮）
│ Critic 闸门 A    │   证据能否支撑 success_criteria（一次小额 LLM 调用）
└──────┬───────────┘
       ▼
┌──────────────────┐
│ Synthesizer      │  跨 Agent 整合 + 冲突消解（单任务时直接采用该 Agent 的回答）
└──────┬───────────┘
       ▼
┌──────────────────┐   不过 → 带意见重写（最多 CRITIC_MAX_REWRITES 次）
│ Critic 闸门 B    │   纯代码：数字溯源、证据引用、画像约束
└──────┬───────────┘
       ▼
  发布回答（status: passed；有证据缺口、或个别数字无法核对时为 partial，回答里点名标注）
  否则只发布未通过的原因（insufficient_data / rejected / failed），不发布草稿
```

**关键设计**

1. **Planner 取代 Router**：Router 只能三选一，"我半导体仓位重不重、要不要调"这类需要持仓 + 风险 + 市场三方面证据的问题必然答不全。Planner 产出一张任务 DAG，无依赖任务并发执行。
2. **真并发**：`BaseAgent.run` 是 async 的；同一轮内的多个工具调用用 `asyncio.gather` 并发。同步 SDK 通过 `streaming.py` 搬到工作线程，不阻塞事件循环。
3. **证据是一等公民**：工具结果连同证据 ID 一起交给模型，回答逐行引用 `[E-…]`；同一轮研究内相同的工具调用只执行一次，并有调用次数与超时预算。
4. **宁可不答，不可乱答**：Critic 不通过、任务失败、输出被截断或被拒绝时，系统发布的是"为什么没有结论"，而不是未经校验的草稿。
5. **风险画像是硬约束**：`InvestorProfile` 注入 Planner / 各专业 Agent / Synthesizer。未完成测评时，不得给出具体仓位比例或止损价位。
6. **算术不交给 LLM**：占比、变动后的集中度、仓位上限都由 compute/check 工具确定性计算。
7. **轮次用尽也要收尾**：工具轮次用完后禁止继续调用，强制模型基于已取得的证据作答并说明缺口。

### Provider 抽象层

```
                    ┌─────────────────┐
                    │   BaseAgent     │  ← 统一接口：stream / create
                    │   (Anthropic    │
                    │    format)      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼                             ▼
    ┌──────────────────┐          ┌──────────────────┐
    │ AnthropicAIClient│          │ DeepSeekAIClient  │
    │ Anthropic SDK    │          │ OpenAI SDK        │
    │ stream()→SSE     │          │ 自动转换:          │
    │ create()→Result  │          │  tools→functions  │
    └──────────────────┘          │  tool_result→tool │
                                  └──────────────────┘
```

Agent 内部始终说 Anthropic 格式，Provider 层在 API 调用边界自动转换——切换提供商零代码改动。

### 系统全景

```
┌──────────────────────────────────────────────────────────────┐
│                Frontend (Vite + React 18 + TypeScript)        │
│     11 pages · API layer with mock fallback · SSE streaming   │
│     SVG icon system · Animated transitions · Smart demo mode  │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────┴─────────────────────────────────┐
│                Backend (FastAPI · 37 endpoints)                │
│                                                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────────┐  ┌────────┐│
│  │ Portfolio  │  │  Market   │  │  Multi-Agent  │  │Analysis││
│  │ CRUD +    │  │  Data     │  │   System      │  │Engine  ││
│  │ CSV/OCR   │  │  Service  │  │               │  │Sharpe/ ││
│  │ Import    │  │           │  │ ┌───────────┐ │  │DD/Corr/││
│  └───────────┘  └───────────┘  │ │  Planner  │ │  │Health  ││
│                                │ └─┬───┬───┬─┘ │  └────────┘│
│                                │   │   │   │   │            │
│                                │   ▼   ▼   ▼   │            │
│                                │ Mkt Port Risk │            │
│                                │ Quant → Critic│            │
│                                └───────────────┘            │
│                                                              │
│  ┌──────────────────┐  ┌─────────┐  ┌───────────────────┐   │
│  │   SQLite          │  │  JWT    │  │ AI Client Layer   │   │
│  │ Portfolio + Chat  │  │  Auth   │  │ Anthropic/DeepSeek│   │
│  │ + Users           │  │         │  │ Auto-adapter      │   │
│  └──────────────────┘  └─────────┘  └───────────────────┘   │
└──────────────────────────────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
   Claude / DeepSeek     AKShare           东方财富/新浪
   (Multi-Agent +      (基金净值 +         (指数行情
    OCR + Report)       排名 + 宏观)        + 新闻)
```

### 技术栈

| 层 | 技术 |
|----|------|
| Frontend | Vite 6, React 18, TypeScript 5.6, SSE Streaming, SVG Icon System |
| Backend | Python 3.11+, FastAPI, SQLModel, Uvicorn |
| AI | Claude API (Anthropic SDK) + DeepSeek (OpenAI SDK)，Planner / 4 Agent / Critic / Synthesizer |
| 数据源 | AKShare（免费）、东方财富 API、天天基金 API、新浪财经 API |
| 认证 | JWT (PyJWT) + bcrypt，多租户隔离 |
| 存储 | SQLite（开发），可替换 PostgreSQL |
| 部署 | Docker Compose, Makefile, Railway, GitHub Pages |
| 集成 | MCP Server (stdio), CLI 非交互模式 |
| CLI | `python -m wealthpilot run/init/config/chat/mcp/ask` |

---

## Features

### 11 个页面

```
Home ─────→ Portfolio（持仓管理：手动添加 / CSV导入 / 截图OCR）
  │
  ├──→ Overview ──→ Attribution（收益归因：按基金/行业/资产类型）
  │         ├──→ Drawdown（回撤分析 + 恢复天数）
  │         ├──→ Health（5 维健康度雷达图）
  │         ├──→ Suggestions（AI 调仓建议）
  │         └──→ Weekly Report（LLM 生成周报）
  │
  ├──→ Chat（多智能体 AI 对话 · Planner → 4 专业 Agent → Critic · SSE）
  ├──→ Login（JWT 注册/登录）
  └──→ Risk Profile（风险偏好问卷评估）
```

### 功能矩阵

| 模块 | 功能 | 数据来源 |
|------|------|---------|
| **持仓管理** | 增删改查、CSV/Excel 批量导入、截图 OCR 识别导入 | 用户输入 + Claude Vision |
| **持仓分析** | 周收益、超额收益、Sharpe 比率、三维度收益归因 | AKShare + 天天基金实时净值 |
| **风险洞察** | 最大回撤 + 恢复天数、5 维健康度雷达、持仓相关性矩阵 | 近 60 个交易日净值历史 |
| **AI 对话** | 任务规划 + 并发取证 + Critic 校验 + 多轮对话；规划、工具调用、证据全程可视化 | Claude/DeepSeek + 实时市场数据 |
| **自动化建议** | 集中度预警、亏损提醒、高相关性分散建议、仓位优化 | 分析引擎输出 |
| **AI 周报** | LLM 生成结构化复盘（要点、下周关注、风险提示、AI 洞察） | AI + 分析数据 |
| **行情追踪** | 实时指数行情、财经新闻流 | 东方财富 + 新浪财经 |
| **量化验证** | 持仓穿透到个股、重仓股重叠、分批规则回测（对比一次性买入 / 定投基线） | 季报前十大重仓 + 历史净值 |
| **情景分析** | 5 个预设压力情景 + 自定义冲击 | 持仓快照 |
| **多资产** | 基金 / 股票 / ETF / 加密货币 | 新浪行情等 |
| **预警** | 回撤等预警落库、未读收件箱、webhook 推送 | 分析引擎输出 |
| **用户认证** | JWT 注册/登录、多租户数据隔离、对话历史持久化 | SQLite + bcrypt |

---

## 投研工作台

`make dev` 启动后打开 **http://localhost:5180**。这是日常使用的入口：桌面端布局，所有数字都来自后端实时计算，接口失败就显示失败，不会回退成示例数据。

| 分组 | 页面 | 做什么 | 背后的 Agent 能力 |
|---|---|---|---|
| 研究 | **AI 研究** | 提问；右侧实时显示任务规划、每次工具调用的证据、Critic 的通过 / 打回，点回答里的证据标签定位到工具返回 | Planner + 4 个 Agent + Critic |
| 组合 | 总览 | 市值、收益、持仓分布、收益归因（按标的 / 行业 / 类别）、要闻与指数 | 持仓 Agent |
| | 持仓 | 增删改、CSV / Excel 导入、截图识别 | — |
| | 持仓穿透 | 把基金拆到个股：真实暴露、被多只基金同时重仓的票、两只基金的重仓股重叠 | 量化 Agent |
| 风险 | 风险体检 | 回撤、5 维健康度、相关性矩阵、集中度、预警 | 风险 Agent |
| | 压力测试 | 预设情景下组合损益与逐持仓明细 | 情景分析 |
| | 调仓推演 | 调仓前先算：占比、集中度、回撤估计怎么变，是否越过风险画像 | 计算 / 校验工具 |
| 市场与量化 | 基金查询 | 任意基金的净值走势、阶段收益、经理与基准 | 市场 Agent |
| | 规则回测 | 分批建仓规则的历史表现，对比一次性买入与定投 | 量化 Agent |
| 报告与设置 | 周报 / 风险画像 | 按需生成复盘；设置 AI 给建议时必须遵守的约束 | — |

功能页通过 `POST /api/tools/{name}` 直接调用 Agent 的工具，所以页面上的数和 AI 回答里引用的证据出自同一份实现。每个功能页右上角都可以把当前话题一键交给 AI 解读。

工作台代码在 `workbench/`（React 19 + Vite + Tailwind 4），视觉遵循 Notion 的设计规范：白色画布、暖灰侧栏、细线边框、柔和色标签。未登录时使用本机匿名档（`user_id = 0`）的持仓，登录后切换到自己的账户。

仓库根目录的 `src/` 是早期的**移动端演示页**（`make demo`，:5173），无后端时用示例数据展示交互，也是 GitHub Pages 上的在线演示；它不是日常使用的入口。

---

## CLI 命令

WealthPilot 提供完整的命令行入口，无需启动 Web 服务也能使用：

```bash
cd backend

uv run python -m wealthpilot init     # 交互式初始化：选择 AI 提供商 + 输入 Key + 建库
uv run python -m wealthpilot config   # 查看当前配置（Key 脱敏显示）
uv run python -m wealthpilot run      # 启动 API 服务（等同 uvicorn）
uv run python -m wealthpilot chat     # 终端交互式 AI 对话（直接体验多 Agent）
uv run python -m wealthpilot ask "查询" # 非交互式查询（支持管道，stdout 可 pipe）
uv run python -m wealthpilot mcp      # 启动 MCP Server（stdio, for Claude Code）
```

`chat` 命令可以直接在终端体验完整流程 —— 规划、工具调用、校验结论实时显示：

```
你: 我的持仓集中度高吗，要不要调

🧭 规划 2 个并行任务（仓位评估）：
   • 💼 持仓分析 — 计算当前集中度
   • 🛡️ 风险评估 — 评估回撤与相关性

💼 持仓分析 开始：计算当前集中度
  🔧 compute_concentration...
   ✓ 完成（工具：compute_concentration）
...
🧩 整合各方证据…

最大单一持仓占比 70.69% [E-3f9a1c2b7d10] ...
```

任务失败会显示 `✗ failed`，Critic 打回会显示原因，研究未通过时结尾会标出状态。CLI 与 MCP 默认读取匿名档（`user_id=0`）的持仓；要分析某个登录用户的数据，设置 `LOCAL_USER_ID`。

### 非交互模式 (ask)

`ask` 子命令支持单次查询和管道输入，完整多 Agent 流程一行获取结果：

```bash
# 直接查询
python -m wealthpilot ask "半导体ETF最新净值"

# 从 stdin 读取（支持管道）
echo "我的持仓风险分析" | python -m wealthpilot ask -

# stdout 干净输出，适合重定向（Agent 路由信息走 stderr）
python -m wealthpilot ask "投资建议" > advice.txt

# 静默模式（抑制 stderr）
python -m wealthpilot ask "市场分析" 2>/dev/null
```

---

## MCP Server — Claude Code / Cursor 集成

WealthPilot 提供标准 **MCP (Model Context Protocol) Server**，将 19 个投资分析工具直接暴露给 Claude Code、Cursor 等 MCP 客户端。Claude 可以自主调用这些工具获取实时行情和持仓分析——**无需自建 Agent，无需 API Key**（MCP Server 本身不调用 LLM）。

### 配置方法

在项目根目录创建 `.mcp.json`（或在 Claude Code 设置中添加）：

```json
{
  "mcpServers": {
    "wealthpilot": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/wealthpilot/backend", "python", "-m", "wealthpilot", "mcp"]
    }
  }
}
```

配置后重启 Claude Code，即可在对话中使用 WealthPilot 的全部工具：

```
> 查一下 007340 的最新净值和近 30 天走势

Claude 会自动调用:
  → get_fund_info("007340")
  → get_nav_history("007340", 30)
然后基于返回数据生成分析回答
```

### 可用工具一览

| 工具 | 参数 | 说明 |
|------|------|------|
| `get_fund_info` | fund_code | 基金基本信息（名称、净值、类型） |
| `get_nav_history` | fund_code, days? | 净值走势（默认 30 个交易日） |
| `search_market_news` | keyword? | 最新财经要闻 |
| `get_portfolio_overview` | — | 持仓总览：市值、收益、Sharpe |
| `get_attribution` | — | 按基金收益归因 |
| `get_health_score` | — | 5 维健康度评分 |
| `get_investment_suggestions` | — | 规则引擎调仓建议 |
| `calculate_return` | fund_code, days | 近 N 个交易日累计收益率（5≈1 周，21≈1 月） |
| `compare_funds` | fund_codes[] | 多基金横向对比 |
| `get_drawdown_analysis` | — | 全持仓回撤分析 |
| `get_max_drawdown` | fund_code | 单基金最大回撤 |
| `get_correlation_matrix` | — | 持仓相关性矩阵 |
| `compute_concentration` | — | 各持仓权重、最大单一权重、HHI、有效持仓数 |
| `simulate_portfolio_change` | changes[] | 推演仓位变动前后的权重、集中度、回撤估计 |
| `check_profile_constraint` | changes? | 按风险画像校验当前持仓或拟议变动 |
| `compute_position_sizing` | fund_code | 不突破回撤容忍度的仓位上限 |
| `lookthrough_portfolio` | — | 穿透到个股的真实暴露（季报前十大，带 report_date） |
| `compute_stock_overlap` | fund_code_a, fund_code_b | 两只基金的重仓股重叠 |
| `backtest_rule` | fund_code, triggers[], stop_loss_pct?, days? | 分批建仓规则回测，对比两个基线 |

---

## Makefile 速查

```bash
make setup     # 首次配置：安装依赖 + 复制 .env
make dev       # 启动后端 + 工作台（http://localhost:5180）
make backend   # 仅启动后端
make workbench # 仅启动工作台
make demo      # 启动移动端演示页（:5173）
make test      # 运行测试
make config    # 查看当前配置
make chat      # 终端 AI 对话
make mcp       # 启动 MCP Server (stdio)
make ask Q="查净值"  # 非交互式 AI 查询
make docker    # Docker Compose 启动
make clean     # 清理生成文件
```

---

## API Reference

<details>
<summary>完整 API 列表（39 个端点，点击展开）</summary>

### Auth（3）

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录，获取 JWT Token |
| GET | `/api/auth/me` | 获取当前用户信息 |

### Portfolio（6）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portfolio` | 查询持仓列表（含实时净值） |
| POST | `/api/portfolio` | 新增持仓 |
| PUT | `/api/portfolio/{id}` | 更新持仓 |
| DELETE | `/api/portfolio/{id}` | 删除持仓 |
| POST | `/api/portfolio/import/csv` | CSV/Excel 批量导入 |
| POST | `/api/portfolio/import/ocr` | 截图 OCR 导入 (Claude Vision) |

### Market Data（8）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/indices` | 实时指数行情 |
| GET | `/api/market/news` | 财经新闻流 |
| GET | `/api/market/fund/{code}` | 基金信息（净值 + 经理 + 排名） |
| GET | `/api/market/fund/{code}/nav` | 历史净值（N 日） |
| GET | `/api/market/fund/{code}/rank` | 基金排名数据 |
| GET | `/api/market/macro` | 宏观指标（PMI/CPI） |
| GET | `/api/market/stock/{code}` | 股票 / ETF 行情 |
| GET | `/api/market/crypto/{symbol}` | 加密货币行情 |

### Analysis（6）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analysis/overview` | 持仓总览 + Sharpe 比率 |
| GET | `/api/analysis/attribution?by=fund` | 收益归因分析 |
| GET | `/api/analysis/drawdown` | 回撤分析 + 恢复天数 |
| GET | `/api/analysis/health` | 5 维健康度雷达 |
| GET | `/api/analysis/correlation` | 持仓相关性矩阵 |
| GET | `/api/analysis/suggestions` | 数据驱动的调仓建议 |

### Investor Profile（3）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/profile` | 获取风险画像（未测评返回 null） |
| PUT | `/api/profile` | 提交/更新风险测评结果 |
| GET | `/api/profile/labels` | 风险等级字典 |

### AI Chat & Reports（5）

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI 多智能体对话（SSE） |
| GET | `/api/chat/history/{id}` | 获取对话历史（含证据与校验状态） |
| GET | `/api/report/weekly` | 获取/生成 AI 周报 |
| POST | `/api/report/generate` | 强制重新生成周报 |
| GET | `/api/report/pdf` | 导出 PDF 报告 |

### Scenario（3）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scenario/presets` | 预设压力情景列表 |
| GET | `/api/scenario` | 自定义冲击下的组合影响 |
| GET | `/api/scenario/{key}` | 运行某个预设情景 |

### Alerts（4）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/alerts` | 计算当前预警 |
| GET | `/api/alerts/inbox` | 未读预警收件箱 |
| POST | `/api/alerts/read` | 标记已读 |
| POST | `/api/alerts/push` | 触发 webhook 推送 |

### Tools（2）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tools` | 19 个 Agent 工具及入参说明，按 Agent 分组 |
| POST | `/api/tools/{name}` | 直接执行一个工具，返回 `{ok, data, as_of}`；工作台功能页走这里 |

`/api/chat` 的 SSE 事件类型：`plan`、`task_start`、`tool_call`、`evidence`、`task_done`、`critic`、`replan`、`synthesizing`、`delta`、`grounding_warning`、`error`、`done`（`done.meta.status` 为 `passed` / `partial` / `insufficient_data` / `rejected` / `failed`）。

</details>

---

## Project Structure

```
wealthpilot/
├── Makefile                     # 一键命令入口
├── docker-compose.yml           # Docker 部署
├── showcase.html                # 项目展示页
│
├── workbench/                   # ⭐ 投研工作台（桌面端，日常使用入口）
│   └── src/
│       ├── api/                 #   接口层（失败即报错，无示例数据兜底）+ 研究会话状态
│       ├── components/          #   Notion 风格组件（kit）、页面积木（ui）、外壳与导航
│       └── pages/               #   11 个功能页：研究 / 总览 / 持仓 / 穿透 / 风险 / 压测 / 调仓 / 基金 / 回测 / 周报 / 画像
│
├── docs/stock-roadmap.md        # 股票能力规划
│
├── src/                         # 移动端演示页（React，GitHub Pages 在线演示）
│   ├── pages/                   #   11 个页面组件
│   └── data/mock.ts             #   无后端时的示例数据
│
└── backend/                     # Backend (Python)
    ├── .env.example             #   环境配置模板
    └── src/wealthpilot/
        ├── __main__.py          #   CLI 入口 (run/init/config/chat/mcp/ask)
        ├── mcp_server.py        #   ⭐ MCP Server（19 工具，for Claude Code）
        ├── main.py              #   FastAPI 应用
        ├── settings.py          #   配置管理（支持双 Provider）
        ├── routes/              #   11 个路由模块，39 个端点（含 tools：工具直调）
        ├── models/              #   数据模型（SQLModel）
        ├── services/
        │   ├── ai_client.py     #   ⭐ Provider 抽象层（Anthropic / DeepSeek 自动适配）
        │   ├── agents/          #   ⭐ 多智能体系统
        │   │   ├── base.py      #     BaseAgent — 异步 tool-use 循环 + 并发工具
        │   │   ├── planner_agent.py # ⭐ Planner — 任务 DAG 拆解 + 关键词兜底
        │   │   ├── critic_agent.py  # ⭐ Critic — 证据充分性 + 输出合规性双闸门
        │   │   ├── synthesizer_agent.py # ⭐ Synthesizer + 数值溯源检查
        │   │   ├── streaming.py #     同步 SDK → 异步事件流桥接
        │   │   ├── market_agent.py #  市场 Agent（3 工具）
        │   │   ├── portfolio_agent.py # 持仓 Agent（4 + 4 计算工具）
        │   │   ├── risk_agent.py   #  风险 Agent（5 + 4 计算工具）
        │   │   ├── quant_agent.py  #  量化 Agent（穿透 / 回测 3 + 4 计算工具）
        │   │   ├── orchestrator.py #  编排器 — Plan → Execute → Critic → Synthesize
        │   │   ├── tools.py     #     19 个工具定义 + 统一执行器
        │   │   └── prompts.py   #     Agent 专属 system prompt
        │   ├── context.py       #   Web / CLI / MCP 共用的持仓与行情上下文加载
        │   ├── evidence.py      #   证据记录、工具缓存与调用预算
        │   ├── analysis.py      #   分析引擎（Sharpe、回撤、健康度、相关性）
        │   ├── simulation.py    #   仓位推演与画像约束校验
        │   ├── lookthrough.py   #   持仓穿透
        │   ├── backtest.py      #   规则回测
        │   ├── scenario.py      #   情景分析
        │   ├── alerting.py      #   预警
        │   ├── market_data.py   #   多源行情数据服务
        │   └── report.py / pdf_report.py  # AI 周报与 PDF 导出
        └── storage/             #   SQLite 数据库
```

---

## Deployment

### 本地开发

```bash
make setup && make dev
```

### Docker Compose（自部署）

```bash
cp backend/.env.example backend/.env
# 编辑 .env 填入 API Key
docker compose up --build -d
```

### Railway（后端）+ GitHub Pages（前端）

1. Fork 仓库 → Railway 连接，Root Directory = `backend`，设置 `ANTHROPIC_API_KEY` + `JWT_SECRET`
2. 前端构建：`VITE_API_URL=https://your-backend.railway.app npm run build`

---

## Roadmap

- [x] Full-stack Agent 架构（FastAPI + React）
- [x] 免费实时行情（AKShare + 东方财富 + 天天基金）
- [x] 多智能体系统（Planner + Market/Portfolio/Risk/Quant，19 工具）
- [x] Provider 抽象层（Claude + DeepSeek 一键切换）
- [x] 持仓管理（CRUD + CSV 导入 + OCR）
- [x] 高级量化分析（Sharpe、最大回撤、相关性矩阵）
- [x] 用户认证（JWT + 多租户隔离）
- [x] 对话历史持久化
- [x] CLI 工具（init/config/chat/run）
- [x] MCP Server（19 工具，Claude Code / Cursor 直接调用）
- [x] CLI 非交互模式（ask 子命令，支持管道）
- [x] Docker Compose 部署
- [x] AI 周报生成
- [x] Demo 体验优化（SVG 图标系统、演示模式模拟多 Agent 流程、页面转场动画、动态雷达图）
- [x] Planner/Synthesizer 架构（任务 DAG + 并行执行 + 冲突消解）
- [x] 投资者画像（风险测评落库，注入 Planner/Agent/Synthesizer 作为硬约束）
- [x] 数值溯源检查（答案中的数字必须来自工具返回）
- [x] 持仓穿透（重仓股重叠度 + 真实行业暴露）
- [x] 计算工具化（compute_* / check_*，杜绝 LLM 算术）
- [x] Critic 双闸门（证据充分性 + 输出合规性，不通过则补任务或重写）
- [x] 回测引擎（分批规则历史验证，含一次性买入 / 定投两个基线）
- [x] 情景分析（5 个预设压力情景 + 自定义冲击，个股/行业/类别/全市场四级粒度）
- [x] 多资产类别（基金 / 股票 / ETF / 加密货币，按类型分组批量取价）
- [x] 推送通知（预警落库 + 冷却期去重 + 未读收件箱 + webhook 推送）
- [x] 报告导出 PDF（reportlab 内置 CID 中文字体，不依赖宿主机字体）
- [x] 投研工作台（桌面端，11 个功能页，Agent 的每项能力都有对应页面）
- [x] 工具直调接口（功能页与 Agent 共用同一批工具）
- [ ] **股票能力**（历史行情 → 个股工具与 StockAgent → 并入穿透与回测 → 个股页面），见 [docs/stock-roadmap.md](docs/stock-roadmap.md)
- [ ] 回答质量评估（黄金题集 + 新旧架构 A/B，需配 API Key）
- [ ] 结构化记忆层（用户偏好与被否决建议）
- [ ] PostgreSQL + Alembic 正式迁移

## 致谢

- 工作台的工程脚手架与外壳结构起步于 [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 的 Web 端（MIT），许可见 `workbench/THIRD_PARTY_LICENSE.dsa-web`
- 视觉规范参考 [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 中的 Notion 设计分析

## License

[MIT](LICENSE)
