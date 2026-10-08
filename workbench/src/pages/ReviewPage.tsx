import type React from 'react'
import { useState } from 'react'
import { RefreshCw, Sparkles } from 'lucide-react'
import { DEMO, api, useApi, type Checkpoint } from '../api'
import { AskAi } from '../components/AskAi'
import { CP_STATUS, CheckpointTable, ProposalList } from '../components/Checkpoints'
import { Button, Callout, ConfirmDialog, Segmented } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td } from '../components/ui'
import { StanceSection } from './DepthSections'

const FILTERS = [['all', '全部'], ['pending', '待核对'], ['held', '成立'], ['broken', '被证伪']] as const
const rate = (v: number | null) => (v == null ? '—' : `${v}%`)

/**
 * 它记下的经验：判断落空时由程序照实记一条（不花钱）；攒够几条后可以让模型归纳一次规律（点了才调用）。
 * 这些会带进之后的研究，不想要的可以删。
 */
const Lessons: React.FC = () => {
  const list = useApi(api.lessons)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ tone: 'success' | 'danger' | 'neutral'; text: string } | null>(null)
  const rows = list.data ?? []
  const reflect = async () => {
    setBusy(true); setNote(null)
    try {
      const r = await api.reflect()
      setNote(r.added.length ? { tone: 'success', text: `归纳出 ${r.added.length} 条规律，已经记下。` } : { tone: 'neutral', text: '这次没有找到有两条以上记录支撑的规律，什么都没记。' })
      list.reload()
    } catch (e) {
      setNote({ tone: 'danger', text: e instanceof Error ? e.message : '没有归纳成' })
    } finally { setBusy(false) }
  }
  return (
    <Section title="它记下的经验" hint="判断落空时自动记一条；之后研究同一只股票会带上"
      actions={DEMO ? undefined : <Button size="sm" variant="secondary" loading={busy} onClick={() => void reflect()} title="把已核对的判断交给模型找规律。会调用一次模型"><Sparkles className="h-3.5 w-3.5" />让它归纳规律</Button>}>
      {note ? <Callout tone={note.tone} className="mb-3">{note.text}</Callout> : null}
      <DataState loading={list.loading} error={list.error} onRetry={list.reload}
        empty={rows.length === 0 ? '还没有。等有判断被证伪，这里会自动出现一条：当时怎么想的、实际是多少。' : undefined}>
        <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
          {rows.map((m) => (
            <li key={m.id} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
              <span className={`shrink-0 rounded-sm px-1.5 py-0.5 text-xs ${m.source === 'reflection' ? 'bg-tint-lavender text-ink' : 'bg-surface text-steel'}`}>{m.source === 'reflection' ? '规律' : '落空'}</span>
              <span className="min-w-0 flex-1 leading-relaxed text-charcoal">{m.content}</span>
              {DEMO ? null : <button type="button" onClick={() => void api.removeMemory(m.id).then(list.reload)} className="shrink-0 text-[13px] text-steel hover:text-ink">删掉</button>}
            </li>
          ))}
        </ul>
      </DataState>
    </Section>
  )
}

/** 验证与回溯：研究当时的判断，后来对不对。 */
const ReviewPage: React.FC = () => {
  const card = useApi(api.scorecard)
  const list = useApi(() => api.checkpoints())
  const proposals = useApi(api.proposals)
  const [filter, setFilter] = useState('all')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [removing, setRemoving] = useState<Checkpoint | null>(null)

  const reload = () => { card.reload(); list.reload() }
  const verify = async () => {
    setBusy(true); setMessage(null)
    try {
      const r = await api.verifyCheckpoints()
      setMessage({ tone: 'success', text: r.checked ? `核对出 ${r.checked} 条结果：成立 ${r.held}，被证伪 ${r.broken}` : '没有到核对时点的验证点：财务类要等下一期财报，估值和涨跌类要等到期日' })
      reload()
    } catch (e) {
      setMessage({ tone: 'danger', text: e instanceof Error ? e.message : '核对失败' })
    } finally { setBusy(false) }
  }

  const c = card.data
  const rows = (list.data ?? []).filter((x) => filter === 'all' || x.status === filter)
  const verified = c ? c.held + c.broken : 0
  const open = (proposals.data ?? []).filter((p) => p.status === 'proposed')

  return (
    <Page title="验证与回溯" description="每次研究最关键的几条判断会被记成验证点，到期后由代码取数核对：当时说的，后来对不对"
      actions={(
        <>
          {DEMO ? null : <Button size="sm" variant="secondary" loading={busy} onClick={() => void verify()}><RefreshCw className="h-3.5 w-3.5" />立即核对</Button>}
          {c?.total ? <AskAi label="让 AI 复盘" question="复盘一下之前的研究：验证点成立了多少，哪些判断被证伪了" /> : null}
        </>
      )}>
      {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

      <DataState loading={card.loading} error={card.error} onRetry={card.reload}
        empty={c && c.total === 0 ? '还没有验证点。在 AI 研究里对一只具体的股票做深度研究或对比，回答发布后会自动生成。' : undefined}>
        {c ? (
          <>
            <Metrics>
              <Metric label="成立率" value={rate(c.hold_rate_pct)} hint={verified ? `已核对 ${verified} 条` : '还没有核对出结果的'} />
              <Metric label="成立" value={c.held} tone="text-down" />
              <Metric label="被证伪" value={c.broken} tone="text-up" />
              <Metric label="待核对" value={c.pending} hint={c.unverifiable ? `另有 ${c.unverifiable} 条无法核对` : undefined} />
            </Metrics>
            <p className="-mt-6 text-[13px] text-steel">{c.note}。{verified > 0 && verified < 10 ? '目前已核对不足 10 条，成立率只能看个大概。' : ''}</p>

            {c.by_group.length ? (
              <Section title="按类别" hint="财务类在下一期财报出来后核对；估值和涨跌类在到期日核对">
                <Table head={[{ label: '类别' }, { label: '总数', right: true }, { label: '成立', right: true }, { label: '被证伪', right: true }, { label: '待核对', right: true }, { label: '成立率', right: true }]}>
                  {c.by_group.map((g) => (
                    <tr key={g.group}><Td>{g.label}</Td><Td right num>{g.total}</Td><Td right num>{g.held}</Td><Td right num>{g.broken}</Td><Td right num>{g.pending}</Td><Td right num>{rate(g.hold_rate_pct)}</Td></tr>
                  ))}
                </Table>
              </Section>
            ) : null}
          </>
        ) : null}
      </DataState>

      {open.length || c?.advice_mode ? (
        <Section title="操作建议单" hint="Agent 只能提出建议；每一条都要你自己授权，授权后才会改动持仓记录">
          <DataState loading={proposals.loading} error={proposals.error} onRetry={proposals.reload}
            empty={(proposals.data ?? []).length === 0 ? '还没有建议单。研究里给出明确的买入、加仓、减仓或卖出建议时会出现在这里。' : undefined}>
            <ProposalList items={proposals.data ?? []} />
          </DataState>
        </Section>
      ) : null}

      {c?.total ? (
        <Section title="全部验证点" hint={`${rows.length} 条`} actions={<Segmented value={filter} onChange={setFilter} options={FILTERS} />}>
          <DataState loading={list.loading} error={list.error} onRetry={list.reload} empty={rows.length === 0 ? `没有${CP_STATUS[filter]?.label ?? ''}的验证点` : undefined}>
            <CheckpointTable items={rows} onRemove={DEMO ? undefined : setRemoving} />
          </DataState>
          <p className="mt-3 text-[13px] text-steel">验证条件由模型在研究发布时提出，基准值和核对结果由代码取数。已经核对出结果的不能删除，成绩单不会因为删掉证伪的条目而变好看。</p>
        </Section>
      ) : null}

      <StanceSection />
      <Lessons />

      <ConfirmDialog open={removing != null} title="删除验证点" confirmText="删除"
        message={removing ? `删除「${removing.name} ${removing.metric_label}」这条待核对的验证点？` : ''}
        onCancel={() => setRemoving(null)}
        onConfirm={() => {
          const target = removing
          setRemoving(null)
          if (target) api.removeCheckpoint(target.id).then(reload).catch((e) => setMessage({ tone: 'danger', text: e instanceof Error ? e.message : '删除失败' }))
        }} />
    </Page>
  )
}

export default ReviewPage
