<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI-Powered Investment Advisory Agent</strong><br/>
  <strong>智能投顾 Agent — 基于 Claude AI 的持仓分析、风险洞察与投资决策辅助</strong>
</p>

<p align="center">
  <a href="https://jackychen-12.github.io/wealthpilot/">Live Demo</a> &nbsp;|&nbsp;
  <a href="https://jackychen-12.github.io/wealthpilot/showcase.html">Showcase</a> &nbsp;|&nbsp;
  <a href="#architecture--架构">Architecture</a> &nbsp;|&nbsp;
  <a href="#api-reference">API Reference</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" alt="React 18" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude_AI-Agent-7C3AED?logo=anthropic&logoColor=white" alt="Claude AI" />
  <img src="https://img.shields.io/badge/AKShare-Free_Data-FF6B35" alt="AKShare" />
  <img src="https://github.com/Jackychen-12/wealthpilot/actions/workflows/deploy.yml/badge.svg" alt="Deploy" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

---

<details open>
<summary><b>English</b></summary>

## What is WealthPilot?

WealthPilot is a **full-stack AI investment advisory agent** that combines real-time market data, portfolio analysis, and Claude AI-powered conversational insights. Users can manage their fund portfolio, get automated risk analysis, and have intelligent multi-turn conversations about their investments.

### Key Highlights

- **Real AI Agent** — Multi-agent architecture: Router Agent + 3 specialist agents (Market, Portfolio, Risk) with 12 tool-use capabilities, powered by Claude
- **Real Market Data** — Free data from AKShare + 东方财富 + 天天基金 + 新浪财经 (no paid API keys needed for market data)
- **Full Backend** — FastAPI with 24 REST endpoints, SQLite storage, JWT auth
- **Multi-tenant** — User registration/login, each user has isolated portfolio and chat history
- **Multiple Import Methods** — Manual input, CSV/Excel bulk import, screenshot OCR (via Claude Vision)
- **One-click Deploy** — Docker Compose for self-hosting, Railway-ready

## Features

| Module | Description | Data Source |
|--------|-------------|-------------|
| **Portfolio Management** | Add/edit/delete fund holdings; CSV/Excel bulk import; screenshot OCR import | User input + Claude Vision |
| **Smart Portfolio Analysis** | Weekly return, excess return, Sharpe ratio, return attribution (by fund/industry/asset type) | AKShare + 天天基金 real-time NAV |
| **Risk Insight Engine** | Max drawdown + recovery days, portfolio health radar (5 dimensions), correlation matrix | Calculated from 60-day NAV history |
| **AI Conversational Q&A** | Multi-agent routing + multi-turn dialogue with SSE streaming; Router auto-dispatches to Market / Portfolio / Risk agents | Claude API + real-time market data |
| **Automated Suggestions** | Rule-engine + data-driven: concentration risk, loss alerts, correlation warnings | Analysis engine output |
| **Weekly Report** | LLM-generated structured review (summary, key points, focus, AI insight) | Claude API + analysis data |
| **Market Tracking** | Real-time index quotes, financial news feed | 东方财富 + 新浪财经 |
| **User Auth** | JWT-based registration/login, multi-tenant data isolation | SQLite + bcrypt |

### Screens

```
Home ─────→ Portfolio (manage holdings)
  │              ├── Import CSV/Excel
  │              └── Import via Screenshot OCR
  │
  ├──→ Overview ──→ Attribution (by fund / industry / asset)
  │         ├──→ Drawdown (max drawdown + recovery analysis)
  │         ├──→ Health (5-dimension radar + scores)
  │         ├──→ Suggestions (AI recommendations)
  │         └──→ Weekly Report (LLM-generated)
  │
  └──→ Chat (Multi-Agent: Router → Market / Portfolio / Risk agents + SSE streaming)
```

## Getting Started

### Quick Start (3 commands)

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git
cd wealthpilot

# Backend
cd backend
cp .env.example .env
uv sync && uv run uvicorn wealthpilot.main:app --reload --port 8000

# Frontend (new terminal)
cd .. && npm install && npm run dev
# Visit http://localhost:5173/wealthpilot/
```

### With Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build
# Frontend: http://localhost:5173  |  Backend: http://localhost:8000/docs
```

### What works without API keys?

| Feature | Without key | With ANTHROPIC_API_KEY |
|---------|:-----------:|:---------------------:|
| Portfolio CRUD | ✅ | ✅ |
| Market data (indices, news, NAV) | ✅ | ✅ |
| Analysis (Sharpe, drawdown, health) | ✅ | ✅ |
| AI Chat | Mock responses | Real Claude Agent with tools |
| OCR Import | ❌ | ✅ |
| Weekly Report (LLM) | Fallback template | Full AI-generated |

## Deployment

### Docker Compose (self-host)

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git && cd wealthpilot
cp backend/.env.example backend/.env
docker compose up --build -d
```

### Railway (backend) + GitHub Pages (frontend)

1. Fork → Railway → connect repo, root = `backend`, add `ANTHROPIC_API_KEY` + `JWT_SECRET`
2. Frontend: `VITE_API_URL=https://your-backend.railway.app npm run build`

</details>

---

<details>
<summary><b>中文</b></summary>

## 这是什么？

WealthPilot 是一个**全栈 AI 智能投顾 Agent**，结合实时行情数据、持仓分析和 Claude AI 对话式洞察。用户可以管理基金持仓、获取自动化风险分析，并与 AI 进行多轮投资对话。

### 核心亮点

- **真实 AI Agent** — 多智能体架构：路由 Agent + 3 个专业 Agent（市场、持仓、风险），12 个 tool_use 工具，基于 Claude 驱动
- **真实行情数据** — AKShare + 东方财富 + 天天基金 + 新浪财经，市场数据无需付费 API Key
- **完整后端** — FastAPI 24 个 REST 端点，SQLite 存储，JWT 认证
- **多租户** — 注册/登录，每个用户数据隔离
- **多种导入方式** — 手动录入、CSV/Excel 批量导入、截图 OCR（Claude Vision）
- **一键部署** — Docker Compose 自托管，Railway 就绪

## 功能一览

| 模块 | 说明 | 数据来源 |
|------|------|----------|
| **持仓管理** | 添加/编辑/删除基金持仓；CSV/Excel 批量导入；截图 OCR 识别 | 用户输入 + Claude Vision |
| **智能持仓分析** | 周收益、超额收益、Sharpe 比率、收益归因（按基金/行业/资产类型） | AKShare + 天天基金实时净值 |
| **风险洞察引擎** | 最大回撤 + 恢复天数、组合健康度雷达（5 维）、相关性矩阵 | 基于 60 日净值历史计算 |
| **AI 对话问答** | 多智能体路由 + 多轮对话 + SSE 流式输出，Router 自动分发至市场 / 持仓 / 风险专业 Agent | Claude API + 实时行情 |
| **自动化建议** | 规则引擎 + 数据驱动：集中度风险、亏损预警、相关性警告 | 分析引擎输出 |
| **周报** | LLM 生成结构化复盘（摘要、要点、关注、AI 洞察） | Claude API + 分析数据 |
| **市场追踪** | 实时指数行情（上证/深证/创业板）、财经新闻 | 东方财富 + 新浪财经 |
| **用户认证** | JWT 注册/登录，多租户数据隔离 | SQLite + bcrypt |

### 页面流

```
首页 ─────→ 持仓管理
  │              ├── CSV/Excel 导入
  │              └── 截图 OCR 导入
  │
  ├──→ 总览 ──→ 收益归因（按基金/行业/资产）
  │        ├──→ 回撤分析（最大回撤 + 恢复天数）
  │        ├──→ 健康度（5 维雷达 + 评分）
  │        ├──→ 建议（AI 个性化推荐）
  │        └──→ 周报（LLM 生成）
  │
  └──→ 对话（多智能体：Router → 市场 / 持仓 / 风险 Agent + SSE 流式）
```

## 快速开始

### 3 条命令启动

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git
cd wealthpilot

# 后端
cd backend
cp .env.example .env
uv sync && uv run uvicorn wealthpilot.main:app --reload --port 8000

# 前端（新终端）
cd .. && npm install && npm run dev
# 访问 http://localhost:5173/wealthpilot/
```

### Docker 启动

```bash
cp backend/.env.example backend/.env
docker compose up --build
# 前端: http://localhost:5173  |  后端: http://localhost:8000/docs
```

### 没有 API Key 也能用什么？

| 功能 | 无 Key | 有 ANTHROPIC_API_KEY |
|------|:------:|:--------------------:|
| 持仓增删改 | ✅ | ✅ |
| 行情数据（指数、新闻、净值） | ✅ | ✅ |
| 分析（Sharpe、回撤、健康度） | ✅ | ✅ |
| AI 对话 | Mock 回复 | 真实 Claude Agent + 工具 |
| OCR 导入 | ❌ | ✅ |
| 周报（LLM） | 模板兜底 | AI 生成完整报告 |

## 部署

### Docker Compose（自托管）

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git && cd wealthpilot
cp backend/.env.example backend/.env
docker compose up --build -d
```

### Railway（后端）+ GitHub Pages（前端）

1. Fork → Railway → 连接仓库，根目录 = `backend`，添加 `ANTHROPIC_API_KEY` + `JWT_SECRET`
2. 前端：`VITE_API_URL=https://your-backend.railway.app npm run build`

</details>

---

## Architecture / 架构

```
┌─────────────────────────────────────────────────────────────┐
│              Frontend (Vite + React + TypeScript)             │
│   9 pages · API layer with mock fallback · SSE streaming     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE
┌───────────────────────────┴─────────────────────────────────┐
│              Backend (FastAPI · 24 endpoints)                 │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐  │
│  │ Portfolio │ │  Market  │ │ Multi-Agent  │ │  Analysis  │  │
│  │ CRUD+    │ │  Data    │ │   System     │ │  Engine    │  │
│  │ Import   │ │  Service │ │              │ │ Sharpe/DD/ │  │
│  │ CSV/OCR  │ │          │ │  ┌────────┐  │ │ Health/    │  │
│  └──────────┘ └──────────┘ │  │ Router │  │ │ Corr/Sugg  │  │
│                            │  └──┬─┬─┬─┘  │ └───────────┘  │
│                            │     │ │ │     │       │         │
│                            │  ┌──┘ │ └──┐  │       │         │
│                            │  ▼    ▼    ▼  │       │         │
│                            │ Mkt Port Risk │       │         │
│                            │ 3T   4T   5T  │───────┘         │
│                            └──────────────┘                  │
│       │             │             │              │           │
│       └─────────────┼─────────────┼──────────────┘           │
│                     │             │                          │
│              ┌──────┴──────┐  ┌───┴────┐                    │
│              │   SQLite    │  │  JWT   │                    │
│              │ (Portfolio  │  │  Auth  │                    │
│              │  + Chat +   │  │        │                    │
│              │  Users)     │  └────────┘                    │
│              └─────────────┘                                │
└──────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    Claude API         AKShare            东方财富/新浪
    (Multi-Agent     (Fund NAV +         (Index quotes
     + OCR +          Rankings +          + News)
     Report)          Macro data)
```

| Layer | Technology |
|-------|-----------|
| Frontend | Vite 6, React 18, TypeScript 5.6 |
| Backend | Python 3.11+, FastAPI, SQLModel, Uvicorn |
| AI | Claude API (Anthropic SDK) — multi-agent (Router + Market/Portfolio/Risk), vision, report |
| Data | AKShare (free), 东方财富 API, 天天基金 API, 新浪财经 API |
| Auth | JWT (PyJWT) + bcrypt |
| Storage | SQLite (dev) — swappable for PostgreSQL |
| Deploy | Docker Compose, Railway, GitHub Pages |

## API Reference

<details>
<summary>Full API table (click to expand)</summary>

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login, get JWT token |
| GET | `/api/auth/me` | Get current user info |

### Portfolio

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portfolio` | List holdings (with real-time NAV) |
| POST | `/api/portfolio` | Add a holding |
| PUT | `/api/portfolio/{id}` | Update a holding |
| DELETE | `/api/portfolio/{id}` | Delete a holding |
| POST | `/api/portfolio/import/csv` | Bulk import from CSV/Excel |
| POST | `/api/portfolio/import/ocr` | Import from screenshot (Claude Vision) |

### Market Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/indices` | Real-time index quotes |
| GET | `/api/market/news` | Financial news feed |
| GET | `/api/market/fund/{code}` | Fund info (NAV + manager + rank) |
| GET | `/api/market/fund/{code}/nav` | NAV history (N days) |
| GET | `/api/market/fund/{code}/rank` | Fund ranking data |
| GET | `/api/market/macro` | Macro indicators (PMI/CPI) |

### Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analysis/overview` | Portfolio overview + Sharpe ratio |
| GET | `/api/analysis/attribution?by=fund` | Return attribution |
| GET | `/api/analysis/drawdown` | Drawdown analysis + recovery |
| GET | `/api/analysis/health` | 5-dimension health radar |
| GET | `/api/analysis/correlation` | Cross-holding correlation matrix |
| GET | `/api/analysis/suggestions` | Data-driven recommendations |

### AI Chat & Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI conversation (SSE streaming) |
| GET | `/api/report/weekly` | Get/generate weekly report |
| POST | `/api/report/generate` | Force regenerate report |

</details>

## Project Structure

```
wealthpilot/
├── src/                        # Frontend
│   ├── api/                    # API layer (client, portfolio, market, analysis, chat)
│   ├── pages/                  # 9 screen components
│   ├── components/             # 12 shared UI components
│   └── data/mock.ts            # Mock fallback data
└── backend/                    # Python backend
    └── src/wealthpilot/
        ├── main.py             # FastAPI entry
        ├── routes/             # 7 route modules, 24 endpoints
        ├── services/
        │   ├── agents/         # Multi-Agent system
        │   │   ├── base.py         # BaseAgent (shared tool-use loop)
        │   │   ├── router_agent.py # Intent classification + keyword fallback
        │   │   ├── market_agent.py # Fund info, NAV history, news (3 tools)
        │   │   ├── portfolio_agent.py # Overview, attribution, health, suggestions (4 tools)
        │   │   ├── risk_agent.py   # Drawdown, correlation, return calc (5 tools)
        │   │   ├── orchestrator.py # Router → specialist coordination
        │   │   ├── tools.py        # 12 tool schemas + unified dispatcher
        │   │   └── prompts.py      # Agent-specific system prompts
        │   ├── analysis.py     # Analysis engine (Sharpe, drawdown, health, correlation)
        │   ├── market_data.py  # Multi-source market data service
        │   └── agent.py        # Legacy single-agent (kept for rollback)
        └── storage/            # SQLite database
```

## Roadmap

- [x] Full-stack Agent architecture (FastAPI + React)
- [x] Real market data (AKShare + 东方财富 + 天天基金)
- [x] Multi-agent system (Router + Market/Portfolio/Risk agents, 12 tools)
- [x] Portfolio management (CRUD + CSV import + OCR)
- [x] Advanced analytics (Sharpe, max drawdown, correlation)
- [x] User auth (JWT + multi-tenant)
- [x] Docker Compose deployment
- [x] Weekly report (LLM-generated)
- [ ] Push notifications (drawdown alerts)
- [ ] Backtesting and scenario analysis
- [ ] Multi-asset class (stocks, bonds, ETFs, crypto)
- [ ] Export reports as PDF

## License

[MIT](LICENSE)
