<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>以 A 股个股为主导的 AI 多智能体投研系统</strong><br/>
  <sub>Multi-Agent Architecture · Claude & DeepSeek · 35 Real-time Tools · One-command Deploy</sub>
</p>

<p align="center">
  <a href="https://jackychen-12.github.io/wealthpilot/">Live Demo</a> &nbsp;|&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;|&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;|&nbsp;
  <a href="#api-reference">API Docs</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white" alt="React 19" />
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

大多数投资分析工具只是简单地调用一次 LLM 生成文本。WealthPilot 不同——它是一个**完整的多智能体系统**，先把问题里的证券名解析成确定的代码，Planner 按研究模板或自由规划拆出任务图，7 个按研究维度分工的 Agent（基本面 / 估值 / 走势 / 行业 / 选股 / 组合 / 基金）并发取证，Critic 双闸门审核证据与回答，通过后才发布结论 —— 每个数字都能追溯到一次工具调用。

以 **A 股个股**为主导，覆盖个股深度研究、持仓组合管理、选股三个场景；基金保留为持仓的一种。

### 核心优势

| | 优势 | 说明 |
|--|------|------|
| 🤖 | **按研究维度分工的多智能体** | 证券解析 → Planner 拆解任务 DAG → 7 个 Agent 并发执行 → Critic 双闸门 → Synthesizer 整合并消解冲突 |
| 📐 | **研究模板** | 个股深度研究 / 个股对比 / 持仓诊断 / 选股四类问题走固定的任务图和报告章节，质量稳定；其余问题由模型自由规划 |
| 🧭 | **不让模型猜代码** | 「宁德时代」「茅台」先由代码解析成 300750、600519，再交给 Agent；解析不到就直说 |
| 🎯 | **风险画像硬约束** | 风险测评结果注入 Planner/Agent/Synthesizer 三处；未测评时不得给出具体仓位比例 |
| 🔍 | **证据溯源 + Critic 闸门** | 每次工具调用生成证据 ID `[E-…]`，回答必须逐条引用；数字回查不到、证据不足或越过画像约束的草稿不会发布 |
| 🔧 | **35 个实时工具** | 个股行情、财务指标、估值历史分位、同行对比、公告、全市场选股，加上持仓、风险、穿透、回测，以及把算术从 LLM 手里拿走的 compute/check 工具 |
| 🌐 | **双模型支持** | Claude & DeepSeek 一行配置切换，Provider 抽象层自动适配 Anthropic SDK / OpenAI SDK |
| 📊 | **免费实时数据** | AKShare + 东方财富 + 天天基金 + 新浪财经，无需付费数据源 |
| ⚡ | **过程可见的 SSE** | 规划、工具调用、证据、Critic 结论实时推送；正文在通过校验后才下发，未过审的草稿不会流到用户面前 |
| 🔌 | **MCP Server** | 35 个工具通过 MCP 协议暴露，Claude Code / Cursor 直接调用，无需自建 Agent |
| 💻 | **多入口调用** | Web UI / 终端交互 / CLI 管道 / MCP，任选其一接入分析能力 |
| 🖥️ | **投研工作台** | 17 个功能页：今日、个股详情（财务 / 估值分位 / 同行 / 公告）、选股器、自选股、研究记录等，页面与 Agent 共用同一批工具 |
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
# 工作台: http://localhost:5180  |  Backend API: http://localhost:8000/docs
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
| 个股详情、选股器、自选股、全局搜索 | ✅ | ✅ |
| AI 研究 | 提示未配置 Key（在线演示可回放录好的研究过程） | **多 Agent 实时分析** |
| 截图 OCR 导入 | ❌ | ✅（仅 Anthropic Key，Claude Vision） |
| MCP Server 的 35 个工具 | ✅（不调用 LLM） | ✅ |
| AI 周报 | 模板回退 | **LLM 智能生成** |

---

## Architecture

### 多智能体系统

WealthPilot 的 AI 核心是 **证券解析 + Planner + 7 个专业 Agent + Critic + Synthesizer** 的协作流程，不是单次 LLM 调用：

```
用户消息
   │
   ▼
┌──────────────────┐
│ 证券解析（纯代码）│  「宁德时代」→ 300750（股票）；Agent 只许用解析出的代码
└──────┬───────────┘
       ▼
┌──────────────────┐
│  Planner         │  意图识别：命中研究模板 → 代码生成任务图 + 固定章节
│                  │  否则 LLM 自由拆解（不可用时关键词兜底）
└──────┬───────────┘
       │  无依赖的任务同波并发（asyncio.gather）
       ├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
       ▼          ▼          ▼          ▼          ▼          ▼          ▼
  🏢 基本面   ⚖️ 估值    📈 走势   🏭 行业市场  🔎 选股   💼 组合风险  🧺 基金
   5 工具     4 工具     7 工具     6 工具     2 工具     11 工具     8 工具
   业绩指标   PE/PB     行情日线   同行公司   全市场     总览归因    净值信息
   ROE/负债   历史分位   均线波动   行业排行   条件筛选   回撤相关性  基金对比
   分红       同行对比   收益回撤   公告要闻              穿透/推演   重仓重叠
                        规则回测   大盘概况              画像约束    规则回测
       │  每次工具调用 → 一条带 ID 的证据 [E-…]（来源、数据日期、口径）
       ▼
┌──────────────────┐   不足 → 补充任务重跑（最多 CRITIC_MAX_REPLANS 轮）
│ Critic 闸门 A    │   证据能否支撑 success_criteria（一次小额 LLM 调用）
└──────┬───────────┘
       ▼
┌──────────────────┐
│ Synthesizer      │  跨 Agent 整合 + 冲突消解；模板研究按固定章节成文
└──────┬───────────┘
       ▼
┌──────────────────┐   不过 → 带意见重写（最多 CRITIC_MAX_REWRITES 次）
│ Critic 闸门 B    │   纯代码：数字溯源、证据引用、画像约束、
│                  │   章节完整、财务数字带报告期、禁止目标价与确定性预测
└──────┬───────────┘
       ▼
  发布回答（status: passed；有证据缺口、或个别数字无法核对时为 partial，回答里点名标注）
  否则只发布未通过的原因（insufficient_data / rejected / failed），不发布草稿
```

**研究模板（Playbook）**

| 模板 | 触发 | 任务图 | 固定章节 |
|---|---|---|---|
| `stock_deep` 个股深度研究 | 一只股票 + 综合性问题 | 基本面 ∥ 估值 ∥ 走势 ∥ 行业 | 结论 / 基本面 / 估值 / 走势 / 行业位置 / 风险 / 待验证 |
| `stock_compare` 个股对比 | 两到三只股票 | 每只各跑 基本面 ∥ 估值 | 对比表 / 各自强弱 / 结论 |
| `holding_review` 持仓诊断 | 「我的持仓 / 组合」 | 组合 → 对重点持仓跑 基本面 ∥ 估值 | 组合概况 / 集中度与回撤 / 重点持仓 / 约束校验 |
| `screen` 选股 | 含筛选条件 | 选股 → 对候选跑 估值 | 条件复述 / 候选表 / 逐只要点 / 局限 |
| 自由问答 | 其他，或只问一个点 | LLM 拆解，通常 1–2 个 Agent | 自由 |

**关键设计**

1. **按研究维度分工，不按资产类型**：基本面、估值、走势、行业互不依赖，天然可以并行；每个 Agent 的工具集小，模型不容易选错。组合与风险共用同一批计算工具，合成一个 Agent。
2. **证券解析在规划之前**：名称 → 代码由搜索接口确定，写进每个子任务的上下文；模型不凭记忆写代码。
3. **固定套路走固定流程**：四类常见问题由代码生成任务图，同一类问题每次的拆法和报告结构一致。
4. **真并发**：`BaseAgent.run` 是 async 的；同一轮内的多个工具调用用 `asyncio.gather` 并发。同步 SDK 通过 `streaming.py` 搬到工作线程，不阻塞事件循环。
5. **证据是一等公民**：工具结果连同证据 ID 一起交给模型，回答逐行引用 `[E-…]`；同一轮研究内相同的工具调用只执行一次，并有调用次数与超时预算。
6. **宁可不答，不可乱答**：Critic 不通过、任务失败、输出被截断或被拒绝时，系统发布的是"为什么没有结论"，而不是未经校验的草稿。
7. **只陈述事实与推断**：不给目标价，不做确定性的涨跌预测；财务数字必须带报告期。
8. **风险画像是硬约束**：`InvestorProfile` 注入 Planner / 各 Agent / Synthesizer。未完成测评时，不得给出具体仓位比例或止损价位。
9. **算术不交给 LLM**：占比、变动后的集中度、仓位上限、选股筛选都由确定性代码计算。

**评测**（`backend/scripts/eval.py`，12 题，DeepSeek 真实模型，2026-10-04 各跑一次）

| 指标 | 重构前（5 个按资产分的 Agent） | 现在（7 个按维度分的 Agent + 模板） |
|---|---|---|
| 通过校验 | 4 / 12 | 9 / 12 |
| 带标注发布（partial） | 7 | 3 |
| 未发布 | 1 | 0 |
| 平均被打回次数 | 1.83 | 1.33 |
| 平均耗时 | 25.7 秒 | 36.8 秒 |
| 平均工具调用 | 9.2 | 11.1 |

样本只有 12 题、每版只跑一次，模型输出有随机性，这组数字说明方向而不是精确幅度。代价是深度研究更慢（一次要跑四个 Agent）。评测后又收紧了规划提示：只问单一维度的问题（如"最近业绩怎么样"）不再走深度研究模板。复现：`uv run python scripts/eval.py --out new.json`，对比用 `--compare old.json new.json`。

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
│          Workbench (Vite + React 19 + TypeScript)             │
│   17 pages · real data only · SSE research process view       │
│   global security search · recorded read-only demo mode       │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────┴─────────────────────────────────┐
│                Backend (FastAPI · 54 endpoints)                │
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
│                                │  7 Agents     │            │
│                                │   → Critic    │            │
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
| Frontend | Vite 7, React 19, TypeScript 5.9, Tailwind 4, Recharts（`workbench/`） |
| Backend | Python 3.11+, FastAPI, SQLModel, Uvicorn |
| AI | Claude API (Anthropic SDK) + DeepSeek (OpenAI SDK)，证券解析 / Planner / 7 Agent / Critic / Synthesizer |
| 数据源 | AKShare（免费）、东方财富 API、天天基金 API、新浪财经 API |
| 认证 | JWT (PyJWT) + bcrypt，多租户隔离 |
| 存储 | SQLite（开发），可替换 PostgreSQL |
| 部署 | Docker Compose, Makefile, Railway, GitHub Pages |
| 集成 | MCP Server (stdio), CLI 非交互模式 |
| CLI | `python -m wealthpilot run/init/config/chat/mcp/ask` |

---

## Features

### 功能矩阵

| 模块 | 功能 | 数据来源 |
|------|------|---------|
| **持仓管理** | 增删改查、CSV/Excel 批量导入、截图 OCR 识别导入 | 用户输入 + Claude Vision |
| **持仓分析** | 周收益、超额收益、Sharpe 比率、三维度收益归因 | AKShare + 天天基金实时净值 |
| **风险洞察** | 最大回撤 + 恢复天数、5 维健康度雷达、持仓相关性矩阵 | 近 60 个交易日净值历史 |
| **个股研究** | 行情与日线、多期财务指标、PE/PB/PS 历史分位、同行业对比、均线与波动、公告、分红 | 腾讯行情 + 东方财富数据中心 |
| **选股** | 按行业、市值、PE、PB、ROE、营收与净利增速筛选全部 A 股；行业涨跌排行、市场涨跌家数 | 全市场估值与业绩快照（每日缓存） |
| **自选股** | 关注列表 + 备注，带最新行情 | SQLite + 新浪行情 |
| **AI 研究** | 证券解析 + 研究模板 + 并发取证 + Critic 校验 + 多轮对话；过程全程可视化，每次研究连同证据存入研究记录 | Claude/DeepSeek + 实时市场数据 |
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

| 分组 | 页面 | 做什么 | 背后的能力 |
|---|---|---|---|
| — | **今日** | 首页：指数与涨跌家数、行业强弱、自选股、持仓市值与盈亏、预警、最近的研究 | 行业与市场工具 |
| — | 全局搜索 | 侧栏顶部，按 `/` 唤起；输入名称或代码，回车进个股或基金详情 | 证券解析 |
| 研究 | **AI 研究** | 四个研究模板入口 + 自由提问；右侧实时显示解析出的证券、任务规划、每次工具调用的证据、Critic 的通过 / 打回 | Planner + 7 个 Agent + Critic |
| | **个股** | 多标签详情：概览与走势 / 财务（多期指标 + 增速图 + 分红）/ 估值（历史分位带 + 同行对比）/ 同行 / 公告；可一键深度研究、加自选 | 基本面 / 估值 / 走势 / 行业工具 |
| | **选股器** | 条件表单 → 结果表 → 多选后交给 AI 对比或加自选。筛选是确定性的，AI 只负责解读 | 选股 |
| | 自选股 | 关注列表与备注 | — |
| 组合 | 持仓 | 股票 / ETF / 基金按类型分组（股票在前），增删改、CSV / Excel 导入、截图识别 | — |
| | 组合总览 | 市值、收益、持仓分布、收益归因（按标的 / 行业 / 类别）、要闻与指数 | 组合 Agent |
| | 持仓穿透 | 直接持股与基金间接持股合并：真实暴露、被多只基金同时重仓的票、两只基金的重仓股重叠 | 组合 / 基金工具 |
| 风险 | 风险体检 | 回撤、5 维健康度、相关性矩阵、集中度、预警 | 组合 Agent |
| | 压力测试 | 预设情景下组合损益与逐持仓明细 | 情景分析 |
| | 调仓推演 | 调仓前先算：占比、集中度、回撤估计怎么变，是否越过风险画像 | 计算 / 校验工具 |
| 工具 | 规则回测 | 分批建仓规则的历史表现，对比一次性买入与定投 | 走势 / 基金工具 |
| | 基金查询 | 任意基金的净值走势、阶段收益、经理与基准 | 基金 Agent |
| 设置 | 风险画像 / 周报 | 设置 AI 给建议时必须遵守的约束；按需生成复盘 | — |
| | 数据连接 | 查看并测试已接入的券商 / 数据商 MCP 服务，标明哪些工具可用、哪些被屏蔽 | 外部连接器 |
| | **研究记录** | 回看任何一次研究的回答、校验结论和当时取得的证据 | — |

功能页通过 `POST /api/tools/{name}` 直接调用 Agent 的工具，所以页面上的数和 AI 回答里引用的证据出自同一份实现。每个功能页右上角都可以把当前话题一键交给 AI 解读。

工作台代码在 `workbench/`（React 19 + Vite + Tailwind 4），视觉遵循 Notion 的设计规范：白色画布、暖灰侧栏、细线边框、柔和色标签。未登录时使用本机匿名档（`user_id = 0`）的持仓，登录后切换到自己的账户。

**在线演示**（GitHub Pages）是同一个工作台的只读版本：Pages 上没有后端，所以构建成演示模式（`make demo-build`），回放一份示例组合在真实行情、真实工具、真实模型上跑出来的结果，页面顶部有明确标注。数据快照由 `make record-demo` 录制，写操作和没录过的查询会如实提示"演示模式不支持"。

---

## A 股个股

个股是现在的主线（只做 A 股）：

- **个股深度研究**：问"帮我分析一下宁德时代"，基本面、估值、走势、行业四个 Agent 并行取证，按固定章节成文，每个数字带证据。
- **估值历史分位**：PE / PB / PS 在近五年自身历史里的位置，以及在同行业盈利公司里的 PE 排名与行业中位数。
- **多期财务指标**：营收、归母与扣非净利润、ROE、毛利率、净利率、资产负债率、每股经营现金流，每条带报告期；另有分红记录。
- **选股**：全市场约 5500 只股票的估值与最新一期业绩快照，按条件确定性筛选；行业涨跌排行按成分股涨跌幅中位数统计。
- **历史行情打通**：持仓里的股票 / ETF 走前复权日线，和基金净值用同一种结构，回撤、Sharpe、相关性、健康度、压力测试都会把它们算进去。
- **穿透合并直接持股**：直接持有的个股会和基金重仓股里的同一只票合并，一眼看出"我直接买了茅台，基金里又间接持有多少"。
- **老工具兼容股票**：区间收益、最大回撤、规则回测带 `asset_type` 参数；股票回测默认计入 0.1% 单边费用，并在局限说明里写明未处理停牌与涨跌停。

几点如实说明：

- 估值分位只和**自己的历史**比，不代表绝对便宜或贵；亏损期 PE 为负，没有可用的分位。
- 财务数据是滞后数据，各期金额为累计值；选股用的 ROE 与增速取自最新一期报表。
- 行业分类来自东方财富的板块归属；行业涨跌是成分股涨跌幅的中位数，不是行业指数。
- **没有做资金流向**：对应的免费接口实测频繁断连，宁可不做也不给不稳定的数。
- 行情源都是免费接口，偶尔会取不到；取不到时工具会直说，不会编默认值。
- 不给目标价，不做买卖点预测；港股、美股暂不支持。

规划与进度见 [docs/stock-roadmap.md](docs/stock-roadmap.md)。

---

## 接入券商与金融数据服务（MCP）

很多券商和数据商开始提供 MCP 服务。WealthPilot 留了一个接入口，把它们的工具交给 Agent 使用：

```
backend/connectors.json            ← 你的配置（已被 git 忽略）
backend/connectors.example.json    ← 模板
```

```json
{
  "connectors": [
    {
      "name": "my_broker",
      "label": "我的券商（只读）",
      "kind": "broker",
      "transport": "http",
      "url": "https://对方提供的地址/mcp",
      "auth_env": "BROKER_MCP_TOKEN",
      "enabled": true
    }
  ]
}
```

- **只读，硬性屏蔽交易**：名字或说明像下单、撤单、转账、申赎的工具一律不暴露给 Agent，也不能通过本服务调用，配置里的白名单也绕不过。WealthPilot 只做研究与分析，不代你交易。
- **凭据不进配置文件**：`auth_env` 只写环境变量名，令牌放在 `backend/.env`；接口返回里不会出现令牌或启动命令。
- **只在服务器端配置**：没有"通过网页新增连接器"的接口——那等于让服务器替网页用户访问任意地址或执行命令。
- **照常进证据链**：外部工具的返回和内置工具一样生成证据 ID，接受 Critic 的数字溯源。
- 支持 HTTP（Streamable HTTP）和 stdio 两种传输；工作台的"数据连接"页可以测试连通性，并列出每个工具是可用还是被屏蔽。
- 模板里带一个 `wealthpilot_self` 示例：把本项目自己的 MCP Server 当外部服务接进来，用来验证链路。

哪家机构提供 MCP 服务、地址和鉴权方式，以对方官方文档为准；本项目不预置任何厂商的接入。

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

WealthPilot 提供标准 **MCP (Model Context Protocol) Server**，将 35 个投资分析工具直接暴露给 Claude Code、Cursor 等 MCP 客户端。Claude 可以自主调用这些工具获取实时行情和持仓分析——**无需自建 Agent，无需 API Key**（MCP Server 本身不调用 LLM）。

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
| `backtest_rule` | fund_code, triggers[], stop_loss_pct?, days?, asset_type? | 分批建仓规则回测，对比两个基线 |
| `resolve_security` | query | 名称 / 简称 / 代码 → 确定的代码与类型（股票 / ETF / 基金） |
| `get_stock_quote` | code | 个股实时行情：价格、涨跌、PE、PB、市值、成交额 |
| `get_stock_kline` | code, days? | 前复权日线摘要：区间收益、高低点、所处位置 |
| `get_stock_valuation` | code | 当前 PE / PB 与近一年价格区间位置 |
| `get_stock_profile` | code | 所属行业、板块、市值 |
| `get_stock_financials` | code, periods? | 最近几期业绩（带报告期） |
| `get_financial_indicators` | code, periods? | 多期财务指标：扣非净利、净利率、负债率、每股经营现金流等 |
| `get_dividend_history` | code | 分红记录与股息率 |
| `get_valuation_history` | code | PE / PB / PS 近五年历史分位 |
| `compare_peers_valuation` | code | 同行业 PE 中位数与排名 |
| `get_technical_indicators` | code | MA5 / 20 / 60、均线排列、20 日年化波动率 |
| `get_industry_peers` | code | 同行业公司（按市值） |
| `get_stock_announcements` | code | 最近公告 |
| `get_sector_ranking` | top? | 当日行业涨跌排行 |
| `get_market_overview` | — | 指数、涨跌家数、涨跌幅中位数 |
| `screen_stocks` | 条件… | 按估值 / 盈利 / 增长条件筛选全部 A 股 |

---

## Makefile 速查

```bash
make setup     # 首次配置：安装依赖 + 复制 .env
make dev       # 启动后端 + 工作台（http://localhost:5180）
make backend   # 仅启动后端
make workbench # 仅启动工作台
make demo-build   # 构建在线演示版（只读，回放录好的结果）
make record-demo  # 重新录制演示数据（会调用真实模型）
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
<summary>完整 API 列表（42 个端点，点击展开）</summary>

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

### Market Data（9）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/indices` | 实时指数行情 |
| GET | `/api/market/news` | 财经新闻流 |
| GET | `/api/market/fund/{code}` | 基金信息（净值 + 经理 + 排名） |
| GET | `/api/market/fund/{code}/nav` | 历史净值（N 日） |
| GET | `/api/market/fund/{code}/rank` | 基金排名数据 |
| GET | `/api/market/macro` | 宏观指标（PMI/CPI） |
| GET | `/api/market/stock/{code}` | 股票 / ETF 行情与估值 |
| GET | `/api/market/stock/{code}/kline` | 股票 / ETF 前复权日线 |
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

### Connectors（2）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/connectors` | 已配置的外部 MCP 连接器（不含凭据与启动命令） |
| POST | `/api/connectors/{name}/test` | 连接一次，列出工具并标明可用 / 屏蔽 |

### Research（10）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/securities/search?q=` | 按名称、简称或代码搜索 A 股、ETF、基金 |
| GET / POST | `/api/watchlist` | 自选列表（带最新行情）/ 加自选 |
| PUT / DELETE | `/api/watchlist/{id}` | 改备注 / 移出自选 |
| POST | `/api/screener` | 按条件筛选全部 A 股（与 `screen_stocks` 工具同一份实现） |
| GET | `/api/screener/industries` | 行业列表与成分股数量 |
| GET | `/api/research/history` | 研究记录列表 |
| GET | `/api/research/history/{id}` | 一次研究的回答与当时的证据 |
| GET | `/api/research/stats` | 研究次数 |

### Tools（2）

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tools` | 35 个 Agent 工具及入参说明，按 Agent 分组 |
| POST | `/api/tools/{name}` | 直接执行一个工具，返回 `{ok, data, as_of}`；工作台功能页走这里 |

`/api/chat` 的 SSE 事件类型：`resolved`（解析出的证券）、`plan`（含 `playbook`）、`task_start`、`tool_call`、`evidence`、`task_done`、`critic`、`replan`、`synthesizing`、`delta`、`grounding_warning`、`error`、`done`（`done.meta.status` 为 `passed` / `partial` / `insufficient_data` / `rejected` / `failed`）。

</details>

---

## Project Structure

```
wealthpilot/
├── Makefile                     # 一键命令入口
├── docker-compose.yml           # Docker 部署
│
├── workbench/                   # ⭐ 投研工作台（桌面端，日常使用入口）
│   └── src/
│       ├── api/                 #   接口层（失败即报错，无示例数据兜底）+ 研究会话状态
│       ├── components/          #   Notion 风格组件（kit）、页面积木（ui）、外壳与导航
│       ├── pages/               #   17 个功能页：今日 / 研究 / 个股 / 选股器 / 自选股 / 持仓 / 总览 / 穿透 / 风险 / 压测 / 调仓 / 回测 / 基金 / 画像 / 数据连接 / 周报 / 研究记录
│       └── demo/                #   在线演示模式：录好的真实结果 + 回放逻辑
│
├── docs/stock-roadmap.md        # 股票能力规划
│
└── backend/                     # Backend (Python)
    ├── .env.example             #   环境配置模板
    └── src/wealthpilot/
        ├── __main__.py          #   CLI 入口 (run/init/config/chat/mcp/ask)
        ├── mcp_server.py        #   ⭐ MCP Server（35 工具，for Claude Code）
        ├── main.py              #   FastAPI 应用
        ├── settings.py          #   配置管理（支持双 Provider）
        ├── routes/              #   13 个路由模块，54 个端点（含 research：搜索 / 自选 / 选股 / 研究记录）
        ├── models/              #   数据模型（SQLModel）
        ├── services/
        │   ├── ai_client.py     #   ⭐ Provider 抽象层（Anthropic / DeepSeek 自动适配）
        │   ├── agents/          #   ⭐ 多智能体系统
        │   │   ├── base.py      #     BaseAgent — 异步 tool-use 循环 + 并发工具
        │   │   ├── planner_agent.py # ⭐ Planner — 意图识别、研究模板、任务 DAG 拆解 + 关键词兜底
        │   │   ├── playbooks.py #     ⭐ 四个研究模板：任务图与固定章节
        │   │   ├── registry.py  #     ⭐ 7 个 Agent 的定义（职责、提示词、工具组）
        │   │   ├── critic_agent.py  # ⭐ Critic — 证据充分性 + 输出合规性双闸门
        │   │   ├── synthesizer_agent.py # ⭐ Synthesizer + 数值溯源检查
        │   │   ├── streaming.py #     同步 SDK → 异步事件流桥接
        │   │   ├── orchestrator.py #  编排器 — Resolve → Plan → Execute → Critic → Synthesize
        │   │   ├── tools.py     #     35 个工具定义 + 统一执行器
        │   │   └── prompts.py   #     持仓 / 画像上下文与 Synthesizer 提示词
        │   ├── securities.py    #   ⭐ 证券解析：名称 → 代码
        │   ├── screener.py      #   全市场快照、条件筛选、行业排行
        │   ├── cache.py         #   SQLite 数据缓存（按 TTL）
        │   ├── context.py       #   Web / CLI / MCP 共用的持仓与行情上下文加载
        │   ├── stocks.py        #   A 股个股数据：日线、行情、财务指标、估值历史、同行、公告、分红
        │   ├── connectors.py    #   外部 MCP 连接器（只读，屏蔽交易类工具）
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

启动后工作台在 http://localhost:5180，由 nginx 托管并把 `/api` 反代到后端容器。

### 后端与工作台分开部署

1. 后端：任意能跑容器的平台（如 Railway），Root Directory = `backend`，设置模型 Key 与 `JWT_SECRET`，并把 `FRONTEND_URL` 设为工作台的域名（CORS 白名单）
2. 工作台：`cd workbench && VITE_API_URL=https://你的后端域名 npm run build`，把 `dist/` 放到任意静态托管

### GitHub Pages 在线演示

推送到 `main` 后由 `.github/workflows/deploy.yml` 自动构建演示版并发布，不需要后端。

---

## Roadmap

- [x] Full-stack Agent 架构（FastAPI + React）
- [x] 免费实时行情（AKShare + 东方财富 + 天天基金）
- [x] 多智能体系统（Planner + 7 个按研究维度分工的 Agent，35 工具）
- [x] Provider 抽象层（Claude + DeepSeek 一键切换）
- [x] 持仓管理（CRUD + CSV 导入 + OCR）
- [x] 高级量化分析（Sharpe、最大回撤、相关性矩阵）
- [x] 用户认证（JWT + 多租户隔离）
- [x] 对话历史持久化
- [x] CLI 工具（init/config/chat/run）
- [x] MCP Server（35 工具，Claude Code / Cursor 直接调用）
- [x] CLI 非交互模式（ask 子命令，支持管道）
- [x] Docker Compose 部署
- [x] AI 周报生成
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
- [x] 投研工作台（桌面端，17 个功能页，Agent 的每项能力都有对应页面）
- [x] 工具直调接口（功能页与 Agent 共用同一批工具）
- [x] **A 股个股**（历史行情、个股工具、并入穿透与回测）
- [x] **外部 MCP 连接器**（券商 / 数据商接入口，只读，交易类工具硬性屏蔽）
- [x] **股票主导的架构**（证券解析、按研究维度分工的 7 个 Agent、四个研究模板、Critic 新增章节 / 报告期 / 禁止预测三条规则）
- [x] **估值历史分位、多期财务指标、同行对比、公告、分红**
- [x] **选股**（全市场快照 + 条件筛选 + 行业排行）
- [x] **今日首页、全局搜索、个股多标签详情、自选股、选股器、研究记录**
- [x] 回答质量评估（12 题评测集 + 新旧架构对比，见 Architecture 一节）
- [ ] 股票后续：资金流向（等稳定数据源）、行业自动归因、单票上限约束、港美股，见 [docs/stock-roadmap.md](docs/stock-roadmap.md)
- [ ] 评测集扩到 20 题以上并多次取平均
- [ ] 结构化记忆层（用户偏好与被否决建议）
- [ ] PostgreSQL + Alembic 正式迁移

## 致谢

- 工作台的工程脚手架与外壳结构起步于 [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 的 Web 端（MIT），许可见 `workbench/THIRD_PARTY_LICENSE.dsa-web`
- 视觉规范参考 [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 中的 Notion 设计分析

## License

[MIT](LICENSE)
