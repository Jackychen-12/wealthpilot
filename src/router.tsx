import { createHashRouter } from 'react-router-dom'
import { Home } from './pages/Home'
import { Overview } from './pages/Overview'
import { Attribution } from './pages/Attribution'
import { Drawdown } from './pages/Drawdown'
import { Health } from './pages/Health'
import { Suggestions } from './pages/Suggestions'
import { WeeklyReport } from './pages/WeeklyReport'
import { Chat } from './pages/Chat'
import { Portfolio } from './pages/Portfolio'
import { Login } from './pages/Login'
import { RiskProfile } from './pages/RiskProfile'
import { AppLayout } from './AppLayout'

export const router = createHashRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <Home /> },
      { path: '/portfolio', element: <Portfolio /> },
      { path: '/overview', element: <Overview /> },
      { path: '/attribution', element: <Attribution /> },
      { path: '/drawdown', element: <Drawdown /> },
      { path: '/health', element: <Health /> },
      { path: '/suggestions', element: <Suggestions /> },
      { path: '/weekly', element: <WeeklyReport /> },
      { path: '/chat', element: <Chat /> },
      { path: '/login', element: <Login /> },
      { path: '/risk-profile', element: <RiskProfile /> },
    ],
  },
])

export const ROUTE_META: Record<string, { icon: string; iconBg: string; title: string; subtitle: string; points: string[]; tech?: string[] }> = {
  '/': {
    icon: '🏠',
    iconBg: 'rgba(37,99,235,0.15)',
    title: 'WealthPilot',
    subtitle: 'AI-Powered Investment Advisory Agent\n多智能体 Agent · 支持 Claude & DeepSeek',
    points: [
      '🤖 多智能体 AI — Planner 拆任务，市场/持仓/风险/量化 4 个 Agent 并行取证',
      '🔧 19 个工具 — 行情、归因、回撤、持仓穿透、规则回测...',
      '🌐 多模型支持 — Claude & DeepSeek，.env 一行切换',
      '📋 自动化周报 — LLM 生成结构化复盘报告',
    ],
    tech: ['React 18', 'TypeScript', 'FastAPI', 'Claude AI', 'DeepSeek', 'AKShare'],
  },
  '/portfolio': {
    icon: '💼',
    iconBg: 'rgba(16,185,129,0.15)',
    title: '持仓管理',
    subtitle: '录入、导入、管理你的基金持仓数据',
    points: ['手动添加基金', 'CSV/Excel 批量导入', '截图 OCR 识别', '实时净值计算盈亏'],
    tech: ['AKShare', '天天基金 API', 'Claude Vision'],
  },
  '/overview': {
    icon: '📊',
    iconBg: 'rgba(37,99,235,0.15)',
    title: 'AI 持仓总览',
    subtitle: '一页看清你的组合表现',
    points: ['周收益 / Sharpe 比率', '收益贡献 TOP', '组合波动评估', '实时数据'],
    tech: ['Sharpe Ratio', '60日净值'],
  },
  '/chat': {
    icon: '🤖',
    iconBg: 'rgba(124,58,237,0.15)',
    title: '多智能体 AI 对话',
    subtitle: '规划 → 并行取证 → 校验 → 发布，全程可见',
    points: ['🧭 Planner 拆解任务', '📊 市场 · 💼 持仓 · 🛡️ 风险 · 🔬 量化 并行取证', '🧐 Critic 双闸门：证据审核 + 回答校验', '🔎 点回答里的标签查看每个数字的出处'],
    tech: ['Multi-Agent', 'tool_use', 'SSE Streaming'],
  },
}
