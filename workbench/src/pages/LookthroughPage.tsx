import type React from 'react'
import { useEffect, useState } from 'react'
import { api, runTool, useApi, type Lookthrough, type Overlap } from '../api'
import { AskAi } from '../components/AskAi'
import { Button, Callout, Select, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td } from '../components/ui'

const LookthroughPage: React.FC = () => {
  const holdings = useApi(api.holdings)
  const look = useApi(() => runTool<Lookthrough | string>('lookthrough_portfolio'))
  const funds = (holdings.data ?? []).filter((h) => h.asset_type === 'fund')
  const nameOf = (code: string) => funds.find((f) => f.fund_code === code)?.fund_name ?? code

  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const firstCode = funds[0]?.fund_code
  const secondCode = funds[1]?.fund_code
  useEffect(() => { if (!a && firstCode) setA(firstCode); if (!b && secondCode) setB(secondCode) }, [a, b, firstCode, secondCode])
  const [overlap, setOverlap] = useState<{ loading: boolean; error: string; data: Overlap | null }>({ loading: false, error: '', data: null })

  const compare = async () => {
    setOverlap({ loading: true, error: '', data: null })
    try {
      const res = await runTool<Overlap | string>('compute_stock_overlap', { fund_code_a: a, fund_code_b: b })
      setOverlap(typeof res.data === 'string' ? { loading: false, error: res.data, data: null } : { loading: false, error: '', data: res.data })
    } catch (e) {
      setOverlap({ loading: false, error: e instanceof Error ? e.message : '对比失败', data: null })
    }
  }

  const d = look.data && typeof look.data.data !== 'string' ? look.data.data : null
  const emptyText = look.data && typeof look.data.data === 'string' ? look.data.data : undefined
  const options = funds.map((f) => ({ value: f.fund_code, label: `${f.fund_name}（${f.fund_code}）` }))

  return (
    <Page title="持仓穿透" description="把基金拆到个股：你真正持有的是什么，哪些票被多只基金同时重仓"
      actions={<AskAi question="把我的组合穿透到个股，真实暴露集中在哪里？有没有隐性重叠？" />}>
      <DataState loading={look.loading} error={look.error} onRetry={look.reload} empty={emptyText}>
        {d ? (
          <>
            <div className="flex flex-col gap-3">
              <Metrics>
                <Metric label="穿透到的个股" value={d.stocks.length} hint={`覆盖 ${d.covered_fund_count} / ${d.total_fund_count} 只基金`} />
                <Metric label="被多只基金同时重仓" value={d.multi_fund_stocks.length} hint="隐性重叠" tone={d.multi_fund_stocks.length ? 'text-warning' : undefined} />
                <Metric label="重叠部分合计暴露" value={`${d.multi_fund_exposure_pct.toFixed(2)}%`} hint="占组合市值" />
                <Metric label="最大单票暴露" value={d.top_exposure[0] ? `${d.top_exposure[0].exposure_pct.toFixed(2)}%` : '—'} hint={d.top_exposure[0]?.stock_name} />
              </Metrics>
              <Callout tone="warning">{d.note}</Callout>
            </div>

            <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <Section title="个股暴露 Top 10" hint={d.summary}>
                <Table head={[{ label: '个股' }, { label: '占组合', right: true }, { label: '通过哪些基金持有' }]}>
                  {d.top_exposure.map((s) => (
                    <tr key={s.stock_code}>
                      <Td><span className="font-medium text-ink">{s.stock_name}</span> <span className="font-mono text-xs text-stone">{s.stock_code}</span></Td>
                      <Td right num>{s.exposure_pct.toFixed(2)}%</Td>
                      <Td>
                        <span className="flex flex-wrap gap-1">
                          {s.via_funds.map((v) => <Tag key={v.fund_code} tone={s.held_by_funds > 1 ? 'orange' : 'gray'}>{nameOf(v.fund_code)} {v.weight_pct}%</Tag>)}
                        </span>
                      </Td>
                    </tr>
                  ))}
                </Table>
              </Section>

              <Section title="数据覆盖度" hint="各基金前十大重仓占其净值的比例">
                <ul className="divide-y divide-hairline-soft border-y border-hairline-soft">
                  {Object.entries(d.coverage_by_fund).map(([code, pct]) => (
                    <li key={code} className="py-2.5 text-sm">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-charcoal">{nameOf(code)}</span>
                        <span className="tabular-nums text-ink">{pct.toFixed(1)}%</span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, pct)}%` }} /></div>
                      <p className="mt-1 font-mono text-xs text-stone">季报 {d.report_dates[code] ?? '—'}</p>
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          </>
        ) : null}
      </DataState>

      <Section title="两只基金的重仓股重叠" hint="净值相关性只说明同涨同跌，重叠的个股才解释为什么">
        {funds.length < 2 ? (
          <DataState empty="至少需要 2 只基金持仓才能对比">{null}</DataState>
        ) : (
          <>
            <div className="mb-4 grid items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <Select id="ov-a" label="基金 A" value={a} onChange={setA} options={options} />
              <Select id="ov-b" label="基金 B" value={b} onChange={setB} options={options} />
              <Button onClick={() => void compare()} loading={overlap.loading} disabled={!a || !b || a === b} className="h-10">对比</Button>
            </div>
            <DataState loading={overlap.loading} error={overlap.error}>
              {overlap.data ? (
                overlap.data.shared_count === 0 ? (
                  <Callout tone="success">前十大重仓股没有重合（季报 {Object.values(overlap.data.report_dates)[0]}）。第十一位之后的持仓季报不披露，看不到。</Callout>
                ) : (
                  <>
                    <p className="mb-3 text-sm text-slate">共有 <b className="text-ink">{overlap.data.shared_count}</b> 只重合，重合部分合计权重 <b className="text-ink">{overlap.data.combined_weight_pct}%</b></p>
                    <Table head={[{ label: '个股' }, { label: `在 ${nameOf(overlap.data.fund_a)} 中`, right: true }, { label: `在 ${nameOf(overlap.data.fund_b)} 中`, right: true }]}>
                      {overlap.data.shared_stocks.map((s) => (
                        <tr key={s.stock_code}>
                          <Td><span className="font-medium text-ink">{s.stock_name}</span> <span className="font-mono text-xs text-stone">{s.stock_code}</span></Td>
                          <Td right num>{s.weight_a}%</Td>
                          <Td right num>{s.weight_b}%</Td>
                        </tr>
                      ))}
                    </Table>
                  </>
                )
              ) : null}
            </DataState>
          </>
        )}
      </Section>
    </Page>
  )
}

export default LookthroughPage
