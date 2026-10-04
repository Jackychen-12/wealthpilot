import type React from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DEMO, api, useApi, type Security } from '../api'
import { SecuritySearch } from '../components/SecuritySearch'
import { Button, Callout, ConfirmDialog, Input, Segmented, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'

const SIDES = [['buy', '买入'], ['sell', '卖出']] as const

/** 模拟盘：不动真钱，把"建议 → 授权 → 下单 → 成交 → 持仓"先跑通。 */
const BrokerPage: React.FC = () => {
  const account = useApi(api.broker)
  const orders = useApi(api.brokerOrders)
  const [target, setTarget] = useState<Security | null>(null)
  const [side, setSide] = useState('buy')
  const [shares, setShares] = useState('100')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [resetting, setResetting] = useState(false)
  const a = account.data
  const reload = () => { account.reload(); orders.reload() }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!target) return
    setBusy(true); setMessage(null)
    try {
      const o = await api.placeOrder({ code: target.code, name: target.name, side: side as 'buy' | 'sell', shares: Number(shares), asset_type: target.asset_type })
      setMessage(o.status === 'filled'
        ? { tone: 'success', text: `已成交：${o.side === 'buy' ? '买入' : '卖出'} ${o.name} ${o.shares} 股 @ ${o.price}，费用 ${o.fee} 元` }
        : { tone: 'danger', text: `被拒：${o.reason}` })
      reload()
    } catch (err) {
      setMessage({ tone: 'danger', text: err instanceof Error ? err.message : '下单失败' })
    } finally { setBusy(false) }
  }

  if (a?.mode === 'none') {
    return (
      <Page title="模拟盘" description="不动真钱的练习账户：按最新价成交，持仓自动同步进组合">
        <Callout tone="info" title="模拟盘还没开启">
          在 <code className="font-mono text-[13px]">backend/.env</code> 里加一行 <code className="font-mono text-[13px]">BROKER=paper</code> 后重启后端。开启后，授权操作建议单会在模拟盘按最新价成交；没开启时，授权只是把你填的成交记入持仓台账。
        </Callout>
      </Page>
    )
  }

  return (
    <Page title="模拟盘" description="不动真钱的练习账户：按最新价成交，持仓自动同步进组合"
      actions={DEMO ? undefined : <Button size="sm" variant="ghost" onClick={() => setResetting(true)}>重置账户</Button>}>
      {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}
      <DataState loading={account.loading} error={account.error} onRetry={account.reload}>
        {a ? (
          <>
            <div>
              <Metrics>
                <Metric label="总资产（元）" value={yuan(a.total_assets)} hint={`初始 ${yuan(a.initial_cash)}`} />
                <Metric label="累计盈亏（元）" value={signed(a.total_pnl, 0)} tone={signClass(a.total_pnl)} hint={signed(a.total_pnl_pct, 2, '%')} />
                <Metric label="持仓市值（元）" value={yuan(a.market_value)} />
                <Metric label="可用资金（元）" value={yuan(a.cash)} />
              </Metrics>
              <p className="mt-2 text-[13px] text-steel">{a.rules}。</p>
            </div>

            {DEMO ? null : (
              <Section title="下单" hint="只有你自己点了才会下单；Agent 没有下单的工具">
                <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
                  <div className="w-64">
                    <span className="mb-1.5 block text-[13px] font-medium text-charcoal">{target ? `${target.name} ${target.code}` : '证券'}</span>
                    <SecuritySearch placeholder="搜索股票或 ETF" onPick={(s) => (s.asset_type === 'fund' ? setMessage({ tone: 'danger', text: '模拟盘只支持股票和 ETF' }) : setTarget(s))} />
                  </div>
                  <div className="pb-1.5"><Segmented value={side} onChange={setSide} options={SIDES} /></div>
                  <div className="w-32"><Input id="o-shares" label="数量（股）" type="number" min="1" step="1" value={shares} onChange={(e) => setShares(e.target.value)} required /></div>
                  <Button type="submit" className="h-10" loading={busy} disabled={!target}>按最新价{side === 'buy' ? '买入' : '卖出'}</Button>
                </form>
              </Section>
            )}

            <Section title="持仓" hint={`${a.positions.length} 只 · 已同步到「持仓」页，参与组合分析`}>
              <DataState empty={a.positions.length === 0 ? '还没有持仓。' : undefined}>
                <Table minWidth={720} head={[{ label: '证券' }, { label: '数量', right: true }, { label: '成本价', right: true }, { label: '最新价', right: true }, { label: '市值', right: true }, { label: '盈亏', right: true }, { label: '盈亏率', right: true }]}>
                  {a.positions.map((p) => (
                    <tr key={p.code}>
                      <Td><Link to={`/stock/${p.code}`} className="font-medium text-ink hover:underline">{p.name}</Link><span className="ml-2 font-mono text-xs text-stone">{p.code}</span></Td>
                      <Td right num>{p.shares}</Td>
                      <Td right num>{p.cost_price.toFixed(3)}</Td>
                      <Td right num>{p.price == null ? '—' : p.price.toFixed(3)}</Td>
                      <Td right num>{yuan(p.market_value)}</Td>
                      <Td right num className={signClass(p.pnl)}>{signed(p.pnl, 0)}</Td>
                      <Td right num className={signClass(p.pnl_pct)}>{signed(p.pnl_pct, 2, '%')}</Td>
                    </tr>
                  ))}
                </Table>
              </DataState>
            </Section>
          </>
        ) : null}
      </DataState>

      <Section title="委托记录" hint="被拒的委托也会留下原因">
        <DataState loading={orders.loading} error={orders.error} onRetry={orders.reload} empty={orders.data?.length === 0 ? '还没有委托。' : undefined}>
          <Table minWidth={760} head={[{ label: '时间' }, { label: '证券' }, { label: '方向' }, { label: '数量', right: true }, { label: '成交价', right: true }, { label: '金额', right: true }, { label: '费用', right: true }, { label: '状态' }]}>
            {(orders.data ?? []).map((o) => (
              <tr key={o.id}>
                <Td className="whitespace-nowrap font-mono text-xs text-stone">{o.created_at.slice(0, 16).replace('T', ' ')}</Td>
                <Td>{o.name} <span className="font-mono text-xs text-stone">{o.code}</span>{o.proposal_id ? <Tag tone="purple" className="ml-2 !py-0">建议单 #{o.proposal_id}</Tag> : null}</Td>
                <Td className={o.side === 'buy' ? 'text-up' : 'text-down'}>{o.side === 'buy' ? '买入' : '卖出'}</Td>
                <Td right num>{o.shares}</Td>
                <Td right num>{o.price ?? '—'}</Td>
                <Td right num>{o.status === 'filled' ? yuan(o.amount, 2) : '—'}</Td>
                <Td right num>{o.status === 'filled' ? o.fee : '—'}</Td>
                <Td>{o.status === 'filled' ? <Tag tone="green">已成交</Tag> : <span className="text-[13px] text-on-rose">被拒：{o.reason}</span>}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>

      <ConfirmDialog open={resetting} title="重置模拟盘" confirmText="重置"
        message="清空模拟盘持仓并把资金恢复到初始值？由模拟盘同步到「持仓」页的记录会一并移除，手工录入的不受影响。委托记录保留。"
        onCancel={() => setResetting(false)}
        onConfirm={() => { setResetting(false); api.resetBroker().then(reload).catch((e) => setMessage({ tone: 'danger', text: e instanceof Error ? e.message : '重置失败' })) }} />
    </Page>
  )
}

export default BrokerPage
