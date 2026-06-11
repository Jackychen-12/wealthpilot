import { useState, useCallback } from 'react'
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
import { Portfolio } from './pages/Portfolio'
import { Login } from './pages/Login'
import { RiskProfile } from './pages/RiskProfile'
import type { ScreenKey, PageProps } from './types'

const screens: Record<ScreenKey, React.ComponentType<PageProps>> = {
  home: Home,
  overview: Overview,
  attribution: Attribution,
  drawdown: Drawdown,
  health: Health,
  suggest: Suggestions,
  weekly: WeeklyReport,
  chat: Chat,
  portfolio: Portfolio,
  login: Login,
  'risk-profile': RiskProfile,
}

interface ScreenInfo {
  icon: string
  iconBg: string
  title: string
  subtitle: string
  points: string[]
  tech?: string[]
}

const screenInfoMap: Record<ScreenKey, ScreenInfo> = {
  home: {
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
  portfolio: {
    icon: '💼',
    iconBg: 'rgba(16,185,129,0.15)',
    title: '持仓管理',
    subtitle: '录入、导入、管理你的基金持仓数据',
    points: [
      '手动添加 — 输入基金代码 + 份额 + 成本净值',
      'CSV/Excel 批量导入 — 支持天天基金导出格式',
      '截图 OCR 识别 — Claude Vision 自动提取持仓',
      '实时净值 — 自动拉取最新净值计算盈亏',
    ],
    tech: ['AKShare', '天天基金 API', 'Claude Vision'],
  },
  overview: {
    icon: '📊',
    iconBg: 'rgba(37,99,235,0.15)',
    title: 'AI 持仓总览',
    subtitle: '一页看清你的组合表现',
    points: [
      '周收益 / 超额收益 / Sharpe 比率',
      '收益贡献 TOP & 拖累 TOP',
      '组合波动状态评估',
      '基于真实净值数据实时计算',
    ],
    tech: ['Sharpe Ratio', '60日净值', '实时估值'],
  },
  attribution: {
    icon: '📈',
    iconBg: 'rgba(14,165,233,0.15)',
    title: '收益归因分析',
    subtitle: '拆解收益来源，看清谁在赚钱',
    points: [
      '三维度归因 — 按基金 / 按行业 / 按资产类型',
      '配置效应 vs 选择效应拆解',
      '动态柱状图可视化',
      'AI 洞察文字解读',
    ],
  },
  drawdown: {
    icon: '📉',
    iconBg: 'rgba(239,68,68,0.15)',
    title: '回撤分析',
    subtitle: '了解下跌原因，评估恢复预期',
    points: [
      '三层归因 — 宏观 → 持仓 → 历史参照',
      '每只基金最大回撤 + 恢复天数',
      '高风险基金预警标注',
      '历史类似情况统计对比',
    ],
    tech: ['Max Drawdown', 'Recovery Days', '60日历史'],
  },
  health: {
    icon: '🩺',
    iconBg: 'rgba(16,185,129,0.15)',
    title: '组合健康度',
    subtitle: '5 维度为你的持仓做体检',
    points: [
      '收益表现 — 绝对收益率评分',
      '波动控制 — 日收益率标准差',
      '持仓分散度 — HHI 集中度指数',
      '风格匹配度 / 风险收益比（Sharpe）',
    ],
    tech: ['HHI Index', 'Pearson Correlation', 'Radar Chart'],
  },
  suggest: {
    icon: '💡',
    iconBg: 'rgba(245,158,11,0.15)',
    title: '后续关注建议',
    subtitle: '数据驱动的个性化建议',
    points: [
      '集中度过高预警（单只 > 40%）',
      '亏损基金止损提醒',
      '高相关性持仓分散建议',
      '权益仓位配比优化',
    ],
  },
  weekly: {
    icon: '📋',
    iconBg: 'rgba(37,99,235,0.15)',
    title: 'AI 周复盘报告',
    subtitle: 'Claude / DeepSeek LLM 自动生成结构化周报',
    points: [
      '本周收益变化汇总',
      '关键归因点自动提取',
      '下周关注事项预测',
      'AI 洞察分析（LLM 生成）',
    ],
    tech: ['Claude API', 'Prompt Engineering', 'JSON Schema'],
  },
  chat: {
    icon: '🤖',
    iconBg: 'rgba(124,58,237,0.15)',
    title: '多智能体 AI 对话',
    subtitle: 'Router 智能分流 → 3 个专业 Agent，12 个实时工具',
    points: [
      '🧠 Router Agent — 意图分类 + 关键词兜底',
      '📊 市场 Agent — 基金查询、净值走势、财经新闻（3 工具）',
      '💼 持仓 Agent — 总览、归因、健康度、建议（4 工具）',
      '🛡️ 风险 Agent — 回撤、相关性、收益率、对比（5 工具）',
    ],
    tech: ['Multi-Agent', 'tool_use', 'SSE Streaming', 'Claude & DeepSeek'],
  },
  login: {
    icon: '🔐',
    iconBg: 'rgba(37,99,235,0.15)',
    title: '账号管理',
    subtitle: '注册/登录后数据与账号绑定，支持多设备同步',
    points: [
      'JWT 认证 — 72 小时有效期',
      '多租户隔离 — 每个用户独立数据',
      'bcrypt 密码加密 — 安全存储',
      '免登录可用 — 跳过也能体验所有功能',
    ],
    tech: ['JWT', 'bcrypt', 'Multi-tenant'],
  },
  'risk-profile': {
    icon: '📝',
    iconBg: 'rgba(245,158,11,0.15)',
    title: '风险偏好评估',
    subtitle: '5 道问卷评估你的风险承受能力，匹配最适合的资产配置',
    points: [
      '投资经验 / 回撤承受 / 收益期望',
      '资金期限 / 最大亏损容忍度',
      '四类风险画像：保守/稳健/积极/激进',
      '配置建议：债券 vs 权益比例指导',
    ],
  },
}

const screenOrder: ScreenKey[] = [
  'home', 'portfolio', 'overview', 'attribution', 'drawdown',
  'health', 'suggest', 'weekly', 'chat', 'login', 'risk-profile',
]

export function App() {
  const [screen, setScreen] = useState<ScreenKey>('home')
  const [transitioning, setTransitioning] = useState(false)
  const [navDir, setNavDir] = useState<'forward' | 'back'>('forward')

  const navigate = useCallback((target: ScreenKey) => {
    if (target === screen) return
    const fromIdx = screenOrder.indexOf(screen)
    const toIdx = screenOrder.indexOf(target)
    setNavDir(toIdx >= fromIdx ? 'forward' : 'back')
    setTransitioning(true)
    setTimeout(() => {
      setScreen(target)
      setTransitioning(false)
    }, 150)
  }, [screen])

  const Comp = screens[screen]
  const info = screenInfoMap[screen]

  const transClass = transitioning
    ? 'screen-transition exit'
    : `screen-transition ${navDir === 'back' ? 'slide-back' : 'slide-forward'}`

  return (
    <>
      <div className="landing-layout">
        <div className="landing-info">
          <div className="landing-logo">
            <div className="landing-logo-icon" style={{ background: info.iconBg }}>
              <span style={{ fontSize: 24 }}>{info.icon}</span>
            </div>
            <span className="landing-logo-text">{info.title}</span>
          </div>

          <div className="landing-tagline">{info.subtitle}</div>

          <div className="landing-features">
            {info.points.map((p, i) => (
              <div key={i} className="landing-feature">
                <div style={{ fontSize: 14, lineHeight: 1.6 }}>{p}</div>
              </div>
            ))}
          </div>

          {info.tech && (
            <div className="landing-badges">
              {info.tech.map((t, i) => (
                <span key={i} className="landing-badge">{t}</span>
              ))}
            </div>
          )}
        </div>

        <PhoneFrame resetScroll={screen}>
          <div className={transClass}>
            <Comp go={navigate} />
          </div>
        </PhoneFrame>
      </div>

      <FloatingNav current={screen} onNav={navigate} />
    </>
  )
}
