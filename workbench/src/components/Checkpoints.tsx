import type React from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DEMO, api, useApi, type Checkpoint, type Proposal } from '../api'
import { Button, Callout, Drawer, Input, Tag, type Tone } from './kit'
import { Table, Td } from './ui'

export const CP_STATUS: Record<string, { tone: Tone; label: string }> = {
  pending: { tone: 'gray', label: '待核对' },
  held: { tone: 'green', label: '成立' },
  broken: { tone: 'pink', label: '被证伪' },
  unverifiable: { tone: 'yellow', label: '无法核对' },
}
const GROUP: Record<string, string> = { financial: '财务', valuation: '估值', market: '涨跌' }
const fmt = (v: number | null) => (v == null ? '—' : `${v}%`)

/** 验证点列表：条件、设定时的值、核对结果。数字都是代码取的，不是模型写的。 */
export const CheckpointTable: React.FC<{ items: Checkpoint[]; showStock?: boolean; onRemove?: (c: Checkpoint) => void }> = ({ items, showStock = true, onRemove }) => (
  <Table minWidth={showStock ? 860 : 720} head={[...(showStock ? [{ label: '股票' }] : []), { label: '验证条件' }, { label: '设定时', right: true }, { label: '核对结果', right: true }, { label: '状态' }, ...(onRemove ? [{ label: '' }] : [])]}>
    {items.map((c) => (
      <tr key={c.id}>
        {showStock ? <Td className="whitespace-nowrap"><Link to={`/stock/${c.code}`} className="font-medium text-ink hover:underline">{c.name}</Link><div className="font-mono text-xs text-stone">{c.code}</div></Td> : null}
        <Td>
          <div className="text-ink"><Tag className="mr-2 !py-0">{GROUP[c.group] ?? c.group}</Tag>{c.metric_label} <b className="font-semibold tabular-nums">{c.op === '>=' ? '≥' : '≤'} {c.threshold}%</b></div>
          {c.statement ? <div className="mt-0.5 text-[13px] leading-relaxed text-steel">{c.statement}</div> : null}
        </Td>
        <Td right num className="whitespace-nowrap">{fmt(c.baseline_value)}<div className="font-mono text-xs text-stone">{c.baseline_as_of}</div></Td>
        <Td right num className="whitespace-nowrap">
          {c.actual_value == null ? <span className="text-steel">{c.status === 'pending' ? `${c.due} 核对` : '—'}</span> : <>{fmt(c.actual_value)}<div className="font-mono text-xs text-stone">{c.actual_as_of}</div></>}
        </Td>
        <Td><Tag tone={CP_STATUS[c.status]?.tone}>{CP_STATUS[c.status]?.label ?? c.status}</Tag></Td>
        {onRemove ? <Td right>{c.status === 'pending' || c.status === 'unverifiable' ? <Button size="xs" variant="ghost" onClick={() => onRemove(c)}>删除</Button> : null}</Td> : null}
      </tr>
    ))}
  </Table>
)

const P_STATUS: Record<string, { tone: Tone; label: string }> = {
  proposed: { tone: 'purple', label: '待你决定' }, executed: { tone: 'green', label: '已执行' }, rejected: { tone: 'gray', label: '已拒绝' },
}

/** 操作建议单：Agent 只能提出，逐条由用户授权。授权 = 把成交记入持仓台账，不向券商下单。 */
export const ProposalList: React.FC<{ items: Proposal[]; onChanged?: (p: Proposal) => void }> = ({ items, onChanged }) => {
  const [local, setLocal] = useState<Record<number, Proposal>>({})
  const paper = useApi(api.broker).data?.mode === 'paper'
  const [target, setTarget] = useState<Proposal | null>(null)
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const done = (p: Proposal) => { setLocal((m) => ({ ...m, [p.id]: p })); setTarget(null); onChanged?.(p) }
  const act = async (work: () => Promise<Proposal>) => {
    setBusy(true); setError('')
    try { done(await work()) } catch (e) { setError(e instanceof Error ? e.message : '操作失败') } finally { setBusy(false) }
  }
  const open = (p: Proposal) => { setTarget(p); setShares(p.shares ? String(p.shares) : ''); setPrice(p.price_ref ? String(p.price_ref) : ''); setError('') }
  const selling = target?.action === 'reduce' || target?.action === 'sell'

  return (
    <>
      <div className="flex flex-col gap-3">
        {items.map((raw) => {
          const p = local[raw.id] ?? raw
          return (
            <div key={p.id} className="rounded-lg border border-hairline p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Tag tone={p.action === 'buy' || p.action === 'add' ? 'pink' : 'green'}>{p.action_label}</Tag>
                <Link to={`/stock/${p.code}`} className="font-medium text-ink hover:underline">{p.name}</Link>
                <span className="font-mono text-xs text-stone">{p.code}</span>
                <span className="text-[13px] tabular-nums text-steel">{p.shares ? `建议 ${p.shares} 股` : '数量由你定'}{p.price_ref ? ` · 提出时价格 ${p.price_ref}` : ''}</span>
                <Tag tone={P_STATUS[p.status]?.tone} className="ml-auto">{P_STATUS[p.status]?.label}{p.status === 'executed' ? ` · ${p.exec_shares} 股 @ ${p.exec_price}` : ''}</Tag>
              </div>
              {p.reason ? <p className="mt-2 text-sm leading-relaxed text-charcoal">{p.reason}</p> : null}
              {p.invalidation ? <p className="mt-1 text-[13px] leading-relaxed text-steel">失效条件：{p.invalidation}</p> : null}
              {p.status === 'proposed' ? (
                <div className="mt-3 flex items-center gap-2">
                  <Button size="sm" disabled={DEMO} onClick={() => open(p)}>{paper ? '授权并在模拟盘下单' : '授权并记入持仓'}</Button>
                  <Button size="sm" variant="ghost" disabled={DEMO || busy} onClick={() => void act(() => api.rejectProposal(p.id))}>不采纳</Button>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
      {error && !target ? <Callout tone="danger" className="mt-3">{error}</Callout> : null}

      <Drawer open={target != null} onClose={() => setTarget(null)} title={target ? `${target.action_label} ${target.name}` : ''} width="max-w-sm">
        {target ? (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void act(() => api.authorizeProposal(target.id, Number(shares), paper ? null : Number(price))) }}>
            {paper ? (
              <Callout tone="info">将在<b>模拟盘</b>按最新价{selling ? '卖出' : '买入'}，不动真钱。成交后持仓自动同步进组合。买入须为 100 股的整数倍，当天买入的次日才能卖。</Callout>
            ) : (
              <Callout tone="warning">
                这一步<b>不会向券商下单</b>。请先在你的券商完成交易，再把实际成交的数量和价格填在这里，系统会据此{selling ? '减少' : '增加'}持仓记录。
              </Callout>
            )}
            <Input id="p-shares" label={paper ? '数量（股）' : '成交数量（股）'} type="number" min="1" step="1" value={shares} onChange={(e) => setShares(e.target.value)} required />
            {paper ? null : <Input id="p-price" label="成交价（元）" type="number" min="0" step="any" value={price} onChange={(e) => setPrice(e.target.value)} required />}
            {error ? <Callout tone="danger">{error}</Callout> : null}
            <div className="flex gap-2">
              <Button type="submit" loading={busy}>{paper ? '确认下单' : '确认记入持仓'}</Button>
              <Button variant="ghost" onClick={() => setTarget(null)}>取消</Button>
            </div>
          </form>
        ) : null}
      </Drawer>
    </>
  )
}
