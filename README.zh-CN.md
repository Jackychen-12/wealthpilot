<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI 智能投顾 Agent</strong><br/>
  <sub>基于 Claude 多智能体架构的持仓分析、风险洞察与投资决策辅助系统</sub>
</p>

<p align="center">
  <a href="./README.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English" /></a>
  <a href="./README.zh-CN.md"><img src="https://img.shields.io/badge/lang-中文-red?style=flat-square" alt="中文" /></a>
</p>

<p align="center">
  <a href="https://jackychen-12.github.io/wealthpilot/">在线演示</a> &nbsp;|&nbsp;
  <a href="https://jackychen-12.github.io/wealthpilot/showcase.html">功能展示</a> &nbsp;|&nbsp;
  <a href="#架构">架构</a> &nbsp;|&nbsp;
  <a href="#api-接口">API 接口</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" alt="React 18" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Claude_AI-多智能体-7C3AED?logo=anthropic&logoColor=white" alt="Claude AI" />
  <img src="https://img.shields.io/badge/AKShare-免费数据-FF6B35" alt="AKShare" />
  <img src="https://github.com/Jackychen-12/wealthpilot/actions/workflows/deploy.yml/badge.svg" alt="Deploy" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

---

## 这是什么？

WealthPilot 是一个**全栈 AI 智能投顾 Agent**，结合实时行情数据、持仓分析和 Claude AI 对话式洞察。用户可以管理基金持仓、获取自动化风险分析，并与 AI 进行多轮投资对话。

### 核心亮点

- **多智能体 AI** — 路由 Agent + 3 个专业 Agent（市场、持仓、风险），12 个 tool_use 工具，基于 Claude 驱动
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
| AI 对话 | Mock 回复 | 真实 Claude 多智能体 |
| OCR 导入 | ❌ | ✅ |
| 周报（LLM） | 模板兜底 | AI 生成完整报告 |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│              前端 (Vite + React + TypeScript)                  │
│   9 个页面 · API 层自带 Mock 兜底 · SSE 流式传输              │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE
┌───────────────────────────┴─────────────────────────────────┐
│              后端 (FastAPI · 24 个端点)                        │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐  │
│  │ 持仓管理  │ │ 行情服务  │ │ 多智能体系统  │ │  分析引擎  │  │
│  │ CRUD+    │ │          │ │              │ │ Sharpe/回撤│  │
│  │ 导入     │ │  多数据源  │ │  ┌────────┐  │ │ 健康度/    │  │
│  │ CSV/OCR  │ │          │ │  │ 路由器  │  │ │ 相关性/建议│  │
│  └──────────┘ └──────────┘ │  └──┬─┬─┬─┘  │ └───────────┘  │
│                            │     │ │ │     │       │         │
│                            │  ┌──┘ │ └──┐  │       │         │
│                            │  ▼    ▼    ▼  │       │         │
│                            │ 市场 持仓 风险 │       │         │
│                            │ 3工具 4工具 5工具│───────┘         │
│                            └──────────────┘                  │
│       │             │             │              │           │
│       └─────────────┼─────────────┼──────────────┘           │
│                     │             │                          │
│              ┌──────┴──────┐  ┌───┴────┐                    │
│              │   SQLite    │  │  JWT   │                    │
│              │ (持仓+对话   │  │  认证  │                    │
│              │  +用户)     │  │        │                    │
│              └─────────────┘  └────────┘                    │
└──────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
    Claude API         AKShare            东方财富/新浪
    (多智能体         (基金净值+          (指数行情
     + OCR +          排名+               + 新闻)
     周报)            宏观数据)
```

| 层级 | 技术栈 |
|------|--------|
| 前端 | Vite 6, React 18, TypeScript 5.6 |
| 后端 | Python 3.11+, FastAPI, SQLModel, Uvicorn |
| AI | Claude API (Anthropic SDK) — 多智能体（路由 + 市场/持仓/风险）, 视觉识别, 周报 |
| 数据 | AKShare（免费）, 东方财富 API, 天天基金 API, 新浪财经 API |
| 认证 | JWT (PyJWT) + bcrypt |
| 存储 | SQLite（开发）— 可切换 PostgreSQL |
| 部署 | Docker Compose, Railway, GitHub Pages |

## API 接口

<details>
<summary>完整 API 列表（点击展开）</summary>

### 认证

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册新用户 |
| POST | `/api/auth/login` | 登录，获取 JWT Token |
| GET | `/api/auth/me` | 获取当前用户信息 |

### 持仓管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/portfolio` | 持仓列表（含实时净值） |
| POST | `/api/portfolio` | 添加持仓 |
| PUT | `/api/portfolio/{id}` | 更新持仓 |
| DELETE | `/api/portfolio/{id}` | 删除持仓 |
| POST | `/api/portfolio/import/csv` | CSV/Excel 批量导入 |
| POST | `/api/portfolio/import/ocr` | 截图 OCR 导入（Claude Vision） |

### 行情数据

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/market/indices` | 实时指数行情 |
| GET | `/api/market/news` | 财经新闻 |
| GET | `/api/market/fund/{code}` | 基金信息（净值 + 经理 + 排名） |
| GET | `/api/market/fund/{code}/nav` | 净值历史（N 天） |
| GET | `/api/market/fund/{code}/rank` | 基金排名数据 |
| GET | `/api/market/macro` | 宏观指标（PMI/CPI） |

### 分析

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/analysis/overview` | 持仓总览 + Sharpe 比率 |
| GET | `/api/analysis/attribution?by=fund` | 收益归因 |
| GET | `/api/analysis/drawdown` | 回撤分析 + 恢复天数 |
| GET | `/api/analysis/health` | 5 维健康度雷达 |
| GET | `/api/analysis/correlation` | 持仓间相关性矩阵 |
| GET | `/api/analysis/suggestions` | 数据驱动投资建议 |

### AI 对话 & 周报

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/chat` | AI 对话（SSE 流式，多智能体） |
| GET | `/api/report/weekly` | 获取/生成周报 |
| POST | `/api/report/generate` | 强制重新生成周报 |

</details>

## 项目结构

```
wealthpilot/
├── src/                        # 前端
│   ├── api/                    # API 层（client, portfolio, market, analysis, chat）
│   ├── pages/                  # 9 个页面组件
│   ├── components/             # 12 个共享 UI 组件
│   └── data/mock.ts            # Mock 兜底数据
└── backend/                    # Python 后端
    └── src/wealthpilot/
        ├── main.py             # FastAPI 入口
        ├── routes/             # 7 个路由模块，24 个端点
        ├── services/
        │   ├── agents/         # 多智能体系统
        │   │   ├── base.py         # BaseAgent（共享 tool-use 循环）
        │   │   ├── router_agent.py # 意图分类 + 关键词兜底
        │   │   ├── market_agent.py # 基金信息、净值历史、新闻（3 个工具）
        │   │   ├── portfolio_agent.py # 总览、归因、健康度、建议（4 个工具）
        │   │   ├── risk_agent.py   # 回撤、相关性、收益率计算（5 个工具）
        │   │   ├── orchestrator.py # 路由 → 专业 Agent 协调
        │   │   ├── tools.py        # 12 个工具 schema + 统一执行器
        │   │   └── prompts.py      # 各 Agent 专属 system prompt
        │   ├── analysis.py     # 分析引擎（Sharpe、回撤、健康度、相关性）
        │   ├── market_data.py  # 多源行情数据服务
        │   └── agent.py        # 旧版单 Agent（保留用于回滚）
        └── storage/            # SQLite 数据库
```

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

## 路线图

- [x] 全栈 Agent 架构（FastAPI + React）
- [x] 真实行情数据（AKShare + 东方财富 + 天天基金）
- [x] 多智能体系统（路由 + 市场/持仓/风险 Agent，12 个工具）
- [x] 持仓管理（CRUD + CSV 导入 + OCR）
- [x] 高级分析（Sharpe、最大回撤、相关性）
- [x] 用户认证（JWT + 多租户）
- [x] Docker Compose 部署
- [x] 周报（LLM 生成）
- [ ] 推送通知（回撤预警）
- [ ] 回测与情景分析
- [ ] 多资产类别（股票、债券、ETF、加密货币）
- [ ] 导出报告为 PDF

## 开源协议

[MIT](LICENSE)
