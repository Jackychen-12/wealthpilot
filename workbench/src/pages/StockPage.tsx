import type React from 'react'
import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DEMO, api, runTool, type NavPoint, type StockProfile, type StockQuote, type StockReport, type StockValuation } from '../api'
import { AskAi } from '../components/AskAi'
import { DEMO_DEFAULTS } from '../demo/defaults'
import { Button, Callout, Input, Segmented, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed } from '../components/ui'

const RANGES = [['21', '近 1 月'], ['63', '近 3 月'], ['125', '近半年'], ['250', '近 1 年']] as const
type Loaded = { quote: StockQuote; valuation: StockValuation | null; profile: StockProfile | null; reports: StockReport[]; kline: NavPoint[] }
const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toFixed(digits))

/** 工具返回字符串说明"没取到"，返回对象才是数据。 */
const data = <T,>(res: { data: T | string }): T | null => (typeof res.data === 'string' ? null : res.data)

const StockPage: React.FC = () => {
  const [draft, setDraft] = useState(DEMO ? DEMO_DEFAULTS.stock : '')
  const [code, setCode] = useState('')
  const [days, setDays] = useState('125')
  const [state, setState] = useState<{ loading: boolean; error: string; loaded: Loaded | null }>({ loading: false, error: '', loaded: null })

  const load = async (target: string, range: string) => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    try {
      const [quote, valuation, profile, financials, kline] = await Promise.all([
        runTool<StockQuote | string>('get_stock_quote', { code: target }),
        runTool<StockValuation | string>('get_stock_valuation', { code: target }),
        runTool<StockProfile | string>('get_stock_profile', { code: target }),
        runTool<{ reports: StockReport[] } | string>('get_stock_financials', { code: target }),
        api.stockKline(target, Number(range)),
      ])
      const q = data(quote)
      if (!q) throw new Error(String(quote.data))
      setState({ loading: false, error: '', loaded: {
        quote: q, valuation: data(valuation), profile: data(profile),
        reports: data(financials)?.reports ?? [], kline: [...kline.data].reverse(),
      } })
    } catch (e) {
      setState({ loading: false, error: e instanceof Error ? e.message : '查询失败', loaded: null })
    }
  }
  const search = (e: React.FormEvent) => {
    e.preventDefault()
    const target = draft.trim()
    if (!target) return
    setCode(target)
    void load(target, days)
  }
  const changeRange = async (range: string) => {
    setDays(range)
    if (!state.loaded) return
    try {
      const kline = await api.stockKline(code, Number(range))
      setState((s) => (s.loaded ? { ...s, loaded: { ...s.loaded, kline: [...kline.data].reverse() } } : s))
    } catch (e) {
      setState((s) => ({ ...s, error: e instanceof Error ? e.message : '日线获取失败' }))
    }
  }

  const d = state.loaded
  const range = d?.valuation?.price_range_1y
  const first = d?.kline[0]?.nav
  const last = d?.kline[d.kline.length - 1]?.nav
  const periodReturn = first && last ? ((last - first) / first) * 100 : null

  return (
    <Page title="个股查询" description="A 股个股与 ETF：行情、走势、估值、业绩与行业"
      actions={d ? <AskAi question={`${d.quote.name}（${d.quote.code}）现在估值怎么样，最近业绩如何？`} /> : undefined}>
      <form onSubmit={search} className="flex max-w-md items-end gap-2">
        <div className="flex-1"><Input id="stock-code" label="股票代码" placeholder="如 600519、000858、510300" value={draft} onChange={(e) => setDraft(e.target.value)} /></div>
        <Button type="submit" className="h-10" loading={state.loading} disabled={!draft.trim()}>查询</Button>
      </form>

      <DataState loading={state.loading && !d} error={state.error} empty={!code ? '输入 6 位 A 股代码开始查询。' : undefined}>
        {d ? (
          <>
            <div>
              <h2 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[22px] font-semibold tracking-[-0.2px] text-ink">
                {d.quote.name}<span className="font-mono text-base font-normal text-stone">{d.quote.code}</span>
                {d.profile?.industry ? <Tag tone="purple">{d.profile.industry}</Tag> : null}
                {d.profile?.listing_board ? <Tag>{d.profile.listing_board}</Tag> : null}
              </h2>
              <div className="mt-3">
                <Metrics>
                  <Metric label="现价（元）" value={num(d.quote.price)} tone={signClass(d.quote.change_pct)} hint={`${signed(d.quote.change)} · ${signed(d.quote.change_pct, 2, '%')}`} />
                  <Metric label="PE（TTM）" value={num(d.quote.pe_ttm)} hint="滚动市盈率" />
                  <Metric label="PB" value={num(d.quote.pb)} hint="市净率" />
                  <Metric label="总市值（亿元）" value={num(d.quote.total_mv_yi, 0)} />
                  <Metric label="成交额（亿元）" value={num(d.quote.amount_yi)} hint={d.quote.turnover_pct == null ? undefined : `换手 ${d.quote.turnover_pct}%`} />
                </Metrics>
              </div>
              <p className="mt-2 text-[13px] text-steel">行情时间 {d.quote.quote_time}</p>
            </div>

            <Section title="日线走势" hint={d.kline.length ? `前复权收盘价 · ${d.kline[0].nav_date} 至 ${d.kline[d.kline.length - 1].nav_date} · 区间 ${signed(periodReturn, 2, '%')}` : undefined}
              actions={<Segmented value={days} onChange={(v) => void changeRange(v)} options={RANGES} />}>
              <DataState empty={d.kline.length === 0 ? '没有取到日线数据' : undefined}>
                <div className="h-[280px] rounded-lg border border-hairline p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={d.kline} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
                      <XAxis dataKey="nav_date" tick={{ fill: 'var(--steel)', fontSize: 11 }} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={48} tickFormatter={(v: string) => v.slice(5)} />
                      <YAxis domain={['auto', 'auto']} tick={{ fill: 'var(--steel)', fontSize: 11 }} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => v.toFixed(v >= 100 ? 0 : 2)} />
                      <Tooltip formatter={(v) => [Number(v).toFixed(2), '收盘（前复权）']} labelStyle={{ color: 'var(--steel)' }}
                        contentStyle={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }} />
                      <Line type="monotone" dataKey="nav" stroke="var(--primary)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </DataState>
              {range?.range_position_pct != null ? (
                <div className="mt-4 max-w-[560px]">
                  <div className="flex justify-between text-[13px] text-steel"><span>近一年最低 {num(range.period_low)}</span><span>近一年最高 {num(range.period_high)}</span></div>
                  <div className="relative mt-1.5 h-2 rounded-full bg-surface">
                    <span className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${range.range_position_pct}%` }} />
                  </div>
                  <p className="mt-2 text-[13px] text-slate">当前价位于近一年价格区间的 <b className="text-ink">{range.range_position_pct}%</b> 位置。这是价格所处的位置，不是估值分位。</p>
                </div>
              ) : null}
            </Section>

            <Section title="业绩" hint="金额单位亿元；各期为累计值（如 06-30 是上半年合计）；同比为相对上年同期">
              <DataState empty={d.reports.length === 0 ? '没有取到业绩报表' : undefined}>
                <Table minWidth={720} head={[{ label: '报告期' }, { label: '营收', right: true }, { label: '营收同比', right: true }, { label: '归母净利润', right: true }, { label: '净利同比', right: true }, { label: 'ROE', right: true }, { label: '毛利率', right: true }, { label: '每股收益', right: true }]}>
                  {d.reports.map((r) => (
                    <tr key={r.report_date}>
                      <Td className="font-mono text-[13px]">{r.report_date}</Td>
                      <Td right num>{num(r.revenue_yi)}</Td>
                      <Td right num className={signClass(r.revenue_yoy_pct)}>{signed(r.revenue_yoy_pct, 2, '%')}</Td>
                      <Td right num>{num(r.net_profit_yi)}</Td>
                      <Td right num className={signClass(r.net_profit_yoy_pct)}>{signed(r.net_profit_yoy_pct, 2, '%')}</Td>
                      <Td right num>{r.roe_pct == null ? '—' : `${r.roe_pct}%`}</Td>
                      <Td right num>{r.gross_margin_pct == null ? '—' : `${r.gross_margin_pct}%`}</Td>
                      <Td right num>{num(r.eps)}</Td>
                    </tr>
                  ))}
                </Table>
              </DataState>
            </Section>
            <Callout tone="neutral">财报是滞后数据：最新一期业绩反映的是报告期当时的经营情况，不代表现在。行情与估值来自腾讯行情，业绩与行业来自东方财富。</Callout>
          </>
        ) : null}
      </DataState>
    </Page>
  )
}

export default StockPage
