import type React from 'react'
import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, runTool, useApi, type ConstraintCheck, type Simulation } from '../api'
import { AskAi } from '../components/AskAi'
import { Button, Callout, Input, Select, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'

type Change = { fund_code: string; mode: 'target_pct' | 'amount'; value: string }
const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(2)}%`)

const RebalancePage: React.FC = () => {
  const navigate = useNavigate()
  const holdings = useApi(api.holdings)
  const rows = holdings.data ?? []
  const nameOf = (code: string) => rows.find((h) => h.fund_code === code)?.fund_name ?? code
  const [changes, setChanges] = useState<Change[]>([])
  const firstCode = rows[0]?.fund_code
  useEffect(() => { if (changes.length === 0 && firstCode) setChanges([{ fund_code: firstCode, mode: 'target_pct', value: '' }]) }, [changes.length, firstCode])
  const [result, setResult] = useState<{ loading: boolean; error: string; sim: Simulation | null; check: ConstraintCheck | null }>({ loading: false, error: '', sim: null, check: null })

  const update = (i: number, patch: Partial<Change>) => setChanges((cs) => cs.map((c, k) => (k === i ? { ...c, ...patch } : c)))
  const payload = changes.filter((c) => c.value !== '' && Number.isFinite(Number(c.value)))
    .map((c) => ({ fund_code: c.fund_code, [c.mode]: Number(c.value) }))

  const run = async (e: React.FormEvent) => {
    e.preventDefault()
    setResult({ loading: true, error: '', sim: null, check: null })
    try {
      const [sim, check] = await Promise.all([
        runTool<Simulation | string>('simulate_portfolio_change', { changes: payload }),
        runTool<ConstraintCheck>('check_profile_constraint', { changes: payload }),
      ])
      if (typeof sim.data === 'string') throw new Error(sim.data)
      if (sim.data.error) throw new Error(sim.data.error)
      setResult({ loading: false, error: '', sim: sim.data, check: check.data })
    } catch (err) {
      setResult({ loading: false, error: err instanceof Error ? err.message : '推演失败', sim: null, check: null })
    }
  }

  const { sim, check } = result
  const codes = sim ? Array.from(new Set([...Object.keys(sim.before.weights), ...Object.keys(sim.after.weights)])) : []
  const options = rows.map((h) => ({ value: h.fund_code, label: `${h.fund_name}（${h.fund_code}）` }))
  const describe = payload.map((c) => `${nameOf(c.fund_code)}${'target_pct' in c ? `调到 ${c.target_pct}%` : `${Number(c.amount) >= 0 ? '加' : '减'} ${Math.abs(Number(c.amount))} 元`}`).join('、')

  return (
    <Page title="调仓推演" description="动手之前先算一遍：调完之后占比、集中度、回撤估计怎么变，会不会越过你的风险画像"
      actions={payload.length ? <AskAi question={`如果我把${describe}，对组合风险有什么影响？合适吗？`} label="让 AI 评估这个方案" /> : undefined}>
      {!holdings.loading && rows.length === 0 ? (
        <DataState empty="还没有持仓，无法推演。" emptyAction={<Button size="sm" onClick={() => navigate('/holdings')}>去录入持仓</Button>}>{null}</DataState>
      ) : (
        <Section title="拟议变动" hint="目标占比填 0–100；金额为正是加仓、为负是减仓。可同时调多只">
          <form onSubmit={(e) => void run(e)} className="flex max-w-[760px] flex-col gap-3">
            {changes.map((c, i) => (
              <div key={i} className="grid items-end gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                <Select id={`rb-code-${i}`} label={i === 0 ? '标的' : undefined} value={c.fund_code} onChange={(v) => update(i, { fund_code: v })} options={options} />
                <Select id={`rb-mode-${i}`} label={i === 0 ? '方式' : undefined} value={c.mode} onChange={(v) => update(i, { mode: v as Change['mode'] })}
                  options={[{ value: 'target_pct', label: '调到目标占比 %' }, { value: 'amount', label: '加减金额 元' }]} />
                <Input id={`rb-value-${i}`} label={i === 0 ? '数值' : undefined} type="number" step="any" placeholder={c.mode === 'target_pct' ? '如 15' : '如 5000 或 -3000'}
                  value={c.value} onChange={(e) => update(i, { value: e.target.value })} />
                <Button variant="ghost" className="h-10" aria-label="移除这一行" disabled={changes.length === 1} onClick={() => setChanges((cs) => cs.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => setChanges((cs) => [...cs, { fund_code: firstCode ?? '', mode: 'target_pct', value: '' }])}><Plus className="h-3.5 w-3.5" />再加一只</Button>
              <Button type="submit" size="sm" loading={result.loading} disabled={payload.length === 0}>开始推演</Button>
            </div>
          </form>
        </Section>
      )}

      <DataState loading={result.loading} error={result.error}>
        {sim && check ? (
          <>
            <Section title="画像约束校验" hint="按你的风险画像逐条核对变动后的组合">
              {check.passed
                ? <Callout tone="success" title="通过">变动后的组合没有越过风险画像的任何约束。</Callout>
                : (
                  <Callout tone="danger" title="未通过"
                    action={check.violations.some((v) => v.includes('风险测评')) ? <Button size="xs" variant="secondary" onClick={() => navigate('/profile')}>去设置画像</Button> : undefined}>
                    <ul className="list-disc pl-5">{check.violations.map((v, i) => <li key={i}>{v}</li>)}</ul>
                  </Callout>
                )}
            </Section>

            <Section title="变动前后对比" hint="加权最大回撤估计是各持仓历史最大回撤按占比加权的和，是保守的上界，不是对组合真实回撤的预测">
              <Metrics>
                <Metric label="组合市值（元）" value={yuan(sim.after.total_value)} hint={`原 ${yuan(sim.before.total_value)}`} />
                <Metric label="最大单一占比" value={pct(sim.after.concentration.max_weight)} hint={`原 ${pct(sim.before.concentration.max_weight)}`} />
                <Metric label="有效持仓数" value={sim.after.concentration.effective_holdings.toFixed(2)} hint={`原 ${sim.before.concentration.effective_holdings.toFixed(2)}`} />
                <Metric label="加权最大回撤估计" value={pct(sim.after.weighted_max_drawdown)} hint={`原 ${pct(sim.before.weighted_max_drawdown)}`} />
              </Metrics>
              <div className="mt-4">
                <Table head={[{ label: '标的' }, { label: '变动前占比', right: true }, { label: '变动后占比', right: true }, { label: '占比变化', right: true }, { label: '需要买卖（元）', right: true }]}>
                  {codes.map((code) => {
                    const before = sim.before.weights[code] ?? 0
                    const after = sim.after.weights[code] ?? 0
                    const delta = sim.changes.find((c) => c.fund_code === code)?.delta_amount
                    return (
                      <tr key={code}>
                        <Td><span className="font-medium text-ink">{nameOf(code)}</span> <span className="font-mono text-xs text-stone">{code}</span>{delta != null ? <Tag tone="purple" className="ml-2">调整</Tag> : null}</Td>
                        <Td right num>{pct(before)}</Td>
                        <Td right num>{pct(after)}</Td>
                        <Td right num className="text-slate">{signed((after - before) * 100, 2, ' 个点')}</Td>
                        <Td right num className={signClass(delta ?? 0)}>{delta == null ? '—' : signed(delta, 0)}</Td>
                      </tr>
                    )
                  })}
                </Table>
              </div>
            </Section>
          </>
        ) : null}
      </DataState>
    </Page>
  )
}

export default RebalancePage
