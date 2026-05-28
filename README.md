<p align="center">
  <img src="public/favicon.svg" width="64" height="64" alt="WealthPilot" />
</p>

<h1 align="center">WealthPilot</h1>

<p align="center">
  <strong>AI-Powered Investment Advisory Agent</strong><br/>
  <sub>智能投顾 Agent — 基于 AI 的持仓分析、风险洞察与投资决策辅助</sub>
</p>

<p align="center">
  <a href="https://keyuchen-del.github.io/wealthpilot/">Live Demo</a> &nbsp;|&nbsp;
  <a href="#features">Features</a> &nbsp;|&nbsp;
  <a href="#architecture">Architecture</a> &nbsp;|&nbsp;
  <a href="#getting-started">Getting Started</a> &nbsp;|&nbsp;
  <a href="#roadmap">Roadmap</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" alt="React 18" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white" alt="Vite" />
  <img src="https://github.com/keyuchen-del/wealthpilot/actions/workflows/deploy.yml/badge.svg" alt="Deploy" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</p>

---

## What is WealthPilot?

WealthPilot is an intelligent investment advisory agent that provides AI-driven portfolio analysis, risk insights, and investment decision support. Built as a high-fidelity mobile interactive prototype with a landing showcase.

> **Status:** Interactive prototype with mock data. Real API integration and LLM conversational engine are on the roadmap.

## Features

| Module | Description |
|--------|-------------|
| **Smart Portfolio Analysis** | AI-driven holdings overview, return attribution (by fund / industry / asset type), and performance tracking |
| **Risk Insight Engine** | Three-layer drawdown attribution (macro → portfolio → historical), portfolio health radar (5 dimensions), risk alerts |
| **AI Conversational Q&A** | Multi-turn dialogue with typing effect, context-aware follow-ups, data table rendering |
| **Automated Weekly Reports** | Weekly review with key attribution highlights, calendar-based signals, actionable suggestions |
| **Market & News Tracking** | Multi-market indices (A-share, HK, US), sector-level news feed, watchlist tracker |

### Screens

```
Home ─────→ Overview ─────→ Attribution (by fund / industry / asset)
                │
                ├──→ Drawdown (3-layer analysis + historical comparison)
                │
                ├──→ Health (5-dimension radar + risk points)
                │
                ├──→ Suggestions (AI recommendations + watch signals)
                │
                ├──→ Weekly Report (auto-generated review)
                │
                └──→ Chat (multi-turn AI Q&A with typing effect)
```

## Architecture

```
src/
├── components/          # 12 shared UI components
│   ├── PhoneFrame       # Mobile simulator shell
│   ├── NavBar           # Navigation with back button
│   ├── Card             # Reusable card container
│   ├── MetricBox        # KPI metric display
│   ├── BarChart         # Animated horizontal bar chart
│   ├── RadarChart       # SVG radar chart (5 dimensions)
│   ├── AiInsight        # AI analysis callout
│   ├── ChatBubble       # AI/User chat bubbles
│   ├── Tag              # Colored label tag
│   ├── FloatingNav      # Bottom navigation bar
│   ├── ErrorBoundary    # Error fallback UI
│   └── ...              # QuickPills, FollowUpBar, Disclaimer
│
├── pages/               # 8 screen components
│   ├── Home             # Market tracking + news + entry
│   ├── Overview         # Portfolio summary + module grid
│   ├── Attribution      # Return attribution with tab switching
│   ├── Drawdown         # 3-layer drawdown analysis
│   ├── Health           # Radar chart + dimension details
│   ├── Suggestions      # AI recommendations + signals
│   ├── WeeklyReport     # Automated weekly review
│   └── Chat             # AI conversation with typing effect
│
├── hooks/               # Custom React hooks
│   └── useTypingEffect  # Character-by-character typing animation
│
├── data/mock.ts         # Centralized mock data layer
├── types.ts             # Shared TypeScript types
├── utils/theme.ts       # Design token constants
└── styles/global.css    # Global stylesheet + animations
```

### Design Decisions

- **Single HTML entry** — Vite transforms it; no router needed since screens are state-driven
- **Typed page navigation** — `ScreenKey` union type ensures compile-time safety for all navigation
- **CSS-only animations** — Page transitions, bar chart growth, radar polygon scale, typing cursor — no animation library needed
- **Mock data layer** — All data is centralized in `data/mock.ts`, ready to swap for real API calls
- **Error boundary** — Catches rendering errors with a user-friendly fallback

## Getting Started

```bash
# Clone
git clone https://github.com/keyuchen-del/wealthpilot.git
cd wealthpilot

# Install
npm install

# Dev server (http://localhost:5173/wealthpilot/)
npm run dev

# Production build
npm run build

# Preview build
npm run preview
```

### Requirements

- Node.js 18+
- npm 9+

## Roadmap

- [ ] Real market data API integration (Yahoo Finance / Alpha Vantage)
- [ ] LLM-powered conversational engine (Claude API / OpenAI)
- [ ] User portfolio input with localStorage persistence
- [ ] Multi-asset class support (stocks, bonds, ETFs, crypto)
- [ ] Backtesting and scenario analysis module
- [ ] Risk tolerance profiling questionnaire
- [ ] i18n support (English / Chinese)
- [ ] Dark mode for in-app UI
- [ ] PWA support (offline access)
- [ ] Export reports as PDF

## License

[MIT](LICENSE)
