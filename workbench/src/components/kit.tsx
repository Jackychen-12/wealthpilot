/** 通用组件：按 DESIGN.md 的 Notion 规范实现。按钮 8px 圆角、卡片 12px、标签用柔和色块。 */
import type React from 'react'
import { useEffect, useId } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '../utils/cn'

// ── 按钮 ────────────────────────────────────────────────
const BUTTON_VARIANT = {
  primary: 'bg-primary text-white hover:bg-primary-pressed disabled:bg-hairline disabled:text-stone',
  dark: 'bg-ink text-canvas hover:opacity-85 disabled:opacity-40',
  secondary: 'border border-hairline-strong bg-canvas text-ink hover:bg-surface disabled:opacity-50',
  ghost: 'text-slate hover:bg-hover hover:text-ink disabled:opacity-50',
  danger: 'text-up hover:bg-tint-rose disabled:opacity-50',
} as const
const BUTTON_SIZE = { xs: 'h-7 px-2 text-[13px] rounded-sm', sm: 'h-8 px-3 text-sm rounded-md', md: 'h-9 px-4 text-sm rounded-md' } as const

export const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BUTTON_VARIANT; size?: keyof typeof BUTTON_SIZE; loading?: boolean
}> = ({ variant = 'primary', size = 'md', loading, className, children, disabled, type = 'button', ...rest }) => (
  <button type={type} disabled={disabled || loading} aria-busy={loading || undefined}
    className={cn('inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap font-medium transition-colors', BUTTON_VARIANT[variant], BUTTON_SIZE[size], className)} {...rest}>
    {loading ? <Spinner className="h-3.5 w-3.5" /> : null}
    {children}
  </button>
)

export const Spinner: React.FC<{ className?: string }> = ({ className }) => (
  <span className={cn('inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70', className)} aria-hidden="true" />
)

// ── 标签（Notion 的属性标签）─────────────────────────────
const TAG_TONE = {
  gray: 'bg-tint-gray text-on-gray',
  purple: 'bg-tint-lavender text-on-lavender',
  orange: 'bg-tint-peach text-on-peach',
  green: 'bg-tint-mint text-on-mint',
  blue: 'bg-tint-sky text-on-sky',
  pink: 'bg-tint-rose text-on-rose',
  yellow: 'bg-tint-yellow text-on-yellow',
} as const
export type Tone = keyof typeof TAG_TONE

export const Tag: React.FC<{ tone?: Tone; className?: string; children: React.ReactNode }> = ({ tone = 'gray', className, children }) => (
  <span className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-sm px-2 py-0.5 text-xs font-medium leading-5', TAG_TONE[tone], className)}>{children}</span>
)

export const Dot: React.FC<{ tone?: 'green' | 'red' | 'orange' | 'purple' | 'gray'; pulse?: boolean; className?: string }> = ({ tone = 'gray', pulse, className }) => (
  <span aria-hidden="true" className={cn('inline-block h-2 w-2 shrink-0 rounded-full',
    { green: 'bg-down', red: 'bg-up', orange: 'bg-warning', purple: 'bg-primary', gray: 'bg-stone' }[tone], pulse && 'animate-pulse', className)} />
)

// ── 容器 ────────────────────────────────────────────────
export const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, ...rest }) => (
  <div className={cn('rounded-lg border border-hairline bg-canvas', className)} {...rest} />
)

/** 提示块：对应 Notion 的 Callout —— 一块有底色的说明。 */
const CALLOUT_TONE = { info: 'bg-tint-sky text-on-sky', warning: 'bg-tint-yellow text-on-yellow', danger: 'bg-tint-rose text-on-rose', success: 'bg-tint-mint text-on-mint', neutral: 'bg-surface text-charcoal' } as const
export const Callout: React.FC<{ tone?: keyof typeof CALLOUT_TONE; title?: string; children: React.ReactNode; action?: React.ReactNode; className?: string }> = ({ tone = 'neutral', title, children, action, className }) => (
  <div role="status" className={cn('flex items-start justify-between gap-3 rounded-md px-4 py-3 text-sm', CALLOUT_TONE[tone], className)}>
    <div className="min-w-0">
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className="break-words">{children}</div>
    </div>
    {action}
  </div>
)

// ── 表单 ────────────────────────────────────────────────
const FIELD = 'h-10 w-full rounded-md border border-hairline-strong bg-canvas px-3 text-sm text-ink outline-none transition-shadow placeholder:text-stone focus:border-primary focus:ring-1 focus:ring-primary disabled:opacity-60'

export const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }> = ({ label, hint, id, className, ...rest }) => {
  const auto = useId()
  const fieldId = id ?? auto
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      {label ? <label htmlFor={fieldId} className="text-[13px] font-medium text-slate">{label}</label> : null}
      <input id={fieldId} className={cn(FIELD, className)} {...rest} />
      {hint ? <p className="text-xs text-steel">{hint}</p> : null}
    </div>
  )
}

export const Select: React.FC<{ id?: string; label?: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }> = ({ id, label, value, onChange, options }) => {
  const auto = useId()
  const fieldId = id ?? auto
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      {label ? <label htmlFor={fieldId} className="text-[13px] font-medium text-slate">{label}</label> : null}
      <select id={fieldId} value={value} onChange={(e) => onChange(e.target.value)} className={cn(FIELD, 'cursor-pointer pr-8')}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

/** 下划线式分段切换。 */
export const Segmented: React.FC<{ value: string; onChange: (v: string) => void; options: readonly (readonly [string, string])[] }> = ({ value, onChange, options }) => (
  <div className="flex gap-4" role="tablist">
    {options.map(([key, label]) => (
      <button key={key} type="button" role="tab" aria-selected={value === key} onClick={() => onChange(key)}
        className={cn('-mb-px border-b-2 pb-1.5 text-sm transition-colors', value === key ? 'border-ink font-medium text-ink' : 'border-transparent text-steel hover:text-ink')}>
        {label}
      </button>
    ))}
  </div>
)

// ── 浮层 ────────────────────────────────────────────────
const useEscape = (active: boolean, onClose: () => void) => {
  useEffect(() => {
    if (!active) return undefined
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, onClose])
}

export const Drawer: React.FC<{ open: boolean; onClose: () => void; title: string; children: React.ReactNode; side?: 'left' | 'right'; width?: string }> = ({ open, onClose, title, children, side = 'right', width = 'max-w-md' }) => {
  useEscape(open, onClose)
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className={cn('relative flex h-full w-full flex-col bg-canvas shadow-modal', width, side === 'right' ? 'ml-auto border-l border-hairline' : 'mr-auto border-r border-hairline')}>
        <header className="flex items-center justify-between border-b border-hairline px-6 py-4">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <Button variant="ghost" size="xs" onClick={onClose} aria-label="关闭"><X className="h-4 w-4" /></Button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export const ConfirmDialog: React.FC<{ open: boolean; title: string; message: string; confirmText?: string; onConfirm: () => void; onCancel: () => void }> = ({ open, title, message, confirmText = '确认', onConfirm, onCancel }) => {
  useEscape(open, onCancel)
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center p-4" role="alertdialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/30" onClick={onCancel} />
      <div className="relative w-full max-w-sm rounded-lg border border-hairline bg-canvas p-6 shadow-modal">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        <p className="mt-2 text-sm text-slate">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>取消</Button>
          <Button variant="dark" size="sm" onClick={onConfirm}>{confirmText}</Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
