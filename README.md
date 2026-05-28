# WealthPilot

**AI-Powered Investment Advisory Agent**

An intelligent investment advisory agent that provides AI-driven portfolio analysis, risk insights, and investment decision support. Built as a high-fidelity mobile interactive prototype.

## Features

- **Smart Portfolio Analysis** — AI-driven holdings overview, return attribution (by fund / industry / asset type), and performance tracking
- **Risk Insight Engine** — Three-layer drawdown attribution, portfolio health radar (5 dimensions), and risk alerts
- **AI Conversational Q&A** — Multi-turn dialogue based on portfolio review results for deep investment insights
- **Automated Weekly Reports** — Auto-generated weekly review reports with key attribution highlights

## Tech Stack

- **React 18** + **TypeScript** — Component-based architecture with type safety
- **Vite** — Fast build tooling and HMR
- **Custom CSS** — Hand-crafted mobile-first UI without heavy dependencies

## Getting Started

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
src/
├── components/     # Shared UI components (PhoneFrame, NavBar, Card, etc.)
├── pages/          # Screen components (Home, Overview, Attribution, etc.)
├── data/           # Mock data layer
├── utils/          # Theme constants
└── styles/         # Global stylesheet
```

## Screens

| Screen | Description |
|--------|-------------|
| Home | Market tracking, news feed, portfolio entry |
| Overview | Weekly portfolio summary with top contributors |
| Attribution | Return attribution by fund, industry, asset type |
| Drawdown | Three-layer drawdown analysis with historical comparison |
| Health | 5-dimension portfolio health radar |
| Suggestions | AI-generated follow-up recommendations |
| Weekly Report | Automated weekly review with key insights |
| Chat | Conversational AI Q&A for deep analysis |

## Roadmap

- [ ] Real market data API integration (Yahoo Finance / Alpha Vantage)
- [ ] LLM-powered conversational engine (Claude / GPT)
- [ ] User portfolio input and persistence
- [ ] Multi-asset class support (stocks, bonds, crypto, commodities)
- [ ] Backtesting and scenario analysis module
- [ ] Risk tolerance profiling
- [ ] i18n (English / Chinese)

## License

MIT
