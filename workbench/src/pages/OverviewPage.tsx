import type React from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { api, useApi } from '../api'
import { Button, Segmented, Tag } from '../components/kit'
import { DataState, DivergingBar, Metric, Metrics, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'
import { cn } from '../utils/cn'

const parseYuan = (s: string) => Number(s.replace(/[^\d.+-]/g, '')) || 0
// Notion 品牌色谱
const SLICE_COLORS = ['#5645d4', '#2a9d99', '#dd5b00', '#0075de', '#ff64c8', '#1aae39', '#f5d75e', '#a4a097']
const BY = [['fund', '按标的'], ['industry', '按行业'], ['category', '按类别']] as const

const OverviewPage: React.FC = () => {
  const navigate = useNavigate()
  const [by, setBy] = useState<string>('fund')
  const overview = useApi(api.overview)
  const holdings = useApi(api.holdings)
  const attribution = useApi(() => api.attribution(by), [by])
  const suggestions = useApi(api.suggestions)
  const indices = useApi(api.indices)
  const news = useApi(api.news)

  const o = overview.data
  const rows = [...(holdings.data ?? [])].sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0))
  const total = rows.reduce((s, h) => s + (h.market_value ?? 0), 0)
  const attr = attribution.data ?? []
  const attrMax = Math.max(1, ...attr.map((a) => Math.abs(parseYuan(a.value))))
  const noHoldings = !holdings.loading && !holdings.error && rows.length === 0
  const todo = (suggestions.data ?? []).filter((s) => s.priority !== 'low')

  return (
    <Page title="总览" description="市值、收益、归因与市场动态"
      actions={<Button size="sm" variant="secondary" onClick={() => navigate('/holdings')}>管理持仓</Button>}>
      {noHoldings ? (
        <DataState empty="还没有持仓。先录入持仓，总览、风险体检和 AI 研究才有数据可算。"
          emptyAction={<Button size="sm" onClick={() => navigate('/holdings')}>去录入持仓</Button>}>{null}</DataState>
      ) : (
        <>
          <div>
            <DataState loading={overview.loading} error={overview.error} onRetry={overview.reload}>
              {o ? (
                <Metrics>
                  <Metric label="总市值（元）" value={yuan(o.total_market_value)} hint={`成本 ${yuan(o.total_cost)}`} />
                  <Metric label="累计收益（元）" value={signed(o.total_return, 0)} tone={signClass(o.total_return)} hint={signed(o.return_pct, 2, '%')} />
                  <Metric label="本周收益（元）" value={signed(o.weekly_return, 0)} tone={signClass(o.weekly_return)} hint={signed(o.weekly_growth_pct, 2, '%')} />
                  <Metric label="超额收益" value={o.excess_return_pct == null ? '—' : signed(o.excess_return_pct, 2, '%')} hint={o.excess_return_pct == null ? '基准数据不足' : '相对基准'} />
                  <Metric label="Sharpe（年化）" value={o.sharpe_ratio == null ? '—' : o.sharpe_ratio.toFixed(2)} hint={o.volatility_status} />
                </Metrics>
              ) : null}
            </DataState>
            {o?.methodology ? <p className="mt-2 text-[13px] text-steel">口径：{o.methodology}</p> : null}
          </div>

          <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Section title="持仓分布" hint="按当前市值">
              <DataState loading={holdings.loading} error={holdings.error} onRetry={holdings.reload}>
                <div className="grid items-center gap-4 md:grid-cols-[180px_minmax(0,1fr)]">
                  <div className="h-[180px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={rows.map((h) => ({ name: h.fund_name, value: h.market_value ?? 0 }))} dataKey="value" innerRadius={50} outerRadius={80} paddingAngle={1.5} stroke="none">
                          {rows.map((h, i) => <Cell key={h.id} fill={SLICE_COLORS[i % SLICE_COLORS.length]} />)}
                        </Pie>
                        <Tooltip formatter={(v) => `${yuan(Number(v))} 元`}
                          contentStyle={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }}
                          itemStyle={{ color: 'var(--ink)' }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <Table head={[{ label: '标的' }, { label: '市值', right: true }, { label: '占比', right: true }, { label: '持有收益', right: true }]} minWidth={400}>
                    {rows.map((h, i) => (
                      <tr key={h.id}>
                        <Td>
                          <span className="flex items-center gap-2">
                            <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: SLICE_COLORS[i % SLICE_COLORS.length] }} />
                            <span className="font-medium text-ink">{h.fund_name}</span>
                            <span className="font-mono text-xs text-stone">{h.fund_code}</span>
                          </span>
                        </Td>
                        <Td right num>{yuan(h.market_value)}</Td>
                        <Td right num>{total ? `${(((h.market_value ?? 0) / total) * 100).toFixed(1)}%` : '—'}</Td>
                        <Td right num className={signClass(h.return_pct)}>{signed(h.return_pct, 2, '%')}</Td>
                      </tr>
                    ))}
                  </Table>
                </div>
              </DataState>
            </Section>

            <Section title="该关注什么" hint="规则引擎根据持仓算出">
              <DataState loading={suggestions.loading} error={suggestions.error} onRetry={suggestions.reload}
                empty={todo.length === 0 ? '当前没有需要关注的事项' : undefined}>
                <ul className="space-y-3">
                  {todo.map((s, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <Tag tone={s.priority === 'high' ? 'pink' : 'yellow'} className="mt-0.5">{s.priority === 'high' ? '重要' : '留意'}</Tag>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink">{s.title}</p>
                        <p className="text-[13px] text-steel">{s.desc}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </DataState>
              <Button size="sm" variant="secondary" className="mt-4" onClick={() => navigate('/')}>让 AI 深入分析</Button>
            </Section>
          </div>

          <Section title="收益归因" hint="累计持有收益来自哪里" actions={<Segmented value={by} onChange={setBy} options={BY} />}>
            <DataState loading={attribution.loading} error={attribution.error} onRetry={attribution.reload}>
              <Table head={[{ label: by === 'fund' ? '标的' : by === 'industry' ? '行业' : '类别' }, { label: '亏损 ← → 盈利', className: 'w-[42%]' }, { label: '收益', right: true }, { label: '影响占比', right: true }]}>
                {attr.map((a) => (
                  <tr key={a.name}>
                    <Td className="font-medium text-ink">{a.name}</Td>
                    <Td><DivergingBar value={parseYuan(a.value)} max={attrMax} /></Td>
                    <Td right num className={a.positive ? 'text-up' : 'text-down'}>{a.value}</Td>
                    <Td right num className="text-slate">{a.pct}%</Td>
                  </tr>
                ))}
              </Table>
            </DataState>
          </Section>
        </>
      )}

      <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Section title="财经要闻" hint="来自东方财富，点击查看原文">
          <DataState loading={news.loading} error={news.error} onRetry={news.reload} empty={news.data?.length === 0 ? '暂时没有取到新闻' : undefined}>
            <ul className="divide-y divide-hairline-soft border-y border-hairline-soft">
              {(news.data ?? []).map((n, i) => (
                <li key={i} className="flex items-baseline gap-3 py-2.5 text-sm">
                  <span className="w-[4.5rem] shrink-0 font-mono text-xs text-stone">{n.published_at?.slice(5, 16)}</span>
                  {n.source_url
                    ? <a className="min-w-0 text-charcoal hover:text-link hover:underline" href={n.source_url} target="_blank" rel="noreferrer">{n.text}</a>
                    : <span className="min-w-0 text-charcoal">{n.text}</span>}
                </li>
              ))}
            </ul>
          </DataState>
        </Section>
        <Section title="大盘指数">
          <DataState loading={indices.loading} error={indices.error} onRetry={indices.reload}>
            <ul className="divide-y divide-hairline-soft border-y border-hairline-soft">
              {(indices.data ?? []).map((ix) => (
                <li key={ix.name} className="flex items-center gap-3 py-2.5 text-sm">
                  <span className="flex-1 text-charcoal">{ix.name}</span>
                  <span className="tabular-nums text-ink">{ix.value}</span>
                  <span className={cn('w-16 text-right tabular-nums', ix.up ? 'text-up' : 'text-down')}>{ix.change}</span>
                </li>
              ))}
            </ul>
          </DataState>
        </Section>
      </div>
    </Page>
  )
}

export default OverviewPage
