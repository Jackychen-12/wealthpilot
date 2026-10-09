import type React from 'react'
import { useEffect, useState } from 'react'
import { api, type GlossaryTerm } from '../api'

// 词条只取一次，全站共用
let loaded: Promise<GlossaryTerm[]> | null = null
export const loadGlossary = (): Promise<GlossaryTerm[]> => {
  if (!loaded) loaded = api.glossary().catch(() => { loaded = null; return [] })
  return loaded
}

/** 一块内容下面的"这几个词是什么意思"：点一个词，就地展开一两句解释。用专业的叫法，但不要求先学会。 */
export const Terms: React.FC<{ words: string[]; className?: string }> = ({ words, className }) => {
  const [all, setAll] = useState<GlossaryTerm[]>([])
  const [open, setOpen] = useState('')
  useEffect(() => { let alive = true; void loadGlossary().then((t) => { if (alive) setAll(t) }); return () => { alive = false } }, [])
  const known = words.map((w) => all.find((t) => t.term === w)).filter((t): t is GlossaryTerm => Boolean(t))
  if (!known.length) return null
  const shown = known.find((t) => t.term === open)
  return (
    <div className={className}>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-steel">
        <span>看不懂的词：</span>
        {known.map((t) => (
          <button key={t.term} type="button" title={`${t.plain}${t.how}`} aria-expanded={open === t.term} onClick={() => setOpen(open === t.term ? '' : t.term)}
            className={`underline decoration-dotted underline-offset-4 transition-colors hover:text-ink ${open === t.term ? 'text-ink' : ''}`}>{t.term}</button>
        ))}
      </p>
      {shown ? <p className="mt-1.5 rounded-md bg-surface-soft px-3 py-2 text-[13px] leading-relaxed text-charcoal"><b className="text-ink">{shown.term}</b>：{shown.plain}{shown.how}</p> : null}
    </div>
  )
}
