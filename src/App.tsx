import { useState } from 'react'
import { PhoneFrame } from './components/PhoneFrame'
import { FloatingNav } from './components/FloatingNav'
import { Home } from './pages/Home'
import { Overview } from './pages/Overview'
import { Attribution } from './pages/Attribution'
import { Drawdown } from './pages/Drawdown'
import { Health } from './pages/Health'
import { Suggestions } from './pages/Suggestions'
import { WeeklyReport } from './pages/WeeklyReport'
import { Chat } from './pages/Chat'

const screens: Record<string, React.ComponentType<{ go: (k: string) => void }>> = {
  home: Home,
  overview: Overview,
  attribution: Attribution,
  drawdown: Drawdown,
  health: Health,
  suggest: Suggestions,
  weekly: WeeklyReport,
  chat: Chat,
}

const features = [
  {
    icon: '📊',
    bg: 'rgba(37,99,235,0.15)',
    title: '智能持仓分析',
    desc: 'AI 驱动的持仓总览、收益归因与绩效追踪',
  },
  {
    icon: '🛡️',
    bg: 'rgba(239,68,68,0.15)',
    title: '风险洞察引擎',
    desc: '三层回撤归因、组合健康度雷达、风险预警',
  },
  {
    icon: '💬',
    bg: 'rgba(14,165,233,0.15)',
    title: 'AI 对话追问',
    desc: '基于复盘结果的多轮对话，深度挖掘投资洞察',
  },
  {
    icon: '📋',
    bg: 'rgba(16,185,129,0.15)',
    title: '自动化周报',
    desc: '每周自动生成复盘报告，关键归因点一目了然',
  },
]

const badges = ['React', 'TypeScript', 'Vite', 'AI Agent', 'Portfolio Analysis', 'Risk Engine']

export function App() {
  const [screen, setScreen] = useState('home')
  const Comp = screens[screen]

  return (
    <>
      <div className="landing-layout">
        <div className="landing-info">
          <div className="landing-logo">
            <div className="landing-logo-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="#fff"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="landing-logo-text">WealthPilot</span>
          </div>

          <div className="landing-tagline">
            AI-Powered Investment Advisory Agent<br />
            智能投顾 Agent — 基于 AI 的持仓分析、风险洞察与投资决策辅助
          </div>

          <div className="landing-features">
            {features.map((f, i) => (
              <div key={i} className="landing-feature">
                <div className="landing-feature-icon" style={{ background: f.bg }}>
                  {f.icon}
                </div>
                <div>
                  <div className="landing-feature-title">{f.title}</div>
                  <div className="landing-feature-desc">{f.desc}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="landing-badges">
            {badges.map((b, i) => (
              <span key={i} className="landing-badge">{b}</span>
            ))}
          </div>
        </div>

        <PhoneFrame resetScroll={screen}>
          <Comp go={setScreen} />
        </PhoneFrame>
      </div>

      <FloatingNav current={screen} onNav={setScreen} />
    </>
  )
}
