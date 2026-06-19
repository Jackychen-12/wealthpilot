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
      '🤖 多智能体 AI — Router + 市场/持仓/风险 3 大专业 Agent',
      '🔧 12 个工具 — 基金查询、净值分析、回撤计算、相关性评估...',
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
    subtitle: 'Router 智能分流 → 3 个专业 Agent',
    points: ['🧠 Router Agent', '📊 市场 Agent', '💼 持仓 Agent', '🛡️ 风险 Agent'],
    tech: ['Multi-Agent', 'tool_use', 'SSE Streaming'],
  },
}
