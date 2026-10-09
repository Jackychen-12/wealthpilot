import type React from 'react'
import { useState } from 'react'
import { api, useApi, type DecisionGroup, type Security } from '../api'
import { SecuritySearch } from '../components/SecuritySearch'
import { Button, Callout, Input, Select, Tag } from '../components/kit'
import { Terms } from '../components/Terms'
import { DataState, Section, Table, Td, signClass } from '../components/ui'

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
const KINDS = ['自己研究', 'AI 研究', '博主 / 大V', '朋友推荐', '新闻 / 公告', '群 / 论坛', '券商研报', '其他']

const cell = (g: DecisionGroup['d20']) => (g.settled ? `${g.beat} / ${g.settled} 笔跑赢` : '还没到期')
const excess = (g: DecisionGroup['d20']) => (g.avg_excess_pct == null ? '—' : `${g.avg_excess_pct > 0 ? '+' : ''}${g.avg_excess_pct} 个点`)

/** 买入理由记录：每次动手记一句为什么、消息从哪来；过后按来源对账。不调用模型。 */
export const DecisionsSection: React.FC = () => {
  const review = useApi(api.decisionsReview)
  const [stock, setStock] = useState<Security | null>(null)
  const [form, setForm] = useState({ reason: '', kind: KINDS[0], who: '', day: today(), action: 'buy' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }))

  const save = async () => {
    if (!stock) return
    setBusy(true); setError('')
    try {
      await api.addDecision({ code: stock.code, name: stock.name, action: form.action, day: form.day, reason: form.reason, source_kind: form.kind, source_name: form.who })
      setStock(null); set({ reason: '', who: '' }); review.reload()
    } catch (e) { setError(e instanceof Error ? e.message : '没有记上') } finally { setBusy(false) }
  }
  const remove = async (id: number) => {
    try { await api.removeDecision(id); review.reload() } catch (e) { setError(e instanceof Error ? e.message : '没有删掉') }
  }
  const data = review.data
  const groups = data ? [...data.by_source, ...data.by_name.map((n) => ({ ...n, source: `其中 ${n.source}` }))] : []

  return (
    <>
      <Section title="买入理由记录" hint="每次动手时记一句：为什么买，消息从哪来。记录存在你自己的电脑上">
        <div className="grid max-w-3xl gap-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_120px_150px]">
            <div className="flex min-w-0 flex-col gap-1.5">
              <span className="text-[13px] font-medium text-slate">哪只股票</span>
              {stock
                ? <div className="flex h-10 items-center justify-between rounded-md border border-hairline-strong px-3 text-sm text-ink"><span className="truncate">{stock.name} <span className="font-mono text-xs text-stone">{stock.code}</span></span><button type="button" className="text-[13px] text-slate underline underline-offset-2" onClick={() => setStock(null)}>换一只</button></div>
                : <SecuritySearch placeholder="搜名称或代码" onPick={setStock} />}
            </div>
            <Select label="买还是卖" value={form.action} onChange={(v) => set({ action: v })} options={[{ value: 'buy', label: '买入' }, { value: 'sell', label: '卖出' }]} />
            <Input label="哪天" type="date" max={today()} value={form.day} onChange={(e) => set({ day: e.target.value })} />
          </div>
          <Input label="当时为什么" maxLength={300} placeholder="比如：储能订单超预期，估值在历史低位" value={form.reason} onChange={(e) => set({ reason: e.target.value })} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="想法从哪来" value={form.kind} onChange={(v) => set({ kind: v })} options={KINDS.map((k) => ({ value: k, label: k }))} />
            <Input label="具体是谁 / 哪里（可不填）" maxLength={40} placeholder="比如某位博主的名字" value={form.who} onChange={(e) => set({ who: e.target.value })} />
          </div>
          <div><Button loading={busy} disabled={!stock || !form.reason.trim()} onClick={() => void save()}>记下来</Button></div>
          {error ? <Callout tone="danger">{error}</Callout> : null}
        </div>
      </Section>

      <Section title="按来源对账" hint={`买入之后 20、60 个交易日，相对${data?.benchmark ?? '沪深 300'} 的超额收益。只算买入`}>
        <DataState loading={review.loading && !data} error={review.error} onRetry={review.reload} empty={data && !groups.length ? data.note : undefined}>
          <Table minWidth={640} head={[{ label: '来源' }, { label: '买入', right: true }, { label: '20 日后', right: true }, { label: '平均超额', right: true }, { label: '60 日后', right: true }, { label: '平均超额', right: true }]}>
            {groups.map((g) => (
              <tr key={g.source}>
                <Td className={g.source.startsWith('其中') ? 'pl-6 text-slate' : 'font-medium text-ink'}>{g.source}</Td>
                <Td right num>{g.count} 笔</Td>
                <Td right num>{cell(g.d20)}</Td><Td right num className={signClass(g.d20.avg_excess_pct)}>{excess(g.d20)}</Td>
                <Td right num>{cell(g.d60)}</Td><Td right num className={signClass(g.d60.avg_excess_pct)}>{excess(g.d60)}</Td>
              </tr>
            ))}
          </Table>
          {data?.note ? <p className="mt-2 text-[13px] text-steel">{data.note}</p> : null}
          <Terms className="mt-2" words={['按来源对账', '超额收益', '买卖理由']} />
        </DataState>
        {data?.decisions.length ? (
          <ul className="mt-4 divide-y divide-hairline-soft rounded-lg border border-hairline">
            {data.decisions.slice(0, 30).map((d) => (
              <li key={d.id} className="flex items-start gap-3 px-4 py-2.5 text-sm">
                <span className="w-[86px] shrink-0 tabular-nums text-steel">{d.day}</span>
                <Tag tone={d.action === 'sell' ? 'green' : 'pink'}>{d.action === 'sell' ? '卖' : '买'}</Tag>
                <span className="min-w-0 flex-1 text-charcoal"><span className="font-medium text-ink">{d.name}</span> {d.reason}
                  <span className="ml-2 text-[13px] text-steel">{d.source_kind}{d.source_name ? ` · ${d.source_name}` : ''}</span></span>
                <button type="button" aria-label={`删除 ${d.day} ${d.name} 这条记录`} className="shrink-0 text-[13px] text-steel underline underline-offset-2 hover:text-ink" onClick={() => void remove(d.id)}>删除</button>
              </li>
            ))}
          </ul>
        ) : null}
      </Section>
    </>
  )
}
