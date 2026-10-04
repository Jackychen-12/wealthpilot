import type React from 'react'
import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { runTool, type Backtest } from '../api'
import { AskAi } from '../components/AskAi'
import { Button, Callout, Input, Tag } from '../components/kit'
import { DataState, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'
import { cn } from '../utils/cn'

type Trigger = { drawdown_pct: string; add_pct: string }

const BacktestPage: React.FC = () => {
  const [code, setCode] = useState('')
  const [days, setDays] = useState('250')
  const [stopLoss, setStopLoss] = useState('')
  const [triggers, setTriggers] = useState<Trigger[]>([{ drawdown_pct: '5', add_pct: '30' }, { drawdown_pct: '10', add_pct: '70' }])
  const [state, setState] = useState<{ loading: boolean; error: string; data: Backtest | null }>({ loading: false, error: '', data: null })

  const update = (i: number, patch: Partial<Trigger>) => setTriggers((ts) => ts.map((t, k) => (k === i ? { ...t, ...patch } : t)))
  const valid = triggers.filter((t) => Number(t.drawdown_pct) > 0 && Number(t.add_pct) > 0)
  const totalAdd = valid.reduce((s, t) => s + Number(t.add_pct), 0)
  const ruleText = valid.map((t) => `回撤${t.drawdown_pct}%加${t.add_pct}%`).join('、')

  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    setState({ loading: true, error: '', data: null })
    try {
      const res = await runTool<Backtest | string>('backtest_rule', {
        fund_code: code.trim(), days: Number(days) || 250,
        triggers: valid.map((t) => ({ drawdown_pct: Number(t.drawdown_pct), add_pct: Number(t.add_pct) })),
        ...(stopLoss ? { stop_loss_pct: Number(stopLoss) } : {}),
      })
      if (typeof res.data === 'string') throw new Error(res.data)
      if (res.data.error) throw new Error(res.data.error)
      setState({ loading: false, error: '', data: res.data })
    } catch (err) {
      setState({ loading: false, error: err instanceof Error ? err.message : '回测失败', data: null })
    }
  }

  const d = state.data
  const legs = d ? [
    { name: '你的规则', tone: 'purple' as const, leg: d.strategy, note: `触发 ${d.strategy.trigger_count} 次 · 投入 ${d.strategy.deployed_pct}%` },
    { name: '一次性买入', tone: 'gray' as const, leg: d.baseline_lump_sum, note: '期初全部投入' },
    { name: '等额定投', tone: 'gray' as const, leg: d.baseline_dca, note: `分 ${d.baseline_dca.installments} 期` },
  ] : []

  return (
    <Page title="规则回测" description="分批建仓规则先拿历史验一遍，并和一次性买入、定投两个基线比"
      actions={code.trim() && valid.length ? <AskAi question={`${code.trim()} ${ruleText}的分批建仓规则，历史上比一次性买入好吗`} /> : undefined}>
      <Section title="规则" hint="每一档：从高点回撤达到多少时，投入总资金的百分之多少。每档只触发一次">
        <form onSubmit={(e) => void run(e)} className="flex max-w-[760px] flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Input id="bt-code" label="基金代码" placeholder="如 110011" value={code} onChange={(e) => setCode(e.target.value)} required />
            <Input id="bt-days" label="回测交易日数" type="number" min="30" max="1500" value={days} onChange={(e) => setDays(e.target.value)} />
            <Input id="bt-stop" label="止损线 %（可空）" hint="相对持仓成本跌破则清仓" type="number" step="any" min="0" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            {triggers.map((t, i) => (
              <div key={i} className="grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                <Input id={`bt-dd-${i}`} label={i === 0 ? '回撤达到 %' : undefined} type="number" step="any" min="0" value={t.drawdown_pct} onChange={(e) => update(i, { drawdown_pct: e.target.value })} />
                <Input id={`bt-add-${i}`} label={i === 0 ? '投入资金 %' : undefined} type="number" step="any" min="0" max="100" value={t.add_pct} onChange={(e) => update(i, { add_pct: e.target.value })} />
                <Button variant="ghost" className="h-10" aria-label="移除这一档" disabled={triggers.length === 1} onClick={() => setTriggers((ts) => ts.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setTriggers((ts) => [...ts, { drawdown_pct: '', add_pct: '' }])}><Plus className="h-3.5 w-3.5" />加一档</Button>
            <Button type="submit" size="sm" loading={state.loading} disabled={!code.trim() || valid.length === 0}>开始回测</Button>
            <span className={cn('text-[13px]', totalAdd > 100 ? 'text-up' : 'text-steel')}>各档合计投入 {totalAdd}%{totalAdd > 100 ? '，超过了 100%' : ''}</span>
          </div>
        </form>
      </Section>

      <DataState loading={state.loading} error={state.error}>
        {d ? (
          <>
            <Section title="结果对比" hint={`${d.period.start} 至 ${d.period.end}，共 ${d.period.trading_days} 个交易日`}>
              <Table head={[{ label: '方案' }, { label: '总收益', right: true }, { label: '年化', right: true }, { label: '最大回撤', right: true }, { label: '说明' }]}>
                {legs.map((l) => (
                  <tr key={l.name}>
                    <Td><Tag tone={l.tone}>{l.name}</Tag></Td>
                    <Td right num className={cn('font-medium', signClass(l.leg.total_return_pct))}>{signed(l.leg.total_return_pct, 2, '%')}</Td>
                    <Td right num className={signClass(l.leg.annualized_pct)}>{signed(l.leg.annualized_pct, 2, '%')}</Td>
                    <Td right num>{l.leg.max_drawdown_pct.toFixed(2)}%</Td>
                    <Td className="text-slate">{l.note}</Td>
                  </tr>
                ))}
              </Table>
              <p className="mt-3 text-sm text-charcoal">
                相对一次性买入 <b className={signClass(d.excess_vs_lump_sum_pct)}>{signed(d.excess_vs_lump_sum_pct, 2, ' 个点')}</b>，
                相对等额定投 <b className={signClass(d.excess_vs_dca_pct)}>{signed(d.excess_vs_dca_pct, 2, ' 个点')}</b>。
              </p>
            </Section>

            <Section title="触发记录" hint="信号出现后的下一个交易日按净值成交">
              {d.strategy.events.length === 0 ? (
                <DataState empty="回测区间内没有任何一档被触发，资金始终未投入。">{null}</DataState>
              ) : (
                <Table head={[{ label: '成交日' }, { label: '动作' }, { label: '成交净值', right: true }, { label: '信号日' }, { label: '当时回撤', right: true }, { label: '金额（元）', right: true }]}>
                  {d.strategy.events.map((ev, i) => (
                    <tr key={i}>
                      <Td className="font-mono text-[13px]">{ev.date}</Td>
                      <Td><Tag tone={ev.action === 'buy' ? 'green' : 'pink'}>{ev.action === 'buy' ? '买入' : '止损清仓'}</Tag></Td>
                      <Td right num>{ev.nav.toFixed(4)}</Td>
                      <Td className="font-mono text-[13px] text-slate">{ev.signal_date}</Td>
                      <Td right num>{ev.drawdown_pct == null ? '—' : `${ev.drawdown_pct}%`}</Td>
                      <Td right num>{yuan(ev.amount)}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Section>

            <Callout tone="warning" title="这份回测的局限">{d.limitations}</Callout>
          </>
        ) : null}
      </DataState>
    </Page>
  )
}

export default BacktestPage
