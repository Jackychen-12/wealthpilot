import type React from 'react'
import { useState } from 'react'
import { Star } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  DEMO, api, runTool, useApi, type Announcement, type Dividend, type Indicator, type PeerValuation, type Peers,
  type StockProfile, type StockQuote, type StockValuation, type Technicals, type ValuationBand, type ValuationHistory,
} from '../api'
import { AskAi } from '../components/AskAi'
import { SecuritySearch, securityPath } from '../components/SecuritySearch'
import { DEMO_DEFAULTS } from '../demo/defaults'
import { Button, Callout, Segmented, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed } from '../components/ui'
import { cn } from '../utils/cn'

const RANGES = [['21', '近 1 月'], ['63', '近 3 月'], ['125', '近半年'], ['250', '近 1 年']] as const
const TABS = [['overview', '概览与走势'], ['financials', '财务'], ['valuation', '估值'], ['peers', '同行'], ['news', '公告']] as const
const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toFixed(digits))
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v}%`)
const TOOLTIP = { background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }
const AXIS = { fill: 'var(--steel)', fontSize: 11 }

/**
 * 调一个只读工具。工具返回字符串表示"没取到"（原样当作空状态的说明），返回对象才是数据。
 * 这些工具就是 Agent 用的那一批，页面上的数和 AI 引用的证据对得上。
 */
function useTool<T>(name: string, code: string, extra: Record<string, unknown> = {}) {
  const res = useApi(() => runTool<T | string>(name, { code, ...extra }), [name, code])
  const missing = typeof res.data?.data === 'string' ? res.data.data : ''
  return { ...res, value: res.data && !missing ? (res.data.data as T) : null, missing }
}

const StockPage: React.FC = () => {
  const code = useParams().code ?? ''
  const navigate = useNavigate()
  return (
    <Page title="个股" description="A 股个股与 ETF：行情走势、财务、估值分位、同行与公告">
      <div className="flex flex-wrap items-center gap-3">
        <SecuritySearch className="w-full max-w-sm" placeholder="输入名称或代码，如 宁德时代、600519" onPick={(s) => navigate(securityPath(s))} />
        {DEMO && !code ? <Button size="sm" variant="secondary" onClick={() => navigate(`/stock/${DEMO_DEFAULTS.stock}`)}>查看示例：贵州茅台</Button> : null}
      </div>
      {code ? <StockDetail key={code} code={code} /> : <DataState empty="搜索一只股票或 ETF 开始。也可以随时按 / 唤起左上角的搜索。">{null}</DataState>}
    </Page>
  )
}

const StockDetail: React.FC<{ code: string }> = ({ code }) => {
  const [tab, setTab] = useState('overview')
  const quote = useTool<StockQuote>('get_stock_quote', code)
  const profile = useTool<StockProfile>('get_stock_profile', code)
  const watch = useApi(api.watchlist)
  const [watchMsg, setWatchMsg] = useState('')
  const q = quote.value
  const watched = watch.data?.some((w) => w.code === code) ?? false

  const addWatch = async () => {
    if (!q) return
    try {
      await api.addWatch({ code, name: q.name, asset_type: 'stock' })
      setWatchMsg('')
      watch.reload()
    } catch (e) {
      setWatchMsg(e instanceof Error ? e.message : '加自选失败')
    }
  }

  return (
    <DataState loading={quote.loading} error={quote.error || quote.missing} onRetry={quote.reload}>
      {q ? (
        <>
          <div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h2 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[22px] font-semibold tracking-[-0.2px] text-ink">
                {q.name}<span className="font-mono text-base font-normal text-stone">{q.code}</span>
                {profile.value?.industry ? <Tag tone="purple">{profile.value.industry}</Tag> : null}
                {profile.value?.listing_board ? <Tag>{profile.value.listing_board}</Tag> : null}
              </h2>
              <div className="flex items-center gap-2">
                {watched
                  ? <Link to="/watchlist" className="inline-flex h-8 items-center gap-1.5 px-2 text-sm text-steel hover:text-ink"><Star className="h-3.5 w-3.5 fill-current" />已在自选</Link>
                  : <Button size="sm" variant="secondary" onClick={() => void addWatch()}><Star className="h-3.5 w-3.5" />加自选</Button>}
                <AskAi label="深度研究" question={`帮我深度分析一下${q.name}（${q.code}）`} />
              </div>
            </div>
            {watchMsg ? <p className="mt-2 text-[13px] text-on-rose">{watchMsg}</p> : null}
            <div className="mt-3">
              <Metrics>
                <Metric label="现价（元）" value={num(q.price)} tone={signClass(q.change_pct)} hint={`${signed(q.change)} · ${signed(q.change_pct, 2, '%')}`} />
                <Metric label="PE（TTM）" value={num(q.pe_ttm)} hint="滚动市盈率" />
                <Metric label="PB" value={num(q.pb)} hint="市净率" />
                <Metric label="总市值（亿元）" value={num(q.total_mv_yi, 0)} />
                <Metric label="成交额（亿元）" value={num(q.amount_yi)} hint={q.turnover_pct == null ? undefined : `换手 ${q.turnover_pct}%`} />
              </Metrics>
            </div>
            <p className="mt-2 text-[13px] text-steel">行情时间 {q.quote_time}</p>
          </div>

          <div className="border-b border-hairline"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
          {tab === 'overview' ? <OverviewTab code={code} /> : null}
          {tab === 'financials' ? <FinancialsTab code={code} /> : null}
          {tab === 'valuation' ? <ValuationTab code={code} /> : null}
          {tab === 'peers' ? <PeersTab code={code} /> : null}
          {tab === 'news' ? <NewsTab code={code} /> : null}
        </>
      ) : null}
    </DataState>
  )
}

const OverviewTab: React.FC<{ code: string }> = ({ code }) => {
  const [days, setDays] = useState('125')
  const kline = useApi(() => api.stockKline(code, Number(days)), [code, days])
  const valuation = useTool<StockValuation>('get_stock_valuation', code)
  const tech = useTool<Technicals>('get_technical_indicators', code)
  const points = kline.data ? [...kline.data.data].reverse() : []
  const first = points[0]?.nav
  const last = points[points.length - 1]?.nav
  const periodReturn = first && last ? ((last - first) / first) * 100 : null
  const range = valuation.value?.price_range_1y
  const t = tech.value

  return (
    <>
      <Section title="日线走势" hint={points.length ? `前复权收盘价 · ${points[0].nav_date} 至 ${points[points.length - 1].nav_date} · 区间 ${signed(periodReturn, 2, '%')}` : undefined}
        actions={<Segmented value={days} onChange={setDays} options={RANGES} />}>
        <DataState loading={kline.loading && !points.length} error={kline.error} onRetry={kline.reload} empty={!kline.loading && points.length === 0 ? '没有取到日线数据' : undefined}>
          <div className="h-[280px] rounded-lg border border-hairline p-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
                <XAxis dataKey="nav_date" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={48} tickFormatter={(v: string) => v.slice(5)} />
                <YAxis domain={['auto', 'auto']} tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => v.toFixed(v >= 100 ? 0 : 2)} />
                <Tooltip formatter={(v) => [Number(v).toFixed(2), '收盘（前复权）']} labelStyle={{ color: 'var(--steel)' }} contentStyle={TOOLTIP} />
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
            <p className="mt-2 text-[13px] text-slate">当前价位于近一年价格区间的 <b className="text-ink">{range.range_position_pct}%</b> 位置。这是价格所处的位置，不是估值分位（估值分位见「估值」页）。</p>
          </div>
        ) : null}
      </Section>

      <Section title="均线与波动" hint={t ? `截至 ${t.as_of} · 前复权收盘价` : undefined}>
        <DataState loading={tech.loading} error={tech.error} empty={tech.missing || undefined} onRetry={tech.reload}>
          {t ? (
            <>
              <Metrics>
                <Metric label="MA5" value={num(t.ma5)} />
                <Metric label="MA20" value={num(t.ma20)} hint={`现价相对 ${signed(t.vs_ma20_pct, 2, '%')}`} />
                <Metric label="MA60" value={num(t.ma60)} hint={`现价相对 ${signed(t.vs_ma60_pct, 2, '%')}`} />
                <Metric label="20 日年化波动率" value={pct(t.volatility_20d_annualized_pct)} />
              </Metrics>
              <p className="mt-3 text-sm text-slate">均线排列：<b className="text-ink">{t.ma_alignment}</b>。均线只描述已经发生的走势，不构成对后续涨跌的预测。</p>
            </>
          ) : null}
        </DataState>
      </Section>
    </>
  )
}

const FinancialsTab: React.FC<{ code: string }> = ({ code }) => {
  const fin = useTool<{ reports: Indicator[] }>('get_financial_indicators', code)
  const div = useTool<{ dividends: Dividend[] }>('get_dividend_history', code)
  const reports = fin.value?.reports ?? []
  // 各期金额是累计值、口径不同，不能直接连成一条线；同比增速各期可比
  const growth = [...reports].reverse().map((r) => ({ period: r.report_name, 营收同比: r.revenue_yoy_pct, 净利同比: r.net_profit_yoy_pct }))

  return (
    <>
      <Section title="主要财务指标" hint="金额单位亿元；各期为累计值（如中报是上半年合计）；同比为相对上年同期">
        <DataState loading={fin.loading} error={fin.error} onRetry={fin.reload} empty={fin.missing || (!fin.loading && reports.length === 0 ? '没有取到财务指标' : undefined)}>
          <Table minWidth={980} head={[{ label: '报告期' }, { label: '营收', right: true }, { label: '同比', right: true }, { label: '归母净利润', right: true }, { label: '同比', right: true },
            { label: '扣非净利润', right: true }, { label: 'ROE', right: true }, { label: '毛利率', right: true }, { label: '净利率', right: true }, { label: '资产负债率', right: true }, { label: '每股经营现金流', right: true }]}>
            {reports.map((r) => (
              <tr key={r.report_date}>
                <Td><div className="text-ink">{r.report_name}</div><div className="font-mono text-xs text-stone">{r.report_date}</div></Td>
                <Td right num>{num(r.revenue_yi)}</Td>
                <Td right num className={signClass(r.revenue_yoy_pct)}>{signed(r.revenue_yoy_pct, 2, '%')}</Td>
                <Td right num>{num(r.net_profit_yi)}</Td>
                <Td right num className={signClass(r.net_profit_yoy_pct)}>{signed(r.net_profit_yoy_pct, 2, '%')}</Td>
                <Td right num>{num(r.deducted_net_profit_yi)}</Td>
                <Td right num>{pct(r.roe_pct)}</Td>
                <Td right num>{pct(r.gross_margin_pct)}</Td>
                <Td right num>{pct(r.net_margin_pct)}</Td>
                <Td right num>{pct(r.debt_ratio_pct)}</Td>
                <Td right num>{num(r.operating_cashflow_per_share)}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>

      {growth.length > 1 ? (
        <Section title="增速变化" hint="各报告期的同比增速（%），从早到晚">
          <div className="h-[240px] rounded-lg border border-hairline p-3">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={growth} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
                <XAxis dataKey="period" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => `${v}%`} />
                <ReferenceLine y={0} stroke="var(--hairline-strong)" />
                <Tooltip formatter={(v, name) => [`${Number(v).toFixed(2)}%`, name]} labelStyle={{ color: 'var(--steel)' }} contentStyle={TOOLTIP} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="营收同比" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                <Line type="monotone" dataKey="净利同比" stroke="var(--warning)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Section>
      ) : null}

      <Section title="分红记录" hint="股息率为方案公布时按当时股价计算的数值">
        <DataState loading={div.loading} error={div.error} onRetry={div.reload} empty={div.missing || (!div.loading && !div.value?.dividends.length ? '没有取到分红记录' : undefined)}>
          <Table head={[{ label: '报告期' }, { label: '方案' }, { label: '股息率', right: true }, { label: '除权除息日', right: true }]}>
            {(div.value?.dividends ?? []).map((d) => (
              <tr key={`${d.report_date}-${d.plan}`}>
                <Td className="font-mono text-[13px]">{d.report_date}</Td>
                <Td>{d.plan}</Td>
                <Td right num>{pct(d.dividend_yield_pct)}</Td>
                <Td right className="font-mono text-[13px]">{d.ex_dividend_date || '—'}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>
      <Callout tone="neutral">财报是滞后数据：最新一期反映的是报告期当时的经营情况，不代表现在。数据来自东方财富。</Callout>
    </>
  )
}

const Band: React.FC<{ label: string; band: ValuationBand }> = ({ label, band }) => {
  const usable = band.current != null && band.percentile != null && band.min != null && band.max != null
  const tone = band.percentile == null ? 'gray' : band.percentile <= 30 ? 'green' : band.percentile >= 70 ? 'pink' : 'yellow'
  return (
    <div className="rounded-lg border border-hairline p-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-steel">{label}</span>
        {band.percentile != null ? <Tag tone={tone}>历史分位 {band.percentile}%</Tag> : null}
      </div>
      <div className="mt-1 text-[26px] font-semibold tabular-nums tracking-[-0.3px] text-ink">{num(band.current)}</div>
      {usable ? (
        <>
          <div className="relative mt-3 h-2 rounded-full bg-surface">
            <span className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${band.percentile}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-xs tabular-nums text-steel">
            <span>最低 {num(band.min)}</span><span>中位 {num(band.median)}</span><span>最高 {num(band.max)}</span>
          </div>
        </>
      ) : <p className="mt-3 text-[13px] text-steel">{band.note || '没有可用的历史分位（常见于亏损期，市盈率为负）'}</p>}
    </div>
  )
}

const ValuationTab: React.FC<{ code: string }> = ({ code }) => {
  const hist = useTool<ValuationHistory>('get_valuation_history', code)
  const peer = useTool<PeerValuation>('compare_peers_valuation', code)
  const h = hist.value
  const p = peer.value
  return (
    <>
      <Section title="估值历史分位" hint={h ? `${h.window_start} 至 ${h.as_of} · ${h.trading_days} 个交易日` : undefined}>
        <DataState loading={hist.loading} error={hist.error} onRetry={hist.reload} empty={hist.missing || undefined}>
          {h ? (
            <>
              <div className="grid gap-3 md:grid-cols-3">
                <Band label="市盈率 PE（TTM）" band={h.pe} />
                <Band label="市净率 PB" band={h.pb} />
                <Band label="市销率 PS（TTM）" band={h.ps} />
              </div>
              <p className="mt-3 text-[13px] text-steel">分位是当前值在这段时间自身历史里的位置（0% 最便宜，100% 最贵）。只和自己的过去比，不代表绝对便宜或贵——盈利下滑时低分位也可能是合理的。</p>
            </>
          ) : null}
        </DataState>
      </Section>
      <Section title="与同行业比" hint={p ? `${p.industry} · ${p.peer_count} 家 · ${p.as_of}` : undefined}>
        <DataState loading={peer.loading} error={peer.error} onRetry={peer.reload} empty={peer.missing || undefined}>
          {p ? (
            <Metrics>
              <Metric label="行业 PE 中位数" value={num(p.industry_median_pe)} hint="只统计盈利（PE 为正）的公司" />
              <Metric label="PE 由低到高排名" value={p.pe_rank_low_to_high == null ? '—' : `第 ${p.pe_rank_low_to_high}`} hint={`共 ${p.positive_pe_peer_count} 家盈利公司`} />
            </Metrics>
          ) : null}
        </DataState>
      </Section>
    </>
  )
}

const PeersTab: React.FC<{ code: string }> = ({ code }) => {
  const peers = useTool<Peers>('get_industry_peers', code)
  const p = peers.value
  return (
    <Section title="同行业公司" hint={p ? `${p.industry} · 共 ${p.peer_count} 家，按总市值排序${p.mv_rank ? ` · 本公司市值排第 ${p.mv_rank}` : ''} · ${p.as_of}` : undefined}>
      <DataState loading={peers.loading} error={peers.error} onRetry={peers.reload} empty={peers.missing || undefined}>
        <Table head={[{ label: '公司' }, { label: '总市值（亿元）', right: true }, { label: 'PE（TTM）', right: true }, { label: 'PB', right: true }, { label: '当日涨跌', right: true }]}>
          {(p?.peers ?? []).map((x) => (
            <tr key={x.code} className={cn(x.code === code && 'bg-surface-soft')}>
              <Td>
                <Link to={`/stock/${x.code}`} className="font-medium text-ink hover:underline">{x.name}</Link>
                <span className="ml-2 font-mono text-xs text-stone">{x.code}</span>
                {x.code === code ? <Tag tone="purple" className="ml-2 !py-0">当前</Tag> : null}
              </Td>
              <Td right num>{num(x.total_mv_yi, 0)}</Td>
              <Td right num>{num(x.pe_ttm)}</Td>
              <Td right num>{num(x.pb)}</Td>
              <Td right num className={signClass(x.change_pct)}>{signed(x.change_pct, 2, '%')}</Td>
            </tr>
          ))}
        </Table>
      </DataState>
    </Section>
  )
}

const NewsTab: React.FC<{ code: string }> = ({ code }) => {
  const ann = useTool<{ announcements: Announcement[] }>('get_stock_announcements', code)
  const list = ann.value?.announcements ?? []
  return (
    <Section title="公司公告" hint="来自东方财富公告，点标题看原文">
      <DataState loading={ann.loading} error={ann.error} onRetry={ann.reload} empty={ann.missing || (!ann.loading && list.length === 0 ? '没有取到公告' : undefined)}>
        <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
          {list.map((a) => (
            <li key={a.url} className="flex items-baseline gap-4 px-4 py-2.5">
              <span className="shrink-0 font-mono text-xs text-stone">{a.date}</span>
              <a href={a.url} target="_blank" rel="noreferrer" className="min-w-0 text-sm text-charcoal hover:text-ink hover:underline">{a.title}</a>
            </li>
          ))}
        </ul>
      </DataState>
    </Section>
  )
}

export default StockPage
