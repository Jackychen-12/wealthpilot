import type React from 'react'
import { useState } from 'react'
import { ArrowRight, ArrowUp } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { DEMO, api, runTool, useApi, type DeskStock, type MarketOverview, type Mover, type SectorRanking } from '../api'
import { research } from '../api/researchStore'
import { CP_STATUS } from '../components/Checkpoints'
import { Heatmap } from '../components/charts'
import { securityPath } from '../components/SecuritySearch'
import { Button, Callout, Tag, type Tone } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed } from '../components/ui'
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

/** 一个待办数字：点了就去处理它的地方。没有待办时变灰，不抢注意力。 */
const Todo: React.FC<{ to: string; count: number; label: string; hint: string; tone: string }> = ({ to, count, label, hint, tone }) => (
  <Link to={to} className={cn('min-w-0 flex-1 rounded-lg border border-hairline px-4 py-3 transition-colors hover:bg-surface-soft', count === 0 && 'opacity-60')}>
    <p className="text-[13px] text-steel">{label}</p>
    <p className={cn('mt-0.5 text-[26px] font-semibold leading-tight tabular-nums', count > 0 ? tone : 'text-ink')}>{count}</p>
    <p className="mt-0.5 truncate text-[13px] text-steel">{hint}</p>
  </Link>
)

const Percentile: React.FC<{ value: number | null }> = ({ value }) => (value == null ? <span className="text-stone">—</span> : (
  <span className="inline-flex items-center gap-2">
    <span className="relative h-1.5 w-14 rounded-full bg-surface"><span className="absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${value}%` }} /></span>
    <span className="w-9 text-right tabular-nums">{value}%</span>
  </span>
))

const MoverList: React.FC<{ title: string; rows: Mover[] }> = ({ title, rows }) => (
  <div className="min-w-0 flex-1 rounded-lg border border-hairline">
    <p className="border-b border-hairline-soft px-4 py-2 text-[13px] font-medium text-steel">{title}</p>
    <ul className="divide-y divide-hairline-soft">
      {rows.map((m) => (
        <li key={m.code}>
          <Link to={`/stock/${m.code}`} className="flex items-center gap-3 px-4 py-1.5 text-sm hover:bg-surface-soft">
            <span className="min-w-0 flex-1 truncate text-ink">{m.name}<span className="ml-2 text-xs text-stone">{m.industry}</span></span>
            <span className={cn('w-16 shrink-0 text-right tabular-nums', signClass(m.change_pct))}>{signed(m.change_pct, 2, '%')}</span>
          </Link>
        </li>
      ))}
    </ul>
  </div>
)

/**
 * 首页是"你的分析师的工作台"，不是行情软件的首页：
 * 先讲有什么等你处理、你的每只股票现在怎么样、当初的判断还成立几条；大盘和板块放在后面。
 */
const TodayPage: React.FC = () => {
  const navigate = useNavigate()
  const desk = useApi(api.desk)
  const market = useApi(() => runTool<MarketOverview | string>('get_market_overview'))
  const sectors = useApi(() => runTool<SectorRanking | string>('get_sector_ranking', { top: 20 }))
  const movers = useApi(api.movers)
  const history = useApi(api.researchHistory)
  const [draft, setDraft] = useState('')
  const [running, setRunning] = useState(false)
  const [digestError, setDigestError] = useState('')

  const d = desk.data
  const m = toolData(market.data)
  const s = toolData(sectors.data)
  const events = (d?.digest?.events ?? []).filter((e) => e.kind !== 'sync')
  const ask = (q: string) => { if (!q.trim() || research.busy) return; void research.ask(q.trim()); navigate('/research') }
  const study = (x: DeskStock) => ask(`帮我深度分析一下${x.name}（${x.code}）`)
  const runDigest = async () => {
    setRunning(true); setDigestError('')
    try { await api.runDigest(); desk.reload() } catch (e) { setDigestError(e instanceof Error ? e.message : '检查失败') } finally { setRunning(false) }
  }

  return (
    <Page title="今日" description="有什么等你处理，你的股票现在怎么样，当初的判断还成立几条">
      <form onSubmit={(e) => { e.preventDefault(); ask(draft) }}
        className="flex items-center gap-2 rounded-xl border border-hairline-strong bg-canvas p-2 shadow-subtle focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={DEMO} aria-label="向 AI 提问"
          placeholder={DEMO ? '在线演示不能提问，去「AI 研究」回放录好的研究' : '问点什么：帮我分析一下宁德时代 / 我的持仓有什么风险 / 复盘一下之前的判断'}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[15px] text-ink outline-none placeholder:text-stone" />
        <Button type="submit" size="sm" disabled={DEMO || !draft.trim()}><ArrowUp className="h-4 w-4" />研究</Button>
      </form>

      <DataState loading={desk.loading && !d} error={desk.error} onRetry={desk.reload}>
        {d ? (
          <>
            {d.stocks.length === 0 ? (
              <Callout tone="info" title="从这里开始">
                按 <kbd className="rounded-xs border border-current/30 px-1 font-mono text-xs">/</kbd> 搜一只股票加入自选，或去<Link className="mx-1 font-medium underline underline-offset-2" to="/holdings">持仓</Link>录入你的股票和基金。
                之后这里会每天告诉你：它们发生了什么、当初的判断还成立几条。
              </Callout>
            ) : (
              <div className="flex flex-col gap-3 sm:flex-row">
                <Todo to="/review" count={d.todo.proposals} label="等你决定的建议" hint="逐条授权才会执行" tone="text-primary" />
                <Todo to="/review" count={d.todo.broken} label="被证伪的判断" hint="当初的结论需要重看" tone="text-up" />
                <Todo to="/review" count={d.todo.pending} label="待核对的验证点" hint="到期后自动核对" tone="text-ink" />
                <Todo to="/watchlist" count={d.todo.unresearched} label="还没研究过的" hint="自选或持仓里没做过研究的" tone="text-ink" />
              </div>
            )}

            {d.stocks.length > 0 ? (
              <Section title="我的股票" hint="持仓与自选。需要处理的排在前面" actions={<><More to="/holdings">持仓</More><More to="/watchlist">自选</More></>}>
                <Table minWidth={940} head={[{ label: '股票' }, { label: '最新价', right: true }, { label: '今日', right: true }, { label: '持有收益', right: true }, { label: 'PE 历史分位' }, { label: '当初的判断' }, { label: '最近研究' }, { label: '' }]}>
                  {d.stocks.map((x) => (
                    <tr key={x.code}>
                      <Td>
                        <Link to={securityPath(x)} className="font-medium text-ink hover:underline">{x.name}</Link>
                        <span className="ml-2 font-mono text-xs text-stone">{x.code}</span>
                        {x.held ? <Tag tone="purple" className="ml-2 !py-0">持有</Tag> : null}
                      </Td>
                      <Td right num>{x.price == null ? '—' : x.price.toFixed(x.price < 10 ? 3 : 2)}</Td>
                      <Td right num className={signClass(x.change_pct)}>{signed(x.change_pct, 2, '%')}</Td>
                      <Td right num className={signClass(x.return_pct)}>{x.return_pct == null ? '—' : signed(x.return_pct, 2, '%')}</Td>
                      <Td><Percentile value={x.pe_percentile} /></Td>
                      <Td className="whitespace-nowrap text-[13px]">
                        {x.checkpoints.broken ? <Tag tone="pink" className="mr-1 !py-0">证伪 {x.checkpoints.broken}</Tag> : null}
                        {x.checkpoints.held ? <Tag tone="green" className="mr-1 !py-0">成立 {x.checkpoints.held}</Tag> : null}
                        {x.checkpoints.pending ? <span className="text-steel">待核对 {x.checkpoints.pending}</span> : null}
                        {!x.checkpoints.broken && !x.checkpoints.held && !x.checkpoints.pending ? <span className="text-stone">—</span> : null}
                      </Td>
                      <Td className="whitespace-nowrap text-[13px]">
                        {x.last_research ? <Link to={`/history/${x.last_research.id}`} className="text-steel hover:text-ink hover:underline">{x.last_research.date}</Link> : <span className="text-stone">没研究过</span>}
                      </Td>
                      <Td right className="whitespace-nowrap">
                        {x.open_proposals ? <Link to="/review" className="mr-2 text-[13px] font-medium text-primary hover:underline">{x.open_proposals} 条建议</Link> : null}
                        {x.asset_type === 'stock' ? <Button size="xs" variant={x.last_research ? 'ghost' : 'secondary'} disabled={DEMO || research.busy} onClick={() => study(x)}>{x.last_research ? '重新研究' : '研究'}</Button> : null}
                      </Td>
                    </tr>
                  ))}
                </Table>
                <p className="mt-2 text-[13px] text-steel">PE 分位来自最近一次盯盘（0% 最便宜）；「当初的判断」是此前研究设下的验证点现在的状态。</p>
              </Section>
            ) : null}

            <Section title="今天发生了什么" hint={d.digest ? `${d.digest.day} · ${d.digest.summary}` : '交易日收盘后自动检查：新财报、重要公告、估值跨档、大涨大跌、验证点核对'}
              actions={DEMO ? undefined : <Button size="xs" variant="secondary" loading={running} onClick={() => void runDigest()}>立即检查</Button>}>
              <DataState error={digestError}
                empty={!d.digest ? '还没有检查过。后端开着时每个交易日会自动跑一次，也可以点「立即检查」。' : events.length === 0 ? `${d.digest.summary}。` : undefined}>
                <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
                  {events.map((e, i) => (
                    <li key={i} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                      <Tag tone={EVENT[e.kind]?.tone ?? 'gray'}>{EVENT[e.kind]?.label ?? e.kind}</Tag>
                      {e.code ? <Link to={`/stock/${e.code}`} className="shrink-0 font-medium text-ink hover:underline">{e.name}</Link> : null}
                      <span className="min-w-0 text-charcoal">{e.text}</span>
                    </li>
                  ))}
                </ul>
              </DataState>
            </Section>

            {d.verified_recent.length > 0 ? (
              <Section title="最近核对出结果的判断" actions={<More to="/review">验证与复盘</More>}>
                <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
                  {d.verified_recent.map((c) => (
                    <li key={c.id} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                      <Tag tone={CP_STATUS[c.status]?.tone}>{CP_STATUS[c.status]?.label}</Tag>
                      <Link to={`/stock/${c.code}`} className="shrink-0 font-medium text-ink hover:underline">{c.name}</Link>
                      <span className="min-w-0 text-charcoal">{c.metric_label} {c.op === '>=' ? '≥' : '≤'} {c.threshold}%，实际 {c.actual_value}%（{c.actual_as_of}）</span>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
          </>
        ) : null}
      </DataState>

      <Section title="市场" hint={m ? `截至 ${m.breadth.trade_date} 收盘` : undefined} actions={<More to="/screener">选股器</More>}>
        <DataState loading={market.loading} error={market.error} onRetry={market.reload} empty={!market.loading && !m ? String(market.data?.data ?? '没有取到大盘数据') : undefined}>
          {m ? (
            <Metrics>
              {m.indices.map((i) => <Metric key={i.name} label={i.name} value={i.value} tone={i.up ? 'text-up' : 'text-down'} hint={i.change} />)}
              <Metric label="上涨 / 下跌（家）" value={<><span className="text-up">{m.breadth.up}</span><span className="mx-1.5 text-stone">/</span><span className="text-down">{m.breadth.down}</span></>}
                hint={`涨跌中位数 ${signed(m.breadth.median_change_pct, 2, '%')}`} />
            </Metrics>
          ) : null}
        </DataState>
        {s ? (
          <div className="mt-3">
            <Heatmap items={[...s.top, ...s.bottom].map((x) => ({ name: x.industry, size: x.stock_count, change: x.median_change_pct, sub: x.leader.name, code: x.leader.code }))}
              onPick={(i) => i.code && navigate(`/stock/${i.code}`)} />
            <p className="mt-2 text-[13px] text-steel">行业热力图：块越大公司越多，颜色越深涨跌越大（红涨绿跌）；只画涨跌幅最靠前和最靠后的行业，点一块看它的领涨股。</p>
          </div>
        ) : null}
        {movers.data?.gainers.length ? (
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <MoverList title={`涨幅榜（市值 ${movers.data.min_mv_yi} 亿以上）`} rows={movers.data.gainers} />
            <MoverList title="跌幅榜" rows={movers.data.losers} />
          </div>
        ) : null}
      </Section>

      <Section title="最近的研究" actions={<More to="/history">全部记录</More>}>
        <DataState loading={history.loading} error={history.error} onRetry={history.reload} empty={history.data?.length === 0 ? '还没有研究记录。' : undefined}>
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
