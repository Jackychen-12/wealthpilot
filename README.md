<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI-Powered Investment Advisory Agent</strong><br/>
  <sub>智能投顾 Agent — 基于 Claude AI 的持仓分析、风险洞察与投资决策辅助</sub>
</p>

<p align="center">
  <a href="https://jackychen-12.github.io/wealthpilot/">Live Demo</a> &nbsp;|&nbsp;
  <a href="#features">Features</a> &nbsp;|&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;|&nbsp;
  <a href="#getting-started">Getting Started</a> &nbsp;|&nbsp;
  <a href="#api-reference">API Reference</a> &nbsp;|&nbsp;
  <a href="#deployment">Deployment</a>
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

## What is WealthPilot?

WealthPilot is a **full-stack AI investment advisory agent** that combines real-time market data, portfolio analysis, and Claude AI-powered conversational insights. Users can manage their fund portfolio, get automated risk analysis, and have intelligent multi-turn conversations about their investments.

### Key Highlights

- **Real AI Agent** — Claude with 5 tool-use capabilities (fund lookup, NAV history, return calculation, fund comparison, news search)
- **Real Market Data** — Free data from AKShare + 东方财富 + 天天基金 + 新浪财经 (no paid API keys needed for market data)
- **Full Backend** — FastAPI with 24 REST endpoints, SQLite storage, JWT auth
- **Multi-tenant** — User registration/login, each user has isolated portfolio and chat history
- **Multiple Import Methods** — Manual input, CSV/Excel bulk import, screenshot OCR (via Claude Vision)
- **One-click Deploy** — Docker Compose for self-hosting, Railway-ready

---

## Features

| Module | Description | Data Source |
|--------|-------------|-------------|
| **Portfolio Management** | Add/edit/delete fund holdings; CSV/Excel bulk import; screenshot OCR import | User input + Claude Vision |
| **Smart Portfolio Analysis** | Weekly return, excess return, Sharpe ratio, return attribution (by fund/industry/asset type) | AKShare + 天天基金 real-time NAV |
| **Risk Insight Engine** | Max drawdown + recovery days, portfolio health radar (5 dimensions), correlation matrix | Calculated from 60-day NAV history |
| **AI Conversational Q&A** | Multi-turn dialogue with SSE streaming, Claude tool_use for real-time data retrieval | Claude API + real-time market data |
| **Automated Suggestions** | Rule-engine + data-driven: concentration risk, loss alerts, correlation warnings | Analysis engine output |
| **Weekly Report** | LLM-generated structured review (summary, key points, focus, AI insight) | Claude API + analysis data |
| **Market Tracking** | Real-time index quotes (上证/深证/创业板), financial news feed | 东方财富 + 新浪财经 |
| **User Auth** | JWT-based registration/login, multi-tenant data isolation | SQLite + bcrypt |

### Screens

```
Home ─────→ Portfolio (manage holdings)
  │              │
  │              ├── Import CSV/Excel
  │              └── Import via Screenshot OCR
  │
  ├──→ Overview ──→ Attribution (by fund / industry / asset)
  │         │
  │         ├──→ Drawdown (max drawdown + recovery analysis)
  │         │
  │         ├──→ Health (5-dimension radar + scores)
  │         │
  │         ├──→ Suggestions (AI recommendations)
  │         │
  │         └──→ Weekly Report (LLM-generated)
  │
  └──→ Chat (Claude AI agent with tool_use + SSE streaming)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Frontend (Vite + React + TypeScript)             │
│   9 pages · API layer with mock fallback · SSE streaming     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE
┌───────────────────────────┴─────────────────────────────────┐
│              Backend (FastAPI · 24 endpoints)                 │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Portfolio │ │  Market  │ │  Agent   │ │   Analysis    │  │
│  │ CRUD+    │ │  Data    │ │  (Chat)  │ │   Engine      │  │
│  │ Import   │ │  Service │ │ +Tools   │ │ Sharpe/DD/    │  │
│  │ CSV/OCR  │ │          │ │ +Stream  │ │ Health/Corr   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
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
    (Chat Agent      (Fund NAV +         (Index quotes
     + OCR +          Rankings +          + News)
     Report)          Macro data)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vite 6, React 18, TypeScript 5.6 |
| Backend | Python 3.11+, FastAPI, SQLModel, Uvicorn |
| AI | Claude API (Anthropic SDK) — chat, tool_use, vision, report generation |
| Data | AKShare (free), 东方财富 API, 天天基金 API, 新浪财经 API |
| Auth | JWT (PyJWT) + bcrypt password hashing |
| Storage | SQLite (dev) — easy to swap for PostgreSQL |
| Deploy | Docker Compose, Railway, GitHub Pages (frontend) |

---

## Getting Started

### Prerequisites

- Node.js 18+ (frontend)
- Python 3.11+ (backend)
- [uv](https://docs.astral.sh/uv/) (Python package manager, optional but recommended)

### Quick Start (3 commands)

```bash
# 1. Clone
git clone https://github.com/Jackychen-12/wealthpilot.git
cd wealthpilot

# 2. Start backend
cd backend
cp .env.example .env    # Edit .env to add ANTHROPIC_API_KEY (optional for basic features)
uv sync                 # or: pip install -e .
uv run uvicorn wealthpilot.main:app --reload --port 8000

# 3. Start frontend (new terminal)
cd ..  # back to root
npm install
npm run dev
# Visit http://localhost:5173/wealthpilot/
```

### With Docker (easiest)

```bash
cd wealthpilot
cp backend/.env.example backend/.env
# Edit backend/.env — add ANTHROPIC_API_KEY for AI features

docker compose up --build
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000/docs
```

### What works without API keys?

| Feature | Without key | With ANTHROPIC_API_KEY |
|---------|-------------|----------------------|
| Portfolio CRUD | ✅ | ✅ |
| Market data (indices, news, NAV) | ✅ | ✅ |
| Analysis (Sharpe, drawdown, health) | ✅ | ✅ |
| AI Chat | Mock responses | Real Claude Agent with tools |
| OCR Import | ❌ | ✅ |
| Weekly Report (LLM) | Fallback template | Full AI-generated |

---

## API Reference

Full interactive docs at `http://localhost:8000/docs` after starting the backend.

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

### AI Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI conversation (SSE streaming) |

### Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/report/weekly` | Get/generate weekly report |
| POST | `/api/report/generate` | Force regenerate report |

---

## Deployment

### Self-host with Docker Compose

```bash
git clone https://github.com/Jackychen-12/wealthpilot.git
cd wealthpilot
cp backend/.env.example backend/.env
# Edit .env with your API keys
docker compose up --build -d
```

### Deploy to Railway (backend)

1. Fork this repo
2. Create new project on [Railway](https://railway.app)
3. Connect GitHub → select `wealthpilot`, root = `backend`
4. Add env vars: `ANTHROPIC_API_KEY`, `JWT_SECRET`
5. Deploy — get your backend URL

### Deploy frontend to Vercel / GitHub Pages

Frontend is a static Vite build. Set `VITE_API_URL` to your backend URL:

```bash
VITE_API_URL=https://your-backend.railway.app npm run build
```

---

## Project Structure

```
wealthpilot/
├── README.md
├── docker-compose.yml          # One-click start
├── nginx.conf                  # Frontend proxy config
├── Dockerfile.frontend         # Frontend container
├── package.json                # Frontend deps
├── vite.config.ts              # Vite + API proxy
├── src/                        # Frontend source
│   ├── api/                    # API layer (client, portfolio, market, analysis, chat)
│   ├── pages/                  # 9 screen components
│   ├── components/             # 12 shared UI components
│   ├── hooks/                  # Custom hooks (useTypingEffect)
│   ├── data/mock.ts            # Mock fallback data
│   ├── types.ts                # Shared types
│   └── utils/theme.ts          # Design tokens
└── backend/                    # Python backend
    ├── pyproject.toml
    ├── Dockerfile
    ├── .env.example
    └── src/wealthpilot/
        ├── main.py             # FastAPI entry
        ├── settings.py         # Config from env
        ├── models/             # SQLModel tables + Pydantic schemas
        ├── routes/             # 7 route modules, 24 endpoints
        ├── services/           # Market data, analysis engine, AI agent, auth
        └── storage/            # SQLite database
```

---

## Roadmap

- [x] Full-stack Agent architecture (FastAPI + React)
- [x] Real market data (AKShare + 东方财富 + 天天基金)
- [x] Claude AI chat with tool_use (5 real-time tools)
- [x] Portfolio management (CRUD + CSV import + OCR)
- [x] Advanced analytics (Sharpe, max drawdown, correlation)
- [x] User auth (JWT + multi-tenant)
- [x] Docker Compose deployment
- [x] Weekly report (LLM-generated)
- [ ] Push notifications (drawdown alerts)
- [ ] Backtesting and scenario analysis
- [ ] Risk tolerance profiling questionnaire
- [ ] Multi-asset class (stocks, bonds, ETFs, crypto)
- [ ] WeChat Mini Program version
- [ ] Dark mode
- [ ] i18n (English/Chinese toggle)
- [ ] Export reports as PDF

---

## Contributing

1. Fork the repo
2. Create feature branch: `git checkout -b feat/my-feature`
3. Commit: `git commit -m "feat: add my feature"`
4. Push: `git push origin feat/my-feature`
5. Open a Pull Request

---

## License

[MIT](LICENSE)
