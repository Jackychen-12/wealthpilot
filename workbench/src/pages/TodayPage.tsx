import type React from 'react'
import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { DEMO, api, runTool, useApi, type MarketOverview, type SectorRanking } from '../api'
import { Heatmap } from '../components/charts'
import { securityPath } from '../components/SecuritySearch'
import { Button, Callout, Tag, type Tone } from '../components/kit'
import { ASSET, DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'
import { cn } from '../utils/cn'
import { PLAYBOOK, STATUS } from './ResearchPage'

const EVENT: Record<string, { label: string; tone: Tone }> = {
  checkpoint: { label: '验证点', tone: 'purple' }, report: { label: '新财报', tone: 'blue' }, filing: { label: '公告', tone: 'yellow' },
  valuation: { label: '估值', tone: 'orange' }, move: { label: '异动', tone: 'pink' }, proposal: { label: '待办', tone: 'green' }, sync: { label: '同步', tone: 'gray' },
}
const More: React.FC<{ to: string; children: React.ReactNode }> = ({ to, children }) => (
  <Link to={to} className="inline-flex items-center gap-1 text-[13px] text-steel hover:text-ink">{children}<ArrowRight className="h-3.5 w-3.5" /></Link>
)
const toolData = <T,>(res: { data: T | string } | null): T | null => (res && typeof res.data !== 'string' ? res.data : null)

/** 首页：一屏看到大盘、板块、自选、持仓、预警和最近的研究。 */
const TodayPage: React.FC = () => {
  const navigate = useNavigate()
  const market = useApi(() => runTool<MarketOverview | string>('get_market_overview'))
  const sectors = useApi(() => runTool<SectorRanking | string>('get_sector_ranking', { top: 20 }))
  const watch = useApi(api.watchlist)
  const holdings = useApi(api.holdings)
  const alerts = useApi(api.alerts)
  const history = useApi(api.researchHistory)
  const digests = useApi(api.digests)
  const [running, setRunning] = useState(false)
  const [digestError, setDigestError] = useState('')
  const latest = digests.data?.[0]
  const runDigest = async () => {
    setRunning(true); setDigestError('')
    try { await api.runDigest(); digests.reload() } catch (e) { setDigestError(e instanceof Error ? e.message : '检查失败') } finally { setRunning(false) }
  }

  const m = toolData(market.data)
  const s = toolData(sectors.data)
  const rows = holdings.data ?? []
  const total = rows.reduce((sum, h) => sum + (h.market_value ?? 0), 0)
  const cost = rows.reduce((sum, h) => sum + h.shares * h.cost_price, 0)
  const totalReturn = rows.reduce((sum, h) => sum + (h.total_return ?? 0), 0)
  const stockValue = rows.filter((h) => h.asset_type === 'stock' || h.asset_type === 'etf').reduce((sum, h) => sum + (h.market_value ?? 0), 0)
  const fresh = !watch.loading && !holdings.loading && !watch.data?.length && rows.length === 0

  return (
    <Page title="今日" description="大盘与板块、自选、持仓和最近的研究">
      {fresh ? (
        <Callout tone="info" title="从这里开始">
          按 <kbd className="rounded-xs border border-current/30 px-1 font-mono text-xs">/</kbd> 搜索一只股票加入自选，或去<Link className="mx-1 font-medium underline underline-offset-2" to="/holdings">持仓</Link>录入你的股票和基金；
          也可以直接到<Link className="mx-1 font-medium underline underline-offset-2" to="/research">AI 研究</Link>提问。
        </Callout>
      ) : null}

      <Section title="今日简报" hint={latest ? `${latest.day} · ${latest.summary}` : '交易日收盘后自动生成：验证点核对、新财报、重要公告、估值跨档、大涨大跌'}
        actions={DEMO ? undefined : <Button size="xs" variant="secondary" loading={running} onClick={() => void runDigest()}>立即检查</Button>}>
        <DataState loading={digests.loading} error={digests.error || digestError} onRetry={digests.reload}
          empty={!latest ? '还没有简报。后端开着时每个交易日会自动跑一次，也可以点「立即检查」。' : latest.events.length === 0 ? `${latest.summary}。` : undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {(latest?.events ?? []).map((e, i) => (
              <li key={i} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                <Tag tone={EVENT[e.kind]?.tone ?? 'gray'}>{EVENT[e.kind]?.label ?? e.kind}</Tag>
                {e.code ? <Link to={`/stock/${e.code}`} className="shrink-0 font-medium text-ink hover:underline">{e.name}</Link> : null}
                <span className="min-w-0 text-charcoal">{e.text}</span>
              </li>
            ))}
          </ul>
        </DataState>
      </Section>

      <Section title="大盘" hint={m ? `涨跌家数截至 ${m.breadth.trade_date} 收盘` : undefined}>
        <DataState loading={market.loading} error={market.error} onRetry={market.reload} empty={!market.loading && !m ? String(market.data?.data ?? '没有取到大盘数据') : undefined}>
          {m ? (
            <Metrics>
              {m.indices.map((i) => <Metric key={i.name} label={i.name} value={i.value} tone={i.up ? 'text-up' : 'text-down'} hint={i.change} />)}
              <Metric label="上涨 / 下跌（家）" value={<><span className="text-up">{m.breadth.up}</span><span className="mx-1.5 text-stone">/</span><span className="text-down">{m.breadth.down}</span></>}
                hint={`涨跌中位数 ${signed(m.breadth.median_change_pct, 2, '%')} · 平 ${m.breadth.flat}`} />
            </Metrics>
          ) : null}
        </DataState>
      </Section>

      <Section title="行业强弱" hint={s ? `行业内个股涨跌幅的中位数 · ${s.trade_date}` : undefined} actions={<More to="/screener">去选股</More>}>
        <DataState loading={sectors.loading} error={sectors.error} onRetry={sectors.reload} empty={!sectors.loading && !s ? String(sectors.data?.data ?? '没有取到行业数据') : undefined}>
          {s ? (
            <>
              <Heatmap items={[...s.top, ...s.bottom].map((x) => ({ name: x.industry, size: x.stock_count, change: x.median_change_pct, sub: x.leader.name, code: x.leader.code }))}
                onPick={(i) => i.code && navigate(`/stock/${i.code}`)} />
              <p className="mt-2 text-[13px] text-steel">块越大行业里的公司越多，颜色越深涨跌越大（红涨绿跌）；只画了涨跌幅最靠前和最靠后的行业，点一块看它的领涨股。</p>
            </>
          ) : null}
        </DataState>
      </Section>

      <div className="grid gap-10 lg:grid-cols-2">
        <Section title="自选股" actions={<More to="/watchlist">全部</More>}>
          <DataState loading={watch.loading} error={watch.error} onRetry={watch.reload} empty={watch.data?.length === 0 ? '还没有自选。搜索一只股票，在详情页点「加自选」。' : undefined}>
            <Table minWidth={320} head={[{ label: '名称' }, { label: '最新价', right: true }, { label: '涨跌幅', right: true }]}>
              {(watch.data ?? []).slice(0, 6).map((w) => (
                <tr key={w.id} className="cursor-pointer hover:bg-surface-soft" onClick={() => navigate(securityPath(w))}>
                  <Td><span className="font-medium text-ink">{w.name}</span><span className="ml-2 font-mono text-xs text-stone">{w.code}</span></Td>
                  <Td right num>{w.price == null ? '—' : w.price.toFixed(2)}</Td>
                  <Td right num className={signClass(w.change_pct)}>{signed(w.change_pct, 2, '%')}</Td>
                </tr>
              ))}
            </Table>
          </DataState>
        </Section>

        <Section title="我的持仓" hint={rows.length ? `共 ${rows.length} 项 · 股票与 ETF 占 ${total ? ((stockValue / total) * 100).toFixed(0) : 0}%` : undefined} actions={<More to="/holdings">全部</More>}>
          <DataState loading={holdings.loading} error={holdings.error} onRetry={holdings.reload} empty={rows.length === 0 ? '还没有持仓。录入后这里显示市值与盈亏。' : undefined}>
            <div className="mb-3 flex items-baseline gap-6">
              <div><p className="text-[13px] text-steel">总市值（元）</p><p className="text-[22px] font-semibold tabular-nums text-ink">{yuan(total)}</p></div>
              <div><p className="text-[13px] text-steel">累计收益（元）</p><p className={cn('text-[22px] font-semibold tabular-nums', signClass(totalReturn))}>{signed(totalReturn, 0)}<span className="ml-2 text-sm font-normal">{cost ? signed((totalReturn / cost) * 100, 2, '%') : ''}</span></p></div>
            </div>
            <Heatmap height={200} limit={20} items={rows.map((h) => ({ name: h.fund_name, size: h.market_value ?? 0, change: h.return_pct, code: h.fund_code, sub: ASSET[h.asset_type] }))}
              onPick={(i) => { const h = rows.find((x) => x.fund_code === i.code); if (h) navigate(securityPath({ code: h.fund_code, asset_type: h.asset_type })) }} />
            <p className="mt-2 text-[13px] text-steel">块的大小是市值，颜色是持有收益率。</p>
          </DataState>
        </Section>
      </div>

      {alerts.data?.alerts.length ? (
        <Section title="预警" hint={`共 ${alerts.data.alerts.length} 条`} actions={<More to="/risk">风险体检</More>}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {alerts.data.alerts.slice(0, 4).map((a, i) => (
              <li key={a.id ?? i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <Tag tone={a.severity === 'high' ? 'pink' : 'yellow'}>{a.fund_name}</Tag>
                <span className="min-w-0 text-charcoal">{a.message}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="最近的研究" actions={<More to="/history">全部记录</More>}>
        <DataState loading={history.loading} error={history.error} onRetry={history.reload}
          empty={history.data?.length === 0 ? '还没有研究记录。' : undefined} emptyAction={<More to="/research">去提问</More>}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {(history.data ?? []).slice(0, 5).map((r) => (
              <li key={r.id}>
                <Link to={`/history/${r.id}`} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-soft">
                  <span className="min-w-0 flex-1 truncate text-ink">{r.question || '（问题未记录）'}</span>
                  {PLAYBOOK[r.playbook] ? <Tag tone="purple">{PLAYBOOK[r.playbook]}</Tag> : null}
                  {STATUS[r.status] ? <Tag tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Tag> : null}
                  <span className="hidden shrink-0 font-mono text-xs text-stone sm:block">{r.created_at.slice(0, 10)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </DataState>
      </Section>
    </Page>
  )
}

export default TodayPage
