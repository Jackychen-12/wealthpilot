import type React from 'react'
import { useState } from 'react'
import { BriefcaseBusiness, Cable, CandlestickChart, ChevronRight, ClipboardCheck, FileText, History, Home, Layers, LayoutDashboard, ListFilter, LogIn, LogOut, MessageSquareText, Moon, NotebookText, Scale, Search, ShieldCheck, Star, Sun, UserRoundCog, Zap } from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { DEMO } from '../../api'
import { cn } from '../../utils/cn'
import { Dot } from '../kit'
import { SecuritySearch, securityPath } from '../SecuritySearch'

export type SidebarNavProps = {
  onNavigate?: () => void
  backend: 'ok' | 'down' | 'checking'
  username: string
  alertCount: number
  researchBusy: boolean
  onLogin: () => void
  onLogout: () => void
}

type NavItem = { to: string; label: string; icon: React.ComponentType<{ className?: string }>; exact?: boolean; badge?: 'alerts' | 'busy' }

// 股票在前：先看市场和研究，再看自己的组合，最后是工具与设置
const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  { label: '', items: [{ to: '/', label: '今日', icon: Home, exact: true }] },
  { label: '研究', items: [
    { to: '/research', label: 'AI 研究', icon: MessageSquareText, badge: 'busy' },
    { to: '/stock', label: '个股', icon: CandlestickChart },
    { to: '/screener', label: '选股器', icon: ListFilter },
    { to: '/watchlist', label: '自选股', icon: Star },
    { to: '/review', label: '验证与复盘', icon: ClipboardCheck },
  ] },
  { label: '组合', items: [
    { to: '/holdings', label: '持仓', icon: BriefcaseBusiness },
    { to: '/overview', label: '组合总览', icon: LayoutDashboard },
    { to: '/lookthrough', label: '持仓穿透', icon: Layers },
  ] },
  { label: '风险', items: [
    { to: '/risk', label: '风险体检', icon: ShieldCheck, badge: 'alerts' },
    { to: '/stress', label: '压力测试', icon: Zap },
    { to: '/rebalance', label: '调仓推演', icon: Scale },
  ] },
  { label: '工具', items: [
    { to: '/backtest', label: '规则回测', icon: History },
    { to: '/fund', label: '基金查询', icon: Search },
  ] },
  { label: '设置', items: [
    { to: '/profile', label: '风险画像', icon: UserRoundCog },
    { to: '/connectors', label: '数据连接', icon: Cable },
    { to: '/report', label: '周报', icon: FileText },
    { to: '/history', label: '研究记录', icon: NotebookText },
  ] },
]

const COLLAPSED_KEY = 'wp_nav_collapsed'
const readCollapsed = (): string[] => {
  try { return JSON.parse(localStorage.getItem(COLLAPSED_KEY) || '[]') as string[] } catch { return [] }
}

const ITEM = 'flex h-8 w-full items-center gap-2.5 rounded-sm px-2.5 text-sm text-slate transition-colors hover:bg-hover hover:text-ink'

export const SidebarNav: React.FC<SidebarNavProps> = ({ onNavigate, backend, username, alertCount, researchBusy, onLogin, onLogout }) => {
  const navigate = useNavigate()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState<string[]>(readCollapsed)
  const toggleGroup = (label: string) => setCollapsed((prev) => {
    const next = prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]
    try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next)) } catch { /* 存不了就只在本次生效 */ }
    return next
  })
  const isCurrent = (to: string) => pathname === to || pathname.startsWith(`${to}/`)
  const toggleTheme = () => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    try { localStorage.setItem('wp_theme', next ? 'dark' : 'light') } catch { /* 存不了就只在本次生效 */ }
    setDark(next)
  }

  return (
    <div className="flex h-full flex-col px-2 py-3">
      <div className="mb-2 flex items-center gap-2.5 px-2.5 py-1.5">
        <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-ink text-xs font-semibold text-canvas">W</div>
        <span className="truncate text-sm font-semibold text-ink">WealthPilot</span>
      </div>

      <SecuritySearch hotkey className="mx-1 mb-3" onPick={(sec) => { navigate(securityPath(sec)); onNavigate?.() }} />

      <nav className="flex flex-1 flex-col gap-3 overflow-y-auto" aria-label="主导航">
        {NAV_GROUPS.map((group) => {
          const folded = collapsed.includes(group.label)
          // 收起后仍然留着当前所在的那一项，免得不知道自己在哪
          const items = folded ? group.items.filter((i) => isCurrent(i.to)) : group.items
          const hasAlert = folded && alertCount > 0 && group.items.some((i) => i.badge === 'alerts' && !isCurrent(i.to))
          const hasBusy = folded && researchBusy && group.items.some((i) => i.badge === 'busy' && !isCurrent(i.to))
          return (
            <div key={group.label} className="flex flex-col gap-0.5">
              {group.label ? (
                <button type="button" onClick={() => toggleGroup(group.label)} aria-expanded={!folded}
                  className="group flex h-6 items-center gap-1 rounded-sm px-2.5 text-left text-xs font-medium text-stone transition-colors hover:bg-hover hover:text-slate">
                  <span>{group.label}</span>
                  {hasAlert ? <Dot tone="red" className="h-1.5 w-1.5" /> : null}
                  {hasBusy ? <Dot tone="purple" pulse className="h-1.5 w-1.5" /> : null}
                  <ChevronRight className={cn('ml-auto h-3.5 w-3.5 opacity-0 transition-all group-hover:opacity-100 group-focus-visible:opacity-100', !folded && 'rotate-90', folded && 'opacity-100')} />
                </button>
              ) : null}
              {items.map(({ to, label, icon: Icon, exact, badge }) => (
                <NavLink key={to} to={to} end={exact} onClick={onNavigate}
                  className={({ isActive }) => cn(ITEM, isActive && 'bg-hover font-medium text-ink')}>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{label}</span>
                  {badge === 'alerts' && alertCount > 0 ? <span className="ml-auto rounded-xs bg-tint-rose px-1.5 text-xs font-medium tabular-nums text-on-rose">{alertCount}</span> : null}
                  {badge === 'busy' && researchBusy ? <Dot tone="purple" pulse className="ml-auto" /> : null}
                </NavLink>
              ))}
            </div>
          )
        })}
      </nav>

      <div className="mt-3 flex flex-col gap-0.5 border-t border-hairline pt-3">
        <div className="flex items-center gap-2.5 px-2.5 py-1 text-[13px] text-steel">
          <Dot tone={backend === 'ok' ? 'green' : backend === 'down' ? 'red' : 'gray'} pulse={backend === 'checking'} />
          {DEMO ? '演示数据（回放）' : backend === 'ok' ? '后端已连接' : backend === 'down' ? '后端未连接' : '连接中'}
        </div>
        <button type="button" onClick={toggleTheme} className={ITEM}>
          {dark ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
          <span>{dark ? '浅色模式' : '深色模式'}</span>
        </button>
        {DEMO ? null : username ? (
          <button type="button" onClick={onLogout} className={ITEM}><LogOut className="h-4 w-4 shrink-0" /><span className="truncate">退出 {username}</span></button>
        ) : (
          <button type="button" onClick={onLogin} className={ITEM}><LogIn className="h-4 w-4 shrink-0" /><span className="truncate">登录</span><span className="ml-auto text-xs text-stone">匿名档</span></button>
        )}
      </div>
    </div>
  )
}
