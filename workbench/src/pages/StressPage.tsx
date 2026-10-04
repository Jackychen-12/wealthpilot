import type React from 'react'
import { useEffect, useState } from 'react'
import { api, useApi } from '../api'
import { CATEGORY, DataState, DivergingBar, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'
import { cn } from '../utils/cn'

const StressPage: React.FC = () => {
  const all = useApi(api.scenarios)
  const [key, setKey] = useState('')
  const scenarios = all.data?.scenarios ?? []
  const first = scenarios[0]?.scenario_key
  useEffect(() => { if (!key && first) setKey(first) }, [key, first])
  const detail = useApi(() => (key ? api.scenario(key) : Promise.resolve(null)), [key])
  const worst = Math.max(1, ...scenarios.map((s) => Math.abs(s.pnl)))
  const d = detail.data

  return (
    <Page title="压力测试" description="预设情景下组合会亏多少。幅度是预设口径，不是预测">
      <Section title="各情景下的组合损益" hint={`${all.data?.assumption ?? ''} 点一行查看逐持仓明细。`}>
        <DataState loading={all.loading} error={all.error} onRetry={all.reload}
          empty={scenarios.length === 0 ? all.data?.message ?? '暂无持仓，无法测算' : undefined}>
          <Table head={[{ label: '情景' }, { label: '亏损 ← → 盈利', className: 'w-[40%]' }, { label: '损益（元）', right: true }, { label: '幅度', right: true }]}>
            {scenarios.map((s) => (
              <tr key={s.scenario_key} onClick={() => setKey(s.scenario_key)} className={cn('cursor-pointer', s.scenario_key === key && '[&>td]:!bg-tint-lavender/50')}>
                <Td className="font-medium text-ink">{s.label}</Td>
                <Td><DivergingBar value={s.pnl} max={worst} /></Td>
                <Td right num className={signClass(s.pnl)}>{signed(s.pnl, 0)}</Td>
                <Td right num className={signClass(s.pnl)}>{signed(s.pnl_pct, 2, '%')}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>

      {key ? (
        <Section title={d?.label ? `明细：${d.label}` : '明细'}
          hint={d && !d.error ? `组合从 ${yuan(d.total_before)} 元变为 ${yuan(d.total_after)} 元（${signed(d.pnl_pct, 2, '%')}）` : undefined}>
          <DataState loading={detail.loading} error={detail.error || d?.error} onRetry={detail.reload}>
            <Table head={[{ label: '标的' }, { label: '类别' }, { label: '假设冲击', right: true }, { label: '冲击前', right: true }, { label: '冲击后', right: true }, { label: '损益（元）', right: true }]}>
              {(d?.holdings ?? []).map((h) => (
                <tr key={h.fund_code}>
                  <Td><div className="font-medium text-ink">{h.fund_name}</div><div className="font-mono text-xs text-stone">{h.fund_code}</div></Td>
                  <Td>{CATEGORY[h.category] ?? h.category}{h.industry ? <span className="text-steel"> · {h.industry}</span> : null}</Td>
                  <Td right num>{signed(h.shock_pct, 1, '%')}</Td>
                  <Td right num>{yuan(h.value_before)}</Td>
                  <Td right num>{yuan(h.value_after)}</Td>
                  <Td right num className={signClass(h.pnl)}>{signed(h.pnl, 0)}</Td>
                </tr>
              ))}
            </Table>
          </DataState>
        </Section>
      ) : null}
    </Page>
  )
}

export default StressPage
