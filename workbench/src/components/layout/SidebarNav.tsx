import type React from 'react'
import { useState } from 'react'
import { LogIn, LogOut, Moon, Sun } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { DEMO } from '../../api'
import { cn } from '../../utils/cn'
import { Dot } from '../kit'
import { SecuritySearch, securityPath } from '../SecuritySearch'
import { SECTIONS, SETTINGS, sectionOf, type SectionDef } from './sections'

export type SidebarNavProps = {
  onNavigate?: () => void
  backend: 'ok' | 'down' | 'checking'
  username: string
  alertCount: number
  researchBusy: boolean
  onLogin: () => void
  onLogout: () => void
}

const ITEM = 'flex h-8 w-full items-center gap-2.5 rounded-sm px-2.5 text-sm text-slate transition-colors hover:bg-hover hover:text-ink'

export const SidebarNav: React.FC<SidebarNavProps> = ({ onNavigate, backend, username, alertCount, researchBusy, onLogin, onLogout }) => {
  const navigate = useNavigate()
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  const { pathname } = useLocation()
  const here = sectionOf(pathname)?.key
  const toggleTheme = () => {
    const next = !dark
    document.documentElement.classList.toggle('dark', next)
    try { localStorage.setItem('wp_theme', next ? 'dark' : 'light') } catch { /* 存不了就只在本次生效 */ }
    setDark(next)
  }
  const entry = ({ key, to, label, icon: Icon }: SectionDef) => (
    <Link key={key} to={to} onClick={onNavigate} aria-current={here === key ? 'page' : undefined}
      className={cn(ITEM, 'h-9', here === key && 'bg-hover font-medium text-ink')}>
      <Icon className="h-4 w-4 shrink-0" />
      <span className="truncate">{label}</span>
      {key === 'research' && researchBusy ? <Dot tone="purple" pulse className="ml-auto" /> : null}
      {key === 'holdings' && alertCount > 0 ? <span className="ml-auto rounded-xs bg-tint-rose px-1.5 text-xs font-medium tabular-nums text-on-rose" title="风险体检里有预警">{alertCount}</span> : null}
    </Link>
  )

  return (
    <div className="flex h-full flex-col px-2 py-3">
      <div className="mb-2 flex items-center gap-2.5 px-2.5 py-1.5">
        <div className="flex h-6 w-6 items-center justify-center rounded-sm bg-ink text-xs font-semibold text-canvas">W</div>
        <span className="truncate text-sm font-semibold text-ink">WealthPilot</span>
      </div>

      <SecuritySearch hotkey className="mx-1 mb-3" onPick={(sec) => { navigate(securityPath(sec)); onNavigate?.() }} />

      {/* 只有五件事。其余页面是它们下面的页签，见 sections.tsx */}
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto" aria-label="主导航">
        {SECTIONS.map(entry)}
      </nav>

      <div className="mt-3 flex flex-col gap-0.5 border-t border-hairline pt-3">
        {entry(SETTINGS)}
        <button type="button" onClick={toggleTheme} className={ITEM}>
          {dark ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
          <span>{dark ? '浅色模式' : '深色模式'}</span>
        </button>
        {DEMO ? null : username ? (
          <button type="button" onClick={onLogout} className={ITEM}><LogOut className="h-4 w-4 shrink-0" /><span className="truncate">退出 {username}</span></button>
        ) : (
          <button type="button" onClick={onLogin} className={ITEM}><LogIn className="h-4 w-4 shrink-0" /><span className="truncate">登录</span><span className="ml-auto text-xs text-stone">匿名档</span></button>
        )}
        <div className="flex items-center gap-2.5 px-2.5 py-1 text-[13px] text-steel">
          <Dot tone={backend === 'ok' ? 'green' : backend === 'down' ? 'red' : 'gray'} pulse={backend === 'checking'} />
          {DEMO ? '演示数据（回放）' : backend === 'ok' ? '后端已连接' : backend === 'down' ? '后端未连接' : '连接中'}
        </div>
      </div>
    </div>
  )
}
