import type React from 'react'
import { useState } from 'react'
import { ArrowRight, ArrowUp, Check } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { DEMO, api, runTool, useApi, type DeskStock, type MarketOverview, type Onboarding as OnboardingData } from '../api'
import { research } from '../api/researchStore'
import { CP_STATUS } from '../components/Checkpoints'
import { securityPath } from '../components/SecuritySearch'
import { Button, Callout, Tag, type Tone } from '../components/kit'
import { DataState, Page, Section, Table, Td, signClass, signed } from '../components/ui'
import { cn } from '../utils/cn'
import { PLAYBOOK, STATUS } from './ResearchPage'

const EVENT: Record<string, { label: string; tone: Tone }> = {
  checkpoint: { label: '验证点', tone: 'purple' }, report: { label: '新财报', tone: 'blue' }, filing: { label: '公告', tone: 'yellow' },
  valuation: { label: '估值', tone: 'orange' }, move: { label: '异动', tone: 'pink' }, proposal: { label: '待办', tone: 'green' }, sync: { label: '同步', tone: 'gray' },
  task: { label: '定时任务', tone: 'blue' }, alert: { label: '提醒', tone: 'pink' }, source: { label: '数据源', tone: 'yellow' },
}
// 第一次用会碰到的几个词。不指望用户先去读文档
const GLOSSARY: [string, string][] = [
  ['验证点', '每次研究会留下几条能用数据核对的判断（比如“下一期营收同比不低于 10%”）。到期后由程序取数核对，成立还是被证伪都记下来。'],
  ['建议单', '研究给出的买卖建议。它只是建议：你逐条点了授权才会执行，不点就什么都不会发生。'],
  ['PE 历史分位', '现在的市盈率在它自己过去几年里排在什么位置。0% 是最便宜的时候，100% 是最贵的时候。'],
  ['盯盘', '每个交易日收盘后自动检查你的股票：新财报、重要公告、估值变化、大涨大跌。有事才提醒。'],
]

/** 首次引导：四步，各自做没做、下一步点哪里。全做完或点了“不再显示”就消失。 */
const Onboarding: React.FC<{ data: OnboardingData; onDismiss: () => void; onChanged: () => void }> = ({ data, onDismiss, onChanged }) => {
  const [busy, setBusy] = useState(false)
  const done = data.steps.filter((s) => s.done).length
  const next = data.steps.find((s) => !s.done && !s.optional)?.key
  const dismiss = () => { onDismiss(); void api.dismissOnboarding() }
  const sample = async () => { setBusy(true); try { await api.loadSample(); onChanged() } finally { setBusy(false) } }
  const ACTION: Record<string, React.ReactNode> = {
    model: <Link to="/settings" className="text-[13px] font-medium text-link hover:underline">去填 Key</Link>,
    data: (
      <span className="flex items-center gap-3">
        <Link to="/holdings?import=1" className="text-[13px] font-medium text-link hover:underline">粘贴持仓</Link>
        <Button size="xs" variant="secondary" loading={busy} onClick={() => void sample()}>先用示例数据</Button>
      </span>
    ),
    research: <Link to="/research" className="text-[13px] font-medium text-link hover:underline">去提问</Link>,
    reach: <Link to="/settings" className="text-[13px] font-medium text-link hover:underline">去绑定</Link>,
  }
  return (
    <section className="rounded-xl border border-hairline p-5" aria-label="开始使用">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">开始使用 <span className="ml-1 text-[13px] font-normal text-steel">{done} / {data.steps.length}</span></h2>
          <p className="mt-0.5 text-[13px] text-steel">做完前三步，它就开始替你盯着这些股票了。</p>
        </div>
        <Button size="xs" variant="ghost" onClick={dismiss}>不再显示</Button>
      </div>
      <ol className="mt-3 divide-y divide-hairline-soft">
        {data.steps.map((s, i) => (
          <li key={s.key} className="flex items-start gap-3 py-3">
            <span className={cn('mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium',
              s.done ? 'bg-tint-mint text-on-mint' : s.key === next ? 'bg-primary text-white' : 'border border-hairline-strong text-steel')}>
              {s.done ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn('text-sm', s.done ? 'text-steel' : 'font-medium text-ink')}>{s.title}{s.optional ? <span className="ml-2 text-xs font-normal text-stone">可选</span> : null}</p>
              {s.done ? null : <p className="mt-0.5 text-[13px] leading-relaxed text-steel">{s.hint}</p>}
            </div>
            {s.done ? null : <div className="shrink-0">{ACTION[s.key]}</div>}
          </li>
        ))}
      </ol>
      <details className="mt-1 text-[13px] text-slate">
        <summary className="cursor-pointer select-none text-steel hover:text-ink">这几个词是什么意思</summary>
        <dl className="mt-2 space-y-2">
          {GLOSSARY.map(([term, meaning]) => (
            <div key={term}><dt className="inline font-medium text-ink">{term}</dt><dd className="ml-2 inline leading-relaxed">{meaning}</dd></div>
          ))}
        </dl>
      </details>
    </section>
  )
}

/** 有新版本时的一行提示。读的是后端缓存的检查结果，不会因此联网。 */
const UpdateNotice: React.FC = () => {
  const v = useApi(() => api.version())
  if (DEMO || !v.data?.behind) return null
  const latest = v.data.latest_version && v.data.latest_version !== v.data.version ? `新版本 ${v.data.latest_version}` : `${v.data.behind} 处更新`
  return (
    <Callout tone="info" action={<Link to="/settings" className="text-[13px] font-medium underline underline-offset-2">看看更新了什么</Link>}>
      有{latest}可用。在终端里运行 <code className="rounded-xs bg-surface px-1 font-mono text-xs">wealthpilot update</code> 升级（会先备份数据库）。
    </Callout>
  )
}
const More: React.FC<{ to: string; children: React.ReactNode }> = ({ to, children }) => (
  <Link to={to} className="inline-flex items-center gap-1 text-[13px] text-steel hover:text-ink">{children}<ArrowRight className="h-3.5 w-3.5" /></Link>
)
const toolData = <T,>(res: { data: T | string } | null): T | null => (res && typeof res.data !== 'string' ? res.data : null)

const Percentile: React.FC<{ value: number | null }> = ({ value }) => (value == null ? <span className="text-stone">—</span> : (
  <span className="inline-flex items-center gap-2">
    <span className="relative h-1.5 w-14 rounded-full bg-surface"><span className="absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${value}%` }} /></span>
    <span className="w-9 text-right tabular-nums">{value}%</span>
  </span>
))

/**
 * 首页是"你的分析师的工作台"，不是行情软件的首页：
 * 只讲三件事：有什么等你处理、你的每只股票现在怎么样、今天它们出了什么事。大盘只留一行，细的在「市场」。
 */
const TodayPage: React.FC = () => {
  const navigate = useNavigate()
  const desk = useApi(api.desk)
  const market = useApi(() => runTool<MarketOverview | string>('get_market_overview'))
  const history = useApi(api.researchHistory)
  const [draft, setDraft] = useState('')
  const [running, setRunning] = useState(false)
  const [digestError, setDigestError] = useState('')
  const onboarding = useApi(api.onboarding)
  const [dismissed, setDismissed] = useState(false)
  const guide = !DEMO && !dismissed && onboarding.data && !onboarding.data.dismissed && !onboarding.data.complete ? onboarding.data : null

  const d = desk.data
  const m = toolData(market.data)
  const events = (d?.digest?.events ?? []).filter((e) => e.kind !== 'sync')
  const todos = d ? [
    { to: '/review', count: d.todo.proposals, label: '条操作建议等你决定' },
    { to: '/review', count: d.todo.broken, label: '条判断被证伪，结论要重看' },
    { to: '/watchlist', count: d.todo.unresearched, label: '只股票还没研究过' },
  ].filter((x) => x.count > 0) : []
  const ask = (q: string) => { if (!q.trim() || research.busy) return; void research.ask(q.trim()); navigate('/research') }
  const study = (x: DeskStock) => ask(`帮我深度分析一下${x.name}（${x.code}）`)
  const runDigest = async () => {
    setRunning(true); setDigestError('')
    try { await api.runDigest(); desk.reload() } catch (e) { setDigestError(e instanceof Error ? e.message : '检查失败') } finally { setRunning(false) }
  }

  return (
    <Page title="今日" description="你的股票现在怎么样，有什么等你处理" terms={['每日简报', '验证点', '建议单']}>
      <form onSubmit={(e) => { e.preventDefault(); ask(draft) }}
        className="flex items-center gap-2 rounded-xl border border-hairline-strong bg-canvas p-2 shadow-subtle focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={DEMO} aria-label="向 AI 提问"
          placeholder={DEMO ? '在线演示不能提问，去「研究」回放录好的研究' : '问点什么：帮我分析一下宁德时代 / 我的持仓有什么风险 / 复盘一下之前的判断'}
          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[15px] text-ink outline-none placeholder:text-stone" />
        <Button type="submit" size="sm" disabled={DEMO || !draft.trim()}><ArrowUp className="h-4 w-4" />研究</Button>
      </form>

      <UpdateNotice />
      {guide ? <Onboarding data={guide} onDismiss={() => setDismissed(true)} onChanged={() => { onboarding.reload(); desk.reload() }} /> : null}

      <DataState loading={desk.loading && !d} error={desk.error} onRetry={desk.reload}>
        {d ? (
          <>
            {d.stocks.length === 0 ? guide ? null : (
              <Callout tone="info" title="这里还是空的">
                按 <kbd className="rounded-xs border border-current/30 px-1 font-mono text-xs">/</kbd> 搜一只股票加入自选，或去<Link className="mx-1 font-medium underline underline-offset-2" to="/holdings">持仓</Link>录入你的股票和基金。
                之后这里会每天告诉你：它们发生了什么、当初的判断还成立几条。
                {DEMO ? null : <span className="mt-2 block"><Button size="sm" variant="secondary" onClick={() => void api.loadSample().then(desk.reload)}>先用一份示例数据看看</Button></span>}
              </Callout>
            ) : (
              todos.length > 0 ? (
                // 只列真要你动手的；没有就不占地方。待核对的验证点会自己到期，在下面每只股票那一行看
                <Callout tone="info" title="等你处理">
                  <ul className="flex flex-col gap-1 sm:flex-row sm:flex-wrap sm:gap-x-6">
                    {todos.map((x) => <li key={x.label}><Link to={x.to} className="underline-offset-2 hover:underline"><b className="tabular-nums">{x.count}</b> {x.label}</Link></li>)}
                  </ul>
                </Callout>
              ) : null
            )}

            {d.sample && !DEMO ? (
              <Callout tone="warning" action={<Button size="xs" variant="secondary" onClick={() => void api.clearSample().then(desk.reload)}>清除示例数据</Button>}>
                现在看到的是示例持仓和自选，不是你的。清除后录入自己的即可。
              </Callout>
            ) : null}
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
                      {e.code ? <Link to={`/stock/${e.code}`} className="shrink-0 font-medium text-ink hover:underline">{e.name}</Link>
                        : e.kind === 'task' ? <span className="shrink-0 font-medium text-ink">{e.name}</span> : null}
                      <span className="min-w-0 text-charcoal">{e.text}{e.kind === 'task' && e.message_id ? <Link to={`/history/${e.message_id}`} className="ml-2 text-link hover:underline">看全文</Link> : null}</span>
                    </li>
                  ))}
                </ul>
              </DataState>
            </Section>

            {d.verified_recent.length > 0 ? (
              <Section title="最近核对出结果的判断" actions={<More to="/review">回顾</More>}>
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

      {m ? (
        <Section title="大盘" hint={`截至 ${m.breadth.trade_date} 收盘`} actions={<More to="/market">涨停、题材、行业</More>}>
          <p className="flex flex-wrap gap-x-6 gap-y-1 rounded-lg border border-hairline px-4 py-3 text-sm">
            {m.indices.map((i) => <span key={i.name}><span className="text-steel">{i.name}</span> <span className="tabular-nums text-ink">{i.value}</span> <span className={cn('tabular-nums', i.up ? 'text-up' : 'text-down')}>{i.change}</span></span>)}
            <span><span className="text-steel">涨 / 跌</span> <span className="tabular-nums text-up">{m.breadth.up}</span><span className="mx-1 text-stone">/</span><span className="tabular-nums text-down">{m.breadth.down}</span> 家</span>
          </p>
        </Section>
      ) : null}

      <Section title="最近的研究" actions={<More to="/history">全部记录</More>}>
        <DataState loading={history.loading} error={history.error} onRetry={history.reload} empty={history.data?.length === 0 ? '还没有研究记录。' : undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {(history.data ?? []).slice(0, 3).map((r) => (
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
