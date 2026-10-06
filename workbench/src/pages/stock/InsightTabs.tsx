/** 个股页的两个标签：资金与筹码、预期与消息；以及财务页里的单季柱状图和主营构成。 */
import type React from 'react'
import { useState } from 'react'
import {
  api, useApi, type CapitalFlow, type Consensus, type Guidance, type Indicator, type InsiderActivity, type LargeTrades, type MarginSummary,
  type ResearchReport, type Segments, type ShareholderStructure, type StockNews, type Survey,
} from '../../api'
import { useTool } from '../../api/tools'
import { Donut, PriceOverlay, RangeMarker, RatingBar, ValueBars } from '../../components/charts'
import { Callout, Segmented, Tag } from '../../components/kit'
import { DataState, Metric, Metrics, Section, Table, Td, signClass, signed } from '../../components/ui'

const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }))
const short = (d: string) => d.slice(5)

// ── 财务页：单季与主营 ──────────────────────────────────

/** 报表里的金额是年初到期末的累计数，把相邻两期相减才是单个季度的数。缺上一期的季度算不出来，就不画。 */
function singleQuarters(reports: Indicator[], key: 'revenue_yi' | 'net_profit_yi') {
  const byDate = new Map(reports.map((r) => [r.report_date, r]))
  return [...reports].reverse().flatMap((r) => {
    const [year, month] = [r.report_date.slice(0, 4), r.report_date.slice(5, 7)]
    const value = r[key]
    if (value == null) return []
    const label = `${year.slice(2)}Q${Number(month) / 3}`
    if (month === '03') return [{ label, value }]
    const prev = byDate.get(`${year}-${month === '06' ? '03-31' : month === '09' ? '06-30' : '09-30'}`)?.[key]
    return prev == null ? [] : [{ label, value: Number((value - prev).toFixed(2)) }]
  }).slice(-6)
}

export const QuarterBars: React.FC<{ reports: Indicator[] }> = ({ reports }) => {
  const revenue = singleQuarters(reports, 'revenue_yi')
  const profit = singleQuarters(reports, 'net_profit_yi')
  if (revenue.length < 2) return null
  return (
    <Section title="单季营收与净利润" hint="由累计值相减得到的单个季度数，亿元。比累计值更容易看出最近一个季度是变好还是变差">
      <div className="flex flex-col gap-3 lg:flex-row">
        <ValueBars title="单季营收" unit="亿元" data={revenue} />
        <ValueBars title="单季归母净利润" unit="亿元" data={profit} signed />
      </div>
    </Section>
  )
}

const SEGMENT_KINDS = [['by_product', '按产品'], ['by_industry', '按行业'], ['by_region', '按地区']] as const

export const SegmentsSection: React.FC<{ code: string }> = ({ code }) => {
  const seg = useTool<Segments>('get_business_segments', code)
  const [kind, setKind] = useState<'by_product' | 'by_industry' | 'by_region'>('by_product')
  const s = seg.value
  const available = SEGMENT_KINDS.filter(([k]) => (s?.[k] ?? []).length > 0)
  const active = available.some(([k]) => k === kind) ? kind : available[0]?.[0]
  const rows = (active && s ? s[active] : []).filter((r) => (r.revenue_ratio_pct ?? 0) > 0)
  return (
    <Section title="靠什么赚钱" hint={s ? `主营构成 · ${s.report_name}` : undefined}
      actions={available.length > 1 && active ? <Segmented value={active} onChange={(v) => setKind(v as typeof kind)} options={available} /> : undefined}>
      <DataState loading={seg.loading} error={seg.error} onRetry={seg.reload} empty={seg.missing || (!seg.loading && rows.length === 0 ? '没有取到主营构成' : undefined)}>
        <div className="flex flex-col gap-3 lg:flex-row">
          <Donut title="收入占比" data={rows.map((r) => ({ name: r.name, value: (r.revenue_yi ?? 0) * 1e8 }))} />
          <div className="min-w-0 flex-[1.4]">
            <Table minWidth={360} head={[{ label: '业务' }, { label: '收入（亿元）', right: true }, { label: '占比', right: true }, { label: '毛利率', right: true }]}>
              {rows.slice(0, 8).map((r) => (
                <tr key={r.name}>
                  <Td>{r.name}</Td>
                  <Td right num>{num(r.revenue_yi)}</Td>
                  <Td right num>{r.revenue_ratio_pct == null ? '—' : `${r.revenue_ratio_pct}%`}</Td>
                  <Td right num>{r.gross_margin_pct == null ? '—' : `${r.gross_margin_pct}%`}</Td>
                </tr>
              ))}
            </Table>
          </div>
        </div>
      </DataState>
    </Section>
  )
}

// ── 资金与筹码 ──────────────────────────────────────────

export const CapitalTab: React.FC<{ code: string; price: number | null }> = ({ code, price }) => {
  const series = useApi(() => api.capitalSeries(code), [code])
  const flow = useTool<CapitalFlow>('get_capital_flow', code)
  const margin = useTool<MarginSummary>('get_margin_trading', code)
  const holders = useTool<ShareholderStructure>('get_shareholder_structure', code)
  const insider = useTool<InsiderActivity>('get_insider_activity', code)
  const large = useTool<LargeTrades>('get_large_trades', code)

  const daily = [...(series.data?.flow?.daily ?? [])].reverse()
  const breakdown = series.data?.flow?.breakdown
  const main = flow.value?.main_force
  const f = flow.value
  const m = margin.value
  const marginRows = series.data?.margin ?? []
  const counts = series.data?.holders ?? []
  const top = holders.value?.top_float_holders
  const orgs = holders.value?.institutions
  const north = holders.value?.northbound?.[0]
  const events = [
    ...(insider.value?.holder_trades ?? []).map((t) => ({ date: t.notice_date, tone: t.direction === '增持' ? 'pink' as const : 'green' as const, tag: `股东${t.direction}`,
      text: `${t.holder} ${t.direction} ${num(t.shares_wan)} 万股${t.float_ratio_pct ? `（占流通股 ${t.float_ratio_pct}%）` : ''}${t.avg_price ? `，均价 ${t.avg_price}` : ''}` })),
    ...(insider.value?.executive_trades ?? []).map((t) => ({ date: t.date, tone: (t.shares ?? 0) >= 0 ? 'pink' as const : 'green' as const, tag: `高管${(t.shares ?? 0) >= 0 ? '增持' : '减持'}`,
      text: `${t.person}（${t.position}${t.relation && t.relation !== '本人' ? ` · ${t.relation}` : ''}）${Math.abs(t.shares ?? 0).toLocaleString()} 股，约 ${num(Math.abs(t.amount_wan ?? 0), 0)} 万元 · ${t.reason}` })),
    ...(insider.value?.buybacks ?? []).map((b) => ({ date: b.notice_date, tone: 'pink' as const, tag: '回购',
      text: `拟回购 ${num(b.amount_lower_yi)}～${num(b.amount_upper_yi)} 亿元${b.price_cap ? `，价格上限 ${b.price_cap}` : ''}${b.finished ? `，已于 ${b.finished} 实施完毕` : `，期限至 ${b.end}`}` })),
    ...(insider.value?.unlocks ?? []).map((u) => ({ date: u.date, tone: u.upcoming ? 'yellow' as const : 'gray' as const, tag: u.upcoming ? '将解禁' : '已解禁',
      text: `${u.type} ${num(u.shares_wan)} 万股，约 ${num(u.value_yi)} 亿元${u.float_ratio_pct ? `，占解禁前流通股 ${u.float_ratio_pct}%` : ''}` })),
    ...(large.value?.block_trades_6m ?? []).map((b) => ({ date: b.date, tone: (b.premium_pct ?? 0) < 0 ? 'green' as const : 'gray' as const, tag: '大宗交易',
      text: `成交 ${num(b.amount_yi, 4)} 亿元，价格 ${b.price}（${(b.premium_pct ?? 0) === 0 ? '平价' : signed(b.premium_pct, 2, '%')}）· 买方 ${b.buyer} · 卖方 ${b.seller}` })),
    ...(large.value?.billboard_12m ?? []).map((b) => ({ date: b.date, tone: 'purple' as const, tag: '龙虎榜',
      text: `${b.reason}；当日 ${signed(b.change_pct, 2, '%')}，上榜净买入 ${signed(b.net_buy_yi, 2)} 亿元 · ${b.summary}` })),
  ].sort((a, b) => b.date.localeCompare(a.date))

  return (
    <>
      <Section title="资金流向" hint={f?.as_of ? `截至 ${f.as_of}` : undefined}>
        <DataState loading={flow.loading && series.loading} error={flow.error} onRetry={flow.reload} empty={flow.missing || undefined}>
          <Metrics>
            <Metric label="近 5 日净流入（亿元）" value={signed(f?.net_5d_yi ?? null, 2)} tone={signClass(f?.net_5d_yi)} />
            <Metric label="近 20 日净流入（亿元）" value={signed(f?.net_20d_yi ?? null, 2)} tone={signClass(f?.net_20d_yi)} />
            <Metric label={f && f.streak_days < 0 ? '连续净流出' : '连续净流入'} value={f ? `${Math.abs(f.streak_days)} 天` : '—'} tone={signClass(f?.streak_days)} />
            <Metric label="主力成本（20 日）" value={num(main?.main_cost_20d)}
              hint={main?.main_cost_20d && price ? `现价${price >= main.main_cost_20d ? '高于' : '低于'}它 ${Math.abs(((price - main.main_cost_20d) / main.main_cost_20d) * 100).toFixed(1)}%` : undefined} />
          </Metrics>
          {daily.length > 1 ? (
            <div className="mt-3">
              <PriceOverlay name="当日净流入" unit="亿元" signed data={daily.map((d) => ({ label: short(d.date), value: d.net_yi, close: d.close }))} />
            </div>
          ) : null}
          {breakdown ? (
            <div className="mt-3">
              <ValueBars title="最近一个交易日 · 按单子大小的净额" unit="亿元" signed height={150}
                data={Object.entries(breakdown).map(([label, b]) => ({ label, value: b.net_yi }))} />
            </div>
          ) : null}
          <p className="mt-2 text-[13px] leading-relaxed text-steel">
            柱子是每天“主动买入减主动卖出”的金额，红色是买的多、绿色是卖的多；虚线是收盘价。资金流向是按每笔成交的方向估算的，
            只能说明买盘更急还是卖盘更急，不等于机构真的在买。逐日数据来自新浪，主力成本来自东方财富，两家口径不同。
          </p>
        </DataState>
      </Section>

      <Section title="融资融券" hint={m?.as_of ? `截至 ${m.as_of}` : undefined}>
        <DataState loading={margin.loading} error={margin.error} onRetry={margin.reload} empty={margin.missing || undefined}>
          <Metrics>
            <Metric label="融资余额（亿元）" value={num(m?.financing_balance_yi)} hint={m?.financing_to_float_mv_pct != null ? `占流通市值 ${m.financing_to_float_mv_pct}%` : undefined} />
            <Metric label="近 5 日变化" value={signed(m?.financing_balance_change_5d_pct ?? null, 2, '%')} tone={signClass(m?.financing_balance_change_5d_pct)} />
            <Metric label="近 20 日变化" value={signed(m?.financing_balance_change_20d_pct ?? null, 2, '%')} tone={signClass(m?.financing_balance_change_20d_pct)} />
            <Metric label="近 60 日变化" value={signed(m?.financing_balance_change_60d_pct ?? null, 2, '%')} tone={signClass(m?.financing_balance_change_60d_pct)} />
          </Metrics>
          {marginRows.length > 1 ? (
            <div className="mt-3">
              <PriceOverlay name="融资余额" unit="亿元" kind="line" data={marginRows.map((d) => ({ label: short(d.date), value: d.financing_balance_yi, close: d.close }))} />
            </div>
          ) : null}
          <p className="mt-2 text-[13px] leading-relaxed text-steel">融资余额是借钱买入、还没还的钱。它上升说明加杠杆的人在变多；股价下跌时这些钱会被迫卖出，所以余额越高，下跌时的抛压也越大。</p>
        </DataState>
      </Section>

      <Section title="票在谁手里" hint={top ? `${top.report} · 定期报告披露，滞后 1 到 3 个月` : undefined}>
        <DataState loading={holders.loading} error={holders.error} onRetry={holders.reload} empty={holders.missing || undefined}>
          {counts.length > 1 ? (
            <>
              <PriceOverlay name="股东户数" unit="户" data={counts.map((c) => ({ label: c.end_date.slice(2, 7), value: c.holders, close: c.close }))} />
              <p className="mb-4 mt-2 text-[13px] leading-relaxed text-steel">
                最新一期 {counts[counts.length - 1].holders?.toLocaleString()} 户，环比 {signed(counts[counts.length - 1].change_pct, 2, '%')}，户均持股 {counts[counts.length - 1].avg_shares?.toLocaleString()} 股。
                户数减少、户均持股上升，通常说明筹码在往少数人手里集中；反过来就是在分散。
              </p>
            </>
          ) : null}
          <div className="flex flex-col gap-4 xl:flex-row">
            {top ? (
              <div className="min-w-0 flex-[1.5]">
                <p className="mb-1.5 text-[13px] font-medium text-steel">十大流通股东</p>
                <Table minWidth={420} head={[{ label: '股东' }, { label: '持股（万股）', right: true }, { label: '占流通股', right: true }, { label: '变动', right: true }]}>
                  {top.holders.map((h) => (
                    <tr key={h.rank}>
                      <Td><span className="mr-2 text-xs text-stone">{h.rank}</span>{h.name}</Td>
                      <Td right num>{num(h.shares_wan, 0)}</Td>
                      <Td right num>{h.float_ratio_pct == null ? '—' : `${h.float_ratio_pct}%`}</Td>
                      <Td right className={h.change === '新进' || h.change === '增加' ? 'text-up' : h.change === '减少' ? 'text-down' : 'text-steel'}>
                        {h.change_shares_wan != null ? `${h.change} ${num(Math.abs(h.change_shares_wan), 0)}` : h.change || '—'}
                      </Td>
                    </tr>
                  ))}
                </Table>
              </div>
            ) : null}
            {orgs ? (
              <div className="min-w-0 flex-1">
                <p className="mb-1.5 text-[13px] font-medium text-steel">机构持仓 · {orgs.latest.report_date}</p>
                <Table minWidth={320} head={[{ label: '类型' }, { label: '家数', right: true }, { label: '占流通股', right: true }, { label: '变动（万股）', right: true }]}>
                  {orgs.latest.by_type.filter((o) => o.type !== '机构汇总').map((o) => (
                    <tr key={o.type}>
                      <Td>{o.type}</Td>
                      <Td right num>{o.count ?? '—'}</Td>
                      <Td right num>{o.float_ratio_pct == null ? '—' : `${o.float_ratio_pct}%`}</Td>
                      <Td right num className={signClass(o.change_shares_wan)}>{o.change_shares_wan == null ? o.change || '—' : signed(o.change_shares_wan, 0)}</Td>
                    </tr>
                  ))}
                </Table>
                {north ? <p className="mt-2 text-[13px] text-steel">北向持股 {num(north.shares_wan, 0)} 万股，占流通股 {north.float_ratio_pct}%（{north.date}，按季度披露）</p> : null}
              </div>
            ) : null}
          </div>
        </DataState>
      </Section>

      <Section title="内部人与大额交易" hint={insider.value ? `${insider.value.window} · 大宗近 6 个月 · 龙虎榜近一年` : undefined}>
        <DataState loading={insider.loading || large.loading} error={insider.error} onRetry={insider.reload}
          empty={!insider.loading && !large.loading && events.length === 0 ? '这段时间没有查到增减持、回购、解禁、大宗交易或龙虎榜记录。' : undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {events.slice(0, 16).map((e, i) => (
              <li key={`${e.date}-${i}`} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                <span className="w-20 shrink-0 font-mono text-xs text-stone">{e.date}</span>
                <Tag tone={e.tone}>{e.tag}</Tag>
                <span className="min-w-0 text-charcoal">{e.text}</span>
              </li>
            ))}
          </ul>
        </DataState>
      </Section>
    </>
  )
}

// ── 预期与消息 ──────────────────────────────────────────

const CHANGE_TONE: Record<string, 'pink' | 'green' | 'purple' | 'gray'> = { 调高: 'pink', 调低: 'green', 首次: 'purple' }

export const ExpectationTab: React.FC<{ code: string }> = ({ code }) => {
  const consensus = useTool<Consensus>('get_consensus_forecast', code)
  const reports = useTool<{ reports: ResearchReport[] }>('get_research_reports', code)
  const guidance = useTool<Guidance>('get_earnings_guidance', code)
  const news = useTool<{ news: StockNews[] }>('get_stock_news', code)
  const surveys = useTool<{ surveys: Survey[] }>('get_investor_surveys', code)
  const c = consensus.value
  const target = c?.broker_target_price_low != null && c.broker_target_price_high != null && c.price ? c : null
  const nextYear = c?.eps_forecast.find((e) => !e.actual)

  return (
    <>
      <Section title="券商怎么看" hint={c ? `${c.org_count} 家机构覆盖` : undefined}>
        <DataState loading={consensus.loading} error={consensus.error} onRetry={consensus.reload} empty={consensus.missing || undefined}>
          {c ? (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-lg border border-hairline p-4">
                  <p className="mb-2 text-[13px] font-medium text-steel">评级分布</p>
                  <RatingBar ratings={c.ratings} />
                  {target ? (
                    <div className="mt-5">
                      <p className="mb-2 text-[13px] font-medium text-steel">券商给出的目标价区间</p>
                      <RangeMarker low={target.broker_target_price_low!} high={target.broker_target_price_high!} current={target.price!} currentLabel={`现价 ${target.price}`} />
                      <p className="mt-1 text-[13px] text-steel">
                        {target.price! < target.broker_target_price_low! ? `现价比最低的目标价还低 ${(((target.broker_target_price_low! - target.price!) / target.price!) * 100).toFixed(1)}%`
                          : target.price! > target.broker_target_price_high! ? `现价已经高过最高的目标价 ${(((target.price! - target.broker_target_price_high!) / target.broker_target_price_high!) * 100).toFixed(1)}%`
                            : '现价在目标价区间之内'}。目标价是券商的看法，历史上普遍偏高。
                      </p>
                    </div>
                  ) : null}
                </div>
                <ValueBars title="每股收益：已披露与券商预测（元）" unit="元" height={190}
                  data={c.eps_forecast.map((e) => ({ label: `${e.year}${e.actual ? '' : ' 预测'}`, value: e.eps, muted: !e.actual }))} />
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate">
                {nextYear ? <>券商平均预测 {nextYear.year} 年每股收益 <b className="text-ink">{nextYear.eps}</b> 元{nextYear.growth_pct != null ? <>，比上一年 <b className={signClass(nextYear.growth_pct)}>{signed(nextYear.growth_pct, 2, '%')}</b></> : null}
                  {nextYear.pe_at_current_price ? <>；按现价算是 <b className="text-ink">{nextYear.pe_at_current_price}</b> 倍预期市盈率</> : null}。</> : null}
                {' '}这些是券商的看法，不是事实：卖方普遍偏乐观、很少给“卖出”，覆盖的机构越少越不可靠。
              </p>
            </>
          ) : null}
        </DataState>
      </Section>

      {guidance.value?.forecast || guidance.value?.express ? (
        <Section title="公司自己怎么说" hint="业绩预告与业绩快报，最终以定期报告为准">
          <div className="flex flex-col gap-2">
            {guidance.value.forecast ? (
              <Callout tone="neutral" title={`业绩预告 · 对应 ${guidance.value.forecast.report_date} · ${guidance.value.forecast.notice_date} 发布`}>
                {guidance.value.forecast.items.map((item) => (
                  <p key={item.metric} className="mt-1"><Tag tone={/增|盈|扭亏/.test(item.type) ? 'pink' : /减|亏/.test(item.type) ? 'green' : 'gray'} className="mr-2 !py-0">{item.type}</Tag>{item.content}
                    {item.reason ? <span className="mt-1 block text-[13px] text-steel">原因：{item.reason}</span> : null}</p>
                ))}
              </Callout>
            ) : null}
            {guidance.value.express ? (
              <Callout tone="neutral" title={`业绩快报 · ${guidance.value.express.period} · ${guidance.value.express.notice_date} 发布`}>
                营收 {num(guidance.value.express.revenue_yi)} 亿元（同比 {signed(guidance.value.express.revenue_yoy_pct, 2, '%')}），
                归母净利润 {num(guidance.value.express.net_profit_yi)} 亿元（同比 {signed(guidance.value.express.net_profit_yoy_pct, 2, '%')}）
              </Callout>
            ) : null}
          </div>
        </Section>
      ) : null}

      <Section title="近期研报" hint="近半年。评级被调高或调低，比评级本身更值得看">
        <DataState loading={reports.loading} error={reports.error} onRetry={reports.reload} empty={reports.missing || undefined}>
          <Table minWidth={720} head={[{ label: '日期' }, { label: '机构' }, { label: '标题' }, { label: '评级' }, { label: '今年 EPS', right: true }, { label: '明年 EPS', right: true }]}>
            {(reports.value?.reports ?? []).map((r) => (
              <tr key={`${r.date}-${r.org}-${r.title}`}>
                <Td className="whitespace-nowrap font-mono text-[13px]">{r.date}</Td>
                <Td className="whitespace-nowrap">{r.org}</Td>
                <Td>{r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="text-ink hover:underline">{r.title}</a> : r.title}</Td>
                <Td className="whitespace-nowrap">{r.rating}{CHANGE_TONE[r.rating_change] ? <Tag tone={CHANGE_TONE[r.rating_change]} className="ml-1.5 !py-0">{r.rating_change}</Tag> : null}</Td>
                <Td right num>{r.eps_this_year ?? '—'}</Td>
                <Td right num>{r.eps_next_year ?? '—'}</Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>

      <Section title="最近的新闻" hint="媒体的转述，不等于事实">
        <DataState loading={news.loading} error={news.error} onRetry={news.reload} empty={news.missing || undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {(news.value?.news ?? []).map((n) => (
              <li key={n.url || n.title} className="px-4 py-2.5">
                <a href={n.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-ink hover:underline">{n.title}</a>
                <p className="mt-0.5 line-clamp-2 text-[13px] leading-relaxed text-steel">{n.summary}</p>
                <p className="mt-0.5 text-xs text-stone">{n.media} · {n.date}</p>
              </li>
            ))}
          </ul>
        </DataState>
      </Section>

      {surveys.value?.surveys.length ? (
        <Section title="机构调研" hint="公司对机构提问的回答，是公司自己的说法">
          <div className="flex flex-col gap-2">
            {surveys.value.surveys.map((s) => (
              <details key={s.notice_date} className="rounded-lg border border-hairline px-4 py-2.5">
                <summary className="cursor-pointer select-none text-sm text-ink">
                  <span className="mr-2 font-mono text-xs text-stone">{s.date}</span>{s.way || '调研'}<span className="ml-2 text-[13px] text-steel">{s.participants} 家机构参加{s.place ? ` · ${s.place}` : ''}</span>
                </summary>
                <p className="mt-2 text-[13px] leading-relaxed text-slate">{s.content}…</p>
              </details>
            ))}
          </div>
        </Section>
      ) : null}
    </>
  )
}
