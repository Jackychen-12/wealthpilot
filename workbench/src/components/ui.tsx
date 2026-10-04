/** 页面级积木：页面框架、小节、指标、数据状态、数据表。 */
import type React from 'react'
import { cn } from '../utils/cn'
import { Button, Spinner } from './kit'

// A 股习惯：红涨绿跌
export const signClass = (v: number | null | undefined) => (v == null || v === 0 ? 'text-ink' : v > 0 ? 'text-up' : 'text-down')
export const yuan = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
export const signed = (v: number | null | undefined, digits = 2, suffix = '') =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`

export const CATEGORY: Record<string, string> = { equity: '权益', bond: '债券', money: '货币', hybrid: '混合' }
export const ASSET: Record<string, string> = { fund: '基金', stock: '股票', etf: 'ETF', crypto: '加密货币' }

/** 页面框架：像一页文档 —— 大标题、一句说明，下面是内容。 */
export const Page: React.FC<{ title: string; description: string; actions?: React.ReactNode; children: React.ReactNode }> = ({ title, description, actions, children }) => (
  <div className="mx-auto w-full max-w-[1120px] px-6 pb-16 pt-10 md:px-10">
    <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <h1 className="text-[32px] font-semibold leading-tight tracking-[-0.5px] text-ink">{title}</h1>
        <p className="mt-1.5 text-base text-steel">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
    <div className="flex flex-col gap-10">{children}</div>
  </div>
)

/** 小节：标题 + 可选说明与操作，下面直接放内容。 */
export const Section: React.FC<{ title: string; hint?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string }> = ({ title, hint, actions, children, className }) => (
  <section className={cn('min-w-0', className)}>
    <div className="mb-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
      <div className="min-w-0">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {hint ? <p className="mt-0.5 text-[13px] text-steel">{hint}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
    {children}
  </section>
)

/** 加载 / 出错 / 空三种状态的统一呈现。 */
export const DataState: React.FC<{ loading?: boolean; error?: string; empty?: string; emptyAction?: React.ReactNode; onRetry?: () => void; children: React.ReactNode }> = ({ loading, error, empty, emptyAction, onRetry, children }) => {
  if (loading) return <div className="flex items-center gap-2 rounded-lg bg-surface-soft px-4 py-6 text-sm text-steel"><Spinner />加载中…</div>
  if (error) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-tint-rose px-4 py-4 text-sm text-on-rose">
        <span>{error}</span>
        {onRetry ? <Button size="xs" variant="secondary" onClick={onRetry}>重试</Button> : null}
      </div>
    )
  }
  if (empty) return <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-soft px-4 py-6 text-sm text-steel"><span>{empty}</span>{emptyAction}</div>
  return <>{children}</>
}

/** 一组指标：同一张卡片里用细线分隔，不是一排各自带框的小卡片。 */
export const Metrics: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="grid grid-cols-2 overflow-hidden rounded-lg border border-hairline bg-canvas lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none">{children}</div>
)
export const Metric: React.FC<{ label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: string }> = ({ label, value, hint, tone }) => (
  <div className="min-w-0 px-5 py-4 [box-shadow:0_0_0_0.5px_var(--hairline)]">
    <p className="text-[13px] text-steel">{label}</p>
    <p className={cn('mt-1 text-[26px] font-semibold leading-tight tracking-[-0.5px] tabular-nums', tone ?? 'text-ink')}>{value}</p>
    {hint ? <p className="mt-1 truncate text-[13px] text-steel">{hint}</p> : null}
  </div>
)

/** 数据表：外框 12px 圆角，行间细线。 */
export const Table: React.FC<{ head: { label: React.ReactNode; right?: boolean; className?: string }[]; children: React.ReactNode; minWidth?: number }> = ({ head, children, minWidth = 560 }) => (
  <div className="overflow-x-auto rounded-lg border border-hairline">
    <table className="db-table" style={{ minWidth }}>
      <thead><tr>{head.map((h, i) => <th key={i} className={cn(h.right && 'r', h.className)}>{h.label}</th>)}</tr></thead>
      <tbody>{children}</tbody>
    </table>
  </div>
)
export const Td: React.FC<React.TdHTMLAttributes<HTMLTableCellElement> & { right?: boolean; num?: boolean }> = ({ className, right, num, ...rest }) => (
  <td className={cn(right && 'r', num && 'tabular-nums', className)} {...rest} />
)

/** 以零为中轴的横向条：盈利向右（红），亏损向左（绿）。 */
export const DivergingBar: React.FC<{ value: number; max: number }> = ({ value, max }) => {
  const width = max > 0 ? Math.min(50, (Math.abs(value) / max) * 50) : 0
  return (
    <div className="relative h-2 min-w-[120px] rounded-full bg-surface" aria-hidden="true">
      <span className="absolute inset-y-[-3px] left-1/2 w-px bg-hairline-strong" />
      <span className={cn('absolute inset-y-0 rounded-full', value >= 0 ? 'bg-up' : 'bg-down')}
        style={value >= 0 ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }} />
    </div>
  )
}
