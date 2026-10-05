import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { api, type Security } from '../api'
import { cn } from '../utils/cn'
import { Spinner, Tag } from './kit'
import { ASSET } from './ui'

/** 证券详情页的地址：股票和 ETF 进个股页，基金进基金页。 */
export const securityPath = (s: { code: string; asset_type: string }) => (s.asset_type === 'fund' ? `/fund/${s.code}` : `/stock/${s.code}`)

/**
 * 按名称、简称或代码搜索证券。结果来自后端的证券解析（与 Agent 用的是同一个），
 * 所以这里能搜到的，AI 研究里也认得。
 */
export const SecuritySearch: React.FC<{
  onPick: (s: Security) => void
  placeholder?: string
  /** 全局搜索框：按 / 聚焦 */
  hotkey?: boolean
  className?: string
}> = ({ onPick, placeholder = '搜索股票、ETF、基金', hotkey, className }) => {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Security[] | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(0)
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const q = query.trim()
    if (!q) { setResults(null); setError(''); setLoading(false); return undefined }
    let alive = true
    setLoading(true)
    // 输入停顿后再查，免得每敲一个字都打一次接口
    const timer = setTimeout(() => {
      api.searchSecurities(q)
        .then((r) => { if (alive) { setResults(r); setError(''); setActive(0) } })
        .catch((e) => { if (alive) { setResults(null); setError(e instanceof Error ? e.message : '搜索失败') } })
        .finally(() => { if (alive) setLoading(false) })
    }, 250)
    return () => { alive = false; clearTimeout(timer) }
  }, [query])

  useEffect(() => {
    if (!hotkey) return undefined
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.key !== '/' || e.metaKey || e.ctrlKey || target?.closest('input, textarea, select, [contenteditable]')) return
      e.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [hotkey])

  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (!boxRef.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const pick = (s: Security) => {
    setQuery('')
    setOpen(false)
    inputRef.current?.blur()
    onPick(s)
  }
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur() }
    if (!results?.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % results.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + results.length) % results.length) }
    if (e.key === 'Enter') { e.preventDefault(); pick(results[active]) }
  }
  const showPanel = open && query.trim() !== ''

  return (
    <div ref={boxRef} className={cn('relative', className)}>
      <div className="flex h-8 items-center gap-2 rounded-md border border-hairline bg-canvas px-2.5 transition-colors focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
        {loading ? <Spinner className="h-3.5 w-3.5 text-stone" /> : <Search className="h-3.5 w-3.5 shrink-0 text-stone" />}
        <input ref={inputRef} value={query} placeholder={placeholder} aria-label={placeholder} role="combobox" aria-expanded={showPanel} aria-controls="security-results"
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={onKeyDown}
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-stone" />
        {hotkey && !query ? <kbd className="rounded-xs border border-hairline px-1 font-mono text-[11px] leading-4 text-stone">/</kbd> : null}
      </div>
      {showPanel ? (
        <div id="security-results" role="listbox" className="absolute left-0 right-0 top-9 z-30 min-w-[240px] overflow-hidden rounded-lg border border-hairline bg-canvas py-1 shadow-card">
          {error ? <p className="px-3 py-2 text-[13px] text-on-rose">{error}</p>
            : results == null ? <p className="px-3 py-2 text-[13px] text-steel">搜索中…</p>
            : results.length === 0 ? <p className="px-3 py-2 text-[13px] text-steel">没有找到「{query.trim()}」。试试完整名称或 6 位代码。</p>
            : results.map((s, i) => (
              <button key={`${s.asset_type}-${s.code}`} type="button" role="option" aria-selected={i === active}
                onMouseEnter={() => setActive(i)} onClick={() => pick(s)}
                className={cn('flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm', i === active && 'bg-hover')}>
                <span className="min-w-0 flex-1 truncate text-ink">{s.name}</span>
                <span className="font-mono text-xs text-stone">{s.code}</span>
                <Tag tone={s.asset_type === 'fund' ? 'blue' : s.asset_type === 'etf' ? 'green' : 'purple'} className="!py-0">{ASSET[s.asset_type] ?? s.asset_type}</Tag>
              </button>
            ))}
        </div>
      ) : null}
    </div>
  )
}
