import type React from 'react'
import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DEMO, api, runTool, type FundInfo, type NavPoint } from '../api'
import { DEMO_DEFAULTS } from '../demo/defaults'
import { AskAi } from '../components/AskAi'
import { Button, Input, Segmented } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, signClass, signed } from '../components/ui'

const RANGES = [['21', '近 1 月'], ['63', '近 3 月'], ['125', '近半年'], ['250', '近 1 年']] as const

const FundPage: React.FC = () => {
  const [draft, setDraft] = useState(DEMO ? DEMO_DEFAULTS.fund : '')
  const [code, setCode] = useState('')
  const [days, setDays] = useState('63')
  const [state, setState] = useState<{ loading: boolean; error: string; info: FundInfo | null; nav: NavPoint[] }>({ loading: false, error: '', info: null, nav: [] })

  const load = async (target: string, range: string) => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    try {
      const [info, nav] = await Promise.all([runTool<FundInfo | string>('get_fund_info', { fund_code: target }), api.fundNav(target, Number(range))])
      if (typeof info.data === 'string') throw new Error(info.data)
      setState({ loading: false, error: '', info: info.data, nav: [...nav.data].reverse() })
    } catch (e) {
      setState({ loading: false, error: e instanceof Error ? e.message : '查询失败', info: null, nav: [] })
    }
  }
  const search = (e: React.FormEvent) => {
    e.preventDefault()
    const target = draft.trim()
    if (!target) return
    setCode(target)
    void load(target, days)
  }

  const { info, nav } = state
  const first = nav[0]?.nav
  const last = nav[nav.length - 1]?.nav
  const stage = (v?: string) => (v == null || v === '' ? null : Number(v))

  return (
    <Page title="基金查询" description="查任意一只基金：净值走势、阶段收益、经理与基准"
      actions={info ? <AskAi question={`${info.code} ${info.name} 近期表现如何，值得关注什么？`} /> : undefined}>
      <form onSubmit={search} className="flex max-w-md items-end gap-2">
        <div className="flex-1"><Input id="fund-code" label="基金代码" placeholder="如 110011" value={draft} onChange={(e) => setDraft(e.target.value)} inputMode="numeric" /></div>
        <Button type="submit" className="h-10" loading={state.loading} disabled={!draft.trim()}>查询</Button>
      </form>

      <DataState loading={state.loading && !info} error={state.error} empty={!code ? '输入 6 位基金代码开始查询。' : undefined}>
        {info ? (
          <>
            <div>
              <h2 className="text-[22px] font-semibold tracking-[-0.2px] text-ink">{info.name} <span className="font-mono text-base font-normal text-stone">{info.code}</span></h2>
              <div className="mt-3">
                <Metrics>
                  <Metric label="单位净值" value={info.nav.toFixed(4)} hint={info.nav_date} />
                  {([['近 1 周', info.return_1w], ['近 1 月', info.return_1m], ['近 3 月', info.return_3m], ['近 1 年', info.return_1y]] as const).map(([label, v]) => (
                    <Metric key={label} label={label} value={stage(v) == null ? '—' : signed(stage(v), 2, '%')} tone={signClass(stage(v))} />
                  ))}
                </Metrics>
              </div>
            </div>

            <Section title="净值走势" actions={<Segmented value={days} onChange={(v) => { setDays(v); void load(code, v) }} options={RANGES} />}
              hint={first && last ? `区间 ${nav[0].nav_date} 至 ${nav[nav.length - 1].nav_date}，共 ${nav.length} 个交易日` : undefined}>
              <DataState loading={state.loading} empty={nav.length === 0 ? '没有取到净值历史' : undefined}>
                <div className="h-[280px] rounded-lg border border-hairline p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={nav} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
                      <XAxis dataKey="nav_date" tick={{ fill: 'var(--steel)', fontSize: 11 }} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={48} tickFormatter={(d: string) => d.slice(5)} />
                      <YAxis domain={['auto', 'auto']} tick={{ fill: 'var(--steel)', fontSize: 11 }} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => v.toFixed(2)} />
                      <Tooltip formatter={(v) => [Number(v).toFixed(4), '单位净值']} labelStyle={{ color: 'var(--steel)' }}
                        contentStyle={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }} />
                      <Line type="monotone" dataKey="nav" stroke="var(--primary)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </DataState>
            </Section>

            <Section title="基本信息">
              <dl className="grid max-w-[720px] grid-cols-[7rem_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm">
                {([['类型', info.type], ['基金经理', info.manager], ['基金公司', info.company], ['规模', info.scale], ['业绩基准', info.benchmark]] as const).map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-steel">{k}</dt><dd className="text-charcoal">{v || <span className="text-stone">未取到</span>}</dd></div>
                ))}
              </dl>
            </Section>
          </>
        ) : null}
      </DataState>
    </Page>
  )
}

export default FundPage
