import type React from 'react'
import { useEffect, useState } from 'react'
import { DEMO, type GlossaryTerm } from '../api'
import { loadGlossary } from '../components/Terms'
import { Callout } from '../components/kit'
import { Page, Section } from '../components/ui'

/** 名词解释：界面上出现的术语，各用一两句话说清楚是什么、怎么读。 */
const GlossaryPage: React.FC = () => {
  const [terms, setTerms] = useState<GlossaryTerm[]>([])
  const [q, setQ] = useState('')
  useEffect(() => { void loadGlossary().then(setTerms) }, [])
  const key = q.trim().toLowerCase()
  const shown = key ? terms.filter((t) => [t.term, ...t.aliases].some((w) => w.toLowerCase().includes(key))) : terms
  if (DEMO) return <Page title="名词解释" description="界面上出现的术语，各用一两句话说清楚"><Callout tone="info">在线演示没有后端，这一页在本地运行后可用。</Callout></Page>
  return (
    <Page title="名词解释" description="界面上用的是行情软件和研报里通行的叫法，方便对照和查找；每个词在这里都有一两句大白话">
      <Section title={`${shown.length} 个词条`} hint="终端里用 /glossary 封板率，手机里发“解释 封板率”，看到的是同一份">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="找一个词，或它的别的叫法" aria-label="搜索词条"
          className="mb-3 h-9 w-full max-w-md rounded-md border border-hairline bg-canvas px-3 text-sm text-ink placeholder:text-stone focus:border-primary focus:outline-none" />
        <dl className="divide-y divide-hairline-soft rounded-lg border border-hairline">
          {shown.map((t) => (
            <div key={t.term} className="grid gap-1 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt className="text-sm font-medium text-ink">{t.term}{t.aliases.length ? <span className="mt-0.5 block text-xs font-normal text-steel">也叫 {t.aliases.slice(0, 3).join('、')}</span> : null}</dt>
              <dd className="text-sm leading-relaxed text-charcoal">{t.plain}<span className="text-slate">{t.how}</span></dd>
            </div>
          ))}
        </dl>
        {key && !shown.length ? <p className="mt-2 text-[13px] text-steel">没有这个词条。</p> : null}
      </Section>
    </Page>
  )
}

export default GlossaryPage
