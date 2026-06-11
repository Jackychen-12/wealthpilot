<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI 多智能体智能投顾系统</strong><br/>
  <sub>Multi-Agent Architecture · Claude & DeepSeek · 12 Real-time Tools · One-command Deploy</sub>
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

大多数投资分析工具只是简单地调用一次 LLM 生成文本。WealthPilot 不同——它是一个**完整的多智能体系统**，由 Router 将用户意图智能分流到 3 个专业 Agent，每个 Agent 配备实时数据工具，能自主决策调用哪些工具、如何组合分析结果，最终以流式对话的方式交付深度投资洞察。

### 核心优势

| | 优势 | 说明 |
|--|------|------|
| 🤖 | **多智能体架构** | Router Agent 意图分类 → 市场/持仓/风险 3 个专业 Agent，各自配备专属工具集，非简单 prompt 拼接 |
| 🔧 | **12 个实时工具** | Agent 自主决策调用：基金查询、净值走势、财经新闻、收益归因、回撤分析、相关性矩阵... |
| 🌐 | **双模型支持** | Claude & DeepSeek 一行配置切换，Provider 抽象层自动适配 Anthropic SDK / OpenAI SDK |
| 📊 | **免费实时数据** | AKShare + 东方财富 + 天天基金 + 新浪财经，无需付费数据源 |
| ⚡ | **真流式输出** | SSE token-by-token 流式传输，工具调用过程实时可见 |
| 🔌 | **MCP Server** | 12 个工具通过 MCP 协议暴露，Claude Code / Cursor 直接调用，无需自建 Agent |
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
make dev            # 启动后端(:8000) + 前端(:5173)
```

打开 http://localhost:5173/wealthpilot/ 即可使用。

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

配置完成后运行 `make config` 验证：

```
┌─ WealthPilot 配置 ─────────────────────┐
│ AI 提供商:      ANTHROPIC              │
│ AI 模型:        claude-sonnet-4-6      │
│ API Key:        sk-ant-api...xxxx      │
│ 工具调用轮次:   3                       │
│ 数据库:         ./data/wealthpilot.db  │
└─────────────────────────────────────────┘
```

### 不配置 API Key 也能用

| 功能 | 无 API Key | 有 API Key |
|------|:----------:|:----------:|
| 持仓管理（增删改查 + CSV 导入） | ✅ | ✅ |
| 实时行情（指数、新闻、净值） | ✅ | ✅ |
| 量化分析（Sharpe、回撤、健康度） | ✅ | ✅ |
| AI 多智能体对话 | 演示模式（模拟 Agent 路由 + 工具调用 + 流式输出） | **多 Agent 实时分析** |
| 截图 OCR 导入 | ❌ | ✅ (Claude Vision) |
| AI 周报 | 模板回退 | **LLM 智能生成** |

---

## Architecture

### 多智能体系统

WealthPilot 的 AI 核心是一个 **4 Agent 协作系统**，不是简单的单次 LLM 调用：

```
用户消息
   │
   ▼
┌──────────────────┐
│   Router Agent   │  意图分类（LLM + 关键词兜底）
│   "这是什么类型   │  → 输出：agent_name + reason
│    的问题？"      │
└──────┬───────────┘
       │
       ├─── market ──→ 📊 MarketAgent（3 工具）
       │                  get_fund_info     — 基金基本信息
       │                  get_nav_history   — 净值走势
       │                  search_news       — 财经新闻
       │
       ├─── portfolio → 💼 PortfolioAgent（4 工具）
       │                  get_overview       — 持仓总览
       │                  get_attribution    — 收益归因
       │                  get_health         — 健康度评分
       │                  get_suggestions    — 调仓建议
       │
       └─── risk ────→ 🛡️ RiskAgent（5 工具）
                          get_drawdown       — 回撤分析
                          get_correlation    — 相关性矩阵
                          calculate_return   — 区间收益率
                          compare_funds      — 基金对比
                          get_max_drawdown   — 最大回撤
```

**关键设计**：每个专业 Agent 继承自 `BaseAgent`，共享 tool-use 循环——Agent 自主决定调用哪些工具、调用几次，直到它认为信息充分后才生成最终回答。这是真正的 Agent 行为，不是预编排的 pipeline。

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
│                Backend (FastAPI · 24 endpoints)                │
│                                                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────────┐  ┌────────┐│
│  │ Portfolio  │  │  Market   │  │  Multi-Agent  │  │Analysis││
│  │ CRUD +    │  │  Data     │  │   System      │  │Engine  ││
│  │ CSV/OCR   │  │  Service  │  │               │  │Sharpe/ ││
│  │ Import    │  │           │  │ ┌───────────┐ │  │DD/Corr/││
│  └───────────┘  └───────────┘  │ │  Router   │ │  │Health  ││
│                                │ └─┬───┬───┬─┘ │  └────────┘│
│                                │   │   │   │   │            │
│                                │   ▼   ▼   ▼   │            │
│                                │  Mkt Port Risk│            │
│                                │  3T   4T   5T │            │
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
| AI | Claude API (Anthropic SDK) + DeepSeek (OpenAI SDK)，多 Agent 协作 |
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
  ├──→ Chat（多智能体 AI 对话 · Router → 3 专业 Agent · SSE 流式）
  ├──→ Login（JWT 注册/登录）
  └──→ Risk Profile（风险偏好问卷评估）
```

### 功能矩阵

| 模块 | 功能 | 数据来源 |
|------|------|---------|
| **持仓管理** | 增删改查、CSV/Excel 批量导入、截图 OCR 识别导入 | 用户输入 + Claude Vision |
| **持仓分析** | 周收益、超额收益、Sharpe 比率、三维度收益归因 | AKShare + 天天基金实时净值 |
| **风险洞察** | 最大回撤 + 恢复天数、5 维健康度雷达、持仓相关性矩阵 | 60 日净值历史计算 |
| **AI 对话** | 多 Agent 路由 + 多轮对话 + SSE 流式 + 工具调用可视化；演示模式完整模拟 Agent 流程 | Claude/DeepSeek + 实时市场数据 |
| **自动化建议** | 集中度预警、亏损提醒、高相关性分散建议、仓位优化 | 分析引擎输出 |
| **AI 周报** | LLM 生成结构化复盘（要点、下周关注、风险提示、AI 洞察） | AI + 分析数据 |
| **行情追踪** | 实时指数行情、财经新闻流 | 东方财富 + 新浪财经 |
| **用户认证** | JWT 注册/登录、多租户数据隔离、对话历史持久化 | SQLite + bcrypt |

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

`chat` 命令可以直接在终端体验完整的多智能体系统——Router 自动分流、工具调用过程实时显示：

```
╔═══════════════════════════════════════╗
║  WealthPilot AI 终端对话 (ANTHROPIC)   ║
║  输入 quit 退出 · 输入 clear 清空历史   ║
╚═══════════════════════════════════════╝

你: 查一下半导体ETF最新净值

📊 市场分析 — 用户询问基金净值信息
  🔧 get_fund_info...
  🔧 get_nav_history...

国泰半导体芯片ETF联接 (007151) 最新净值 1.5983，
近5日走势：1.5821 → 1.5903 → 1.5847 → 1.5962 → 1.5983...
```

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

WealthPilot 提供标准 **MCP (Model Context Protocol) Server**，将 12 个投资分析工具直接暴露给 Claude Code、Cursor 等 MCP 客户端。Claude 可以自主调用这些工具获取实时行情和持仓分析——**无需自建 Agent，无需 API Key**（MCP Server 本身不调用 LLM）。

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
| `get_nav_history` | fund_code, days? | 净值走势（默认 30 天） |
| `search_market_news` | keyword? | 最新财经要闻 |
| `get_portfolio_overview` | — | 持仓总览：市值、收益、Sharpe |
| `get_attribution` | — | 按基金收益归因 |
| `get_health_score` | — | 5 维健康度评分 |
| `get_investment_suggestions` | — | 规则引擎调仓建议 |
| `calculate_return` | fund_code, days | 区间累计收益率 |
| `compare_funds` | fund_codes[] | 多基金横向对比 |
| `get_drawdown_analysis` | — | 全持仓回撤分析 |
| `get_max_drawdown` | fund_code | 单基金最大回撤 |
| `get_correlation_matrix` | — | 持仓相关性矩阵 |

---

## Makefile 速查

```bash
make setup     # 首次配置：安装依赖 + 复制 .env
make dev       # 启动后端 + 前端（开发模式）
make backend   # 仅启动后端
make frontend  # 仅启动前端
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
<summary>完整 API 列表（24 个端点，点击展开）</summary>

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

### Market Data（6）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/indices` | 实时指数行情 |
| GET | `/api/market/news` | 财经新闻流 |
| GET | `/api/market/fund/{code}` | 基金信息（净值 + 经理 + 排名） |
| GET | `/api/market/fund/{code}/nav` | 历史净值（N 日） |
| GET | `/api/market/fund/{code}/rank` | 基金排名数据 |
| GET | `/api/market/macro` | 宏观指标（PMI/CPI） |

### Analysis（6）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analysis/overview` | 持仓总览 + Sharpe 比率 |
| GET | `/api/analysis/attribution?by=fund` | 收益归因分析 |
| GET | `/api/analysis/drawdown` | 回撤分析 + 恢复天数 |
| GET | `/api/analysis/health` | 5 维健康度雷达 |
| GET | `/api/analysis/correlation` | 持仓相关性矩阵 |
| GET | `/api/analysis/suggestions` | 数据驱动的调仓建议 |

### AI Chat & Reports（3）

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI 多智能体对话（SSE 流式） |
| GET | `/api/chat/history/{id}` | 获取对话历史 |
| GET | `/api/report/weekly` | 获取/生成 AI 周报 |

</details>

---

## Project Structure

```
wealthpilot/
├── Makefile                     # 一键命令入口
├── docker-compose.yml           # Docker 部署
├── showcase.html                # 项目展示页
│
├── src/                         # Frontend (React)
│   ├── api/                     #   API 层（client, portfolio, market, analysis, chat）
│   ├── pages/                   #   11 个页面组件
│   ├── components/              #   18 个共享 UI 组件（SVG 图标系统）
│   └── data/mock.ts             #   Mock 降级数据（含 Agent/工具元数据）
│
└── backend/                     # Backend (Python)
    ├── .env.example             #   环境配置模板
    └── src/wealthpilot/
        ├── __main__.py          #   CLI 入口 (run/init/config/chat/mcp/ask)
        ├── mcp_server.py        #   ⭐ MCP Server（12 工具，for Claude Code）
        ├── main.py              #   FastAPI 应用
        ├── settings.py          #   配置管理（支持双 Provider）
        ├── routes/              #   7 个路由模块，24 个端点
        ├── models/              #   数据模型（SQLModel）
        ├── services/
        │   ├── ai_client.py     #   ⭐ Provider 抽象层（Anthropic / DeepSeek 自动适配）
        │   ├── agents/          #   ⭐ 多智能体系统
        │   │   ├── base.py      #     BaseAgent — 共享 tool-use 循环
        │   │   ├── router_agent.py #  Router — 意图分类 + 关键词兜底
        │   │   ├── market_agent.py #  市场 Agent（3 工具）
        │   │   ├── portfolio_agent.py # 持仓 Agent（4 工具）
        │   │   ├── risk_agent.py   #  风险 Agent（5 工具）
        │   │   ├── orchestrator.py #  编排器 — Router → Agent 协调
        │   │   ├── tools.py     #     12 个工具定义 + 统一执行器
        │   │   └── prompts.py   #     Agent 专属 system prompt
        │   ├── analysis.py      #   分析引擎（Sharpe、回撤、健康度、相关性）
        │   ├── market_data.py   #   多源行情数据服务
        │   └── report.py        #   AI 周报生成
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
- [x] 多智能体系统（Router + Market/Portfolio/Risk，12 工具）
- [x] Provider 抽象层（Claude + DeepSeek 一键切换）
- [x] 持仓管理（CRUD + CSV 导入 + OCR）
- [x] 高级量化分析（Sharpe、最大回撤、相关性矩阵）
- [x] 用户认证（JWT + 多租户隔离）
- [x] 对话历史持久化
- [x] CLI 工具（init/config/chat/run）
- [x] MCP Server（12 工具，Claude Code / Cursor 直接调用）
- [x] CLI 非交互模式（ask 子命令，支持管道）
- [x] Docker Compose 部署
- [x] AI 周报生成
- [x] Demo 体验优化（SVG 图标系统、演示模式模拟多 Agent 流程、页面转场动画、动态雷达图）
- [ ] 推送通知（回撤预警）
- [ ] 回测与情景分析
- [ ] 多资产类别（股票、债券、ETF、加密货币）
- [ ] 报告导出 PDF

## License

[MIT](LICENSE)
