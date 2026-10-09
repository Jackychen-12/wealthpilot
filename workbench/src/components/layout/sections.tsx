import type React from 'react'
import { BriefcaseBusiness, CandlestickChart, ClipboardCheck, Home, MessageSquareText, Settings } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '../../utils/cn'

/**
 * 整个工作台只有五件事：今日、研究、市场、持仓、回顾（外加设置）。
 * 其余页面都是这五件事下面的页签 —— 路径不变，只是不再各占一个侧栏入口。
 * 这张表是唯一的出处：侧栏、页签条、当前在哪，都从这里算。
 */
type Leaf = { to: string; label: string; also?: string[] }
type Tab = Leaf & { sub?: Leaf[] }
export type SectionDef = { key: string; label: string; to: string; icon: React.ComponentType<{ className?: string }>; tabs: Tab[]; detail?: string[] }

export const SECTIONS: SectionDef[] = [
  { key: 'today', label: '今日', to: '/', icon: Home, tabs: [] },
  // detail：个股、基金的详情页算在「研究」里，但它们是具体的一只，不显示页签
  { key: 'research', label: '研究', to: '/research', icon: MessageSquareText, detail: ['/stock', '/fund'], tabs: [
    { to: '/research', label: '提问' },
    { to: '/history', label: '研究记录' },
  ] },
  { key: 'market', label: '市场', to: '/market', icon: CandlestickChart, tabs: [
    { to: '/market', label: '大盘' },
    { to: '/macro', label: '宏观' },
    { to: '/screener', label: '选股器' },
  ] },
  { key: 'holdings', label: '持仓', to: '/holdings', icon: BriefcaseBusiness, tabs: [
    { to: '/holdings', label: '持仓', also: ['/overview'] },
    { to: '/watchlist', label: '自选股' },
    { to: '/risk', label: '组合分析', sub: [
      { to: '/risk', label: '风险体检' },
      { to: '/lookthrough', label: '持仓穿透' },
      { to: '/stress', label: '压力测试' },
      { to: '/rebalance', label: '调仓推演' },
      { to: '/backtest', label: '规则回测' },
    ] },
    { to: '/broker', label: '模拟盘' },
  ] },
  { key: 'review', label: '回顾', to: '/review', icon: ClipboardCheck, tabs: [
    { to: '/review', label: '验证与回溯' },
    { to: '/trades', label: '交易行为诊断' },
    { to: '/report', label: '周报' },
  ] },
]
export const SETTINGS: SectionDef = { key: 'settings', label: '设置', to: '/settings', icon: Settings, tabs: [
  { to: '/settings', label: '基本设置' },
  { to: '/skills', label: '研究方法' },
  { to: '/memory', label: '记忆' },
  { to: '/profile', label: '风险画像' },
  { to: '/automations', label: '自动任务' },
  { to: '/connectors', label: '数据连接' },
  { to: '/audit', label: '审计日志' },
  { to: '/glossary', label: '名词解释' },
] }

const under = (pathname: string, to: string) => (to === '/' ? pathname === '/' : pathname === to || pathname.startsWith(`${to}/`))
const leafActive = (pathname: string, leaf: Leaf) => under(pathname, leaf.to) || (leaf.also ?? []).some((p) => under(pathname, p))
const tabActive = (pathname: string, tab: Tab) => leafActive(pathname, tab) || (tab.sub ?? []).some((s) => leafActive(pathname, s))

/** 这个路径属于哪一件事。 */
export const sectionOf = (pathname: string): SectionDef | null =>
  [...SECTIONS, SETTINGS].find((s) => under(pathname, s.to) || s.tabs.some((t) => tabActive(pathname, t)) || (s.detail ?? []).some((p) => under(pathname, p))) ?? null

const TAB = '-mb-px whitespace-nowrap border-b-2 px-0.5 py-2.5 text-sm transition-colors'

/** 页签条：当前这件事下面有哪几页。固定在内容上方，不跟着滚动。 */
export const SectionTabs: React.FC<{ alertCount?: number }> = ({ alertCount = 0 }) => {
  const { pathname } = useLocation()
  const section = sectionOf(pathname)
  if (!section || !section.tabs.some((t) => tabActive(pathname, t))) return null     // 首页、个股详情：没有页签
  const current = section.tabs.find((t) => tabActive(pathname, t))
  return (
    <div className="border-b border-hairline bg-canvas">
      <nav aria-label={`${section.label}下的页面`} className="mx-auto flex w-full max-w-[1120px] gap-5 overflow-x-auto px-6 [scrollbar-width:none] md:px-10 [&::-webkit-scrollbar]:hidden">
        {section.tabs.map((t) => {
          const active = t === current
          return (
            <Link key={t.to} to={t.to} aria-current={active ? 'page' : undefined}
              className={cn(TAB, active ? 'border-ink font-medium text-ink' : 'border-transparent text-steel hover:text-ink')}>
              {t.label}
              {t.to === '/risk' && alertCount > 0 ? <span className="ml-1.5 rounded-xs bg-tint-rose px-1.5 text-xs font-medium tabular-nums text-on-rose">{alertCount}</span> : null}
            </Link>
          )
        })}
      </nav>
      {current?.sub ? (
        <nav aria-label={`${current.label}里的工具`} className="mx-auto flex w-full max-w-[1120px] gap-1.5 overflow-x-auto px-6 pb-2.5 pt-2.5 [scrollbar-width:none] md:px-10 [&::-webkit-scrollbar]:hidden">
          {current.sub.map((s) => (
            <Link key={s.to} to={s.to} aria-current={leafActive(pathname, s) ? 'page' : undefined}
              className={cn('whitespace-nowrap rounded-full px-3 py-1 text-[13px] transition-colors', leafActive(pathname, s) ? 'bg-ink text-canvas' : 'bg-surface text-slate hover:bg-hover hover:text-ink')}>
              {s.label}
            </Link>
          ))}
        </nav>
      ) : null}
    </div>
  )
}
