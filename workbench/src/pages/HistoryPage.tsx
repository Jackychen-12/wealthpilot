import type React from 'react'
import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, useApi } from '../api'
import { AnswerMarkdown } from '../components/AnswerMarkdown'
import { CheckpointTable, ProposalList } from '../components/Checkpoints'
import { ExportButtons } from '../components/ExportButtons'
import { securityPath } from '../components/SecuritySearch'
import { Drawer, Tag } from '../components/kit'
import { DataState, Page, Section, Table, Td } from '../components/ui'
import { cn } from '../utils/cn'
import { DebateCard, PLAYBOOK, STATUS } from './ResearchPage'

const clip = (v: unknown) => {
  const s = typeof v === 'string' ? v : JSON.stringify(v, null, 1)
  return s.length > 4000 ? `${s.slice(0, 4000)}…` : s
}

const Detail: React.FC<{ id: number }> = ({ id }) => {
  const detail = useApi(() => api.researchDetail(id), [id])
  const [open, setOpen] = useState('')
  const d = detail.data
  const evidence = d?.meta.evidence ?? []
  const cite = (eid: string) => {
    setOpen(eid)
    setTimeout(() => document.getElementById(`ev-${eid}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60)
  }
  return (
    <DataState loading={detail.loading} error={detail.error} onRetry={detail.reload}>
      {d ? (
        <div className="flex flex-col gap-6">
          <div>
            <h3 className="text-lg font-semibold leading-snug text-ink">{d.question || '（问题未记录）'}</h3>
            <p className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px] text-steel">
              {STATUS[d.meta.status ?? ''] ? <Tag tone={STATUS[d.meta.status ?? ''].tone}>{STATUS[d.meta.status ?? ''].label}</Tag> : null}
              <span className="font-mono">{d.created_at.slice(0, 16).replace('T', ' ')}</span>
              {d.answer ? <ExportButtons className="ml-auto" item={{ question: d.question, answer: d.answer, when: d.created_at, evidence }} /> : null}
            </p>
          </div>
          {d.meta.debate ? <div className="mb-4"><DebateCard debate={d.meta.debate} /></div> : null}
          <AnswerMarkdown content={d.answer} onCite={cite} />
          {d.checkpoints?.length ? (
            <section>
              <p className="eyebrow mb-2">这次研究设下的验证点</p>
              <CheckpointTable items={d.checkpoints} showStock={new Set(d.checkpoints.map((c) => c.code)).size > 1} />
            </section>
          ) : null}
          {d.proposals?.length ? (
            <section>
              <p className="eyebrow mb-2">操作建议单</p>
              <ProposalList items={d.proposals} />
            </section>
          ) : null}
          {evidence.length ? (
            <section>
              <p className="eyebrow mb-2">当时取得的证据 · {evidence.length} 条</p>
              {evidence.map((e) => (
                <div key={e.id} id={`ev-${e.id}`} className={cn('rounded-sm', open === e.id && 'bg-tint-lavender/60')}>
                  <button type="button" onClick={() => setOpen((o) => (o === e.id ? '' : e.id))} className="flex w-full items-center gap-1.5 rounded-sm px-1 py-1 text-left text-[13px] hover:bg-hover">
                    <ChevronRight className={cn('h-3.5 w-3.5 shrink-0 text-stone transition-transform', open === e.id && 'rotate-90')} />
                    <code className="truncate font-mono text-[12.5px] text-charcoal">{e.tool}</code>
                    {e.status !== 'ok' ? <Tag tone="yellow" className="!py-0">无数据</Tag> : null}
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-stone">{e.id.slice(2, 6)}</span>
                  </button>
                  {open === e.id ? (
                    <div className="mb-1 ml-5 space-y-1 border-l border-hairline pl-3 text-xs text-slate">
                      <p><span className="text-steel">入参</span> <span className="break-all font-mono">{clip(e.input ?? {})}</span></p>
                      <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-surface p-2.5 font-mono text-[11.5px] leading-relaxed text-charcoal">{clip(e.output ?? '')}</pre>
                    </div>
                  ) : null}
                </div>
              ))}
            </section>
          ) : null}
          <p className="text-xs text-stone">这是当时的回答与数据，行情和财报可能已经更新。</p>
        </div>
      ) : null}
    </DataState>
  )
}

/** 研究记录：每一次问答连同当时的证据都存着，可以回看。 */
const HistoryPage: React.FC = () => {
  const history = useApi(api.researchHistory)
  const navigate = useNavigate()
  const selected = Number(useParams().id) || null
  const rows = history.data ?? []
  return (
    <Page title="研究记录" description="做过的每一次研究：回答、校验结论和当时取得的证据" terms={['证据编号', '验证点', '多空辩论']}>
      <Section title="全部记录" hint={rows.length ? `最近 ${rows.length} 条，新的在前` : undefined}>
        <DataState loading={history.loading} error={history.error} onRetry={history.reload}
          empty={rows.length === 0 ? '还没有研究记录。在 AI 研究里提问后，会自动存到这里。' : undefined}
          emptyAction={<Link to="/research" className="font-medium text-ink underline underline-offset-2">去提问</Link>}>
          <Table minWidth={760} head={[{ label: '问题' }, { label: '涉及证券' }, { label: '类型' }, { label: '结论' }, { label: '证据', right: true }, { label: '时间', right: true }]}>
            {rows.map((r) => (
              <tr key={r.id} className="cursor-pointer hover:bg-surface-soft" onClick={() => navigate(`/history/${r.id}`)}>
                <Td className="max-w-[340px]"><span className="line-clamp-2 font-medium text-ink">{r.question || '（问题未记录）'}</span></Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {r.securities.slice(0, 3).map((s) => (
                      <Link key={s.code} to={securityPath(s)} onClick={(e) => e.stopPropagation()} className="rounded-sm bg-tint-gray px-1.5 py-0.5 text-xs text-on-gray hover:brightness-95">{s.name}</Link>
                    ))}
                  </div>
                </Td>
                <Td>{PLAYBOOK[r.playbook] ?? '自由问答'}</Td>
                <Td>{STATUS[r.status] ? <Tag tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Tag> : '—'}</Td>
                <Td right num>{r.evidence_count}</Td>
                <Td right className="whitespace-nowrap font-mono text-xs text-stone">{r.created_at.slice(0, 16).replace('T', ' ')}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>
      <Drawer open={selected != null} onClose={() => navigate('/history')} title="研究记录" width="max-w-2xl">
        {selected != null ? <Detail key={selected} id={selected} /> : null}
      </Drawer>
    </Page>
  )
}

export default HistoryPage
