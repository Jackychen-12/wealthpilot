import type React from 'react'
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts'
import { api, runTool, useApi, type Concentration } from '../api'
import { Tag } from '../components/kit'
import { DataState, Metric, Metrics, Page, Section, Table, Td, signClass } from '../components/ui'
import { cn } from '../utils/cn'

/** 相关系数 → 底色：正相关偏红（同涨同跌），负相关偏青，越接近 0 越淡。 */
const heat = (v: number) => {
  const a = Math.min(1, Math.abs(v)) * 0.6
  return v >= 0 ? `rgba(224, 49, 49, ${a})` : `rgba(0, 117, 222, ${a})`
}

const RiskPage: React.FC = () => {
  const drawdown = useApi(api.drawdown)
  const health = useApi(api.healthScore)
  const correlation = useApi(api.correlation)
  const alerts = useApi(api.alerts)
  const concentration = useApi(() => runTool<Concentration | string>('compute_concentration'))
  const conc = concentration.data && typeof concentration.data.data !== 'string' ? concentration.data.data : null

  const h = health.data
  const dd = drawdown.data
  const codes = Object.keys(correlation.data?.matrix ?? {})
  const names = correlation.data?.names ?? {}

  return (
    <Page title="风险体检" description="回撤、健康度、相关性与预警">
      {dd?.summary && h ? (
        <Metrics>
          <Metric label="健康度总分" value={h.overall_score} hint={h.overall_status} />
          <Metric label="平均最大回撤" value={`${dd.summary.avg_drawdown_pct}%`} hint="近 60 个交易日" />
          {conc ? <Metric label="最大单一占比" value={`${(conc.max_weight * 100).toFixed(1)}%`} hint={`有效持仓 ${conc.effective_holdings.toFixed(2)} 只`} /> : null}
          <Metric label="高风险持仓" value={dd.summary.high_risk_count} tone={dd.summary.high_risk_count ? 'text-up' : undefined} hint="当前亏损较深" />
        </Metrics>
      ) : null}

      <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Section title="回撤" hint="持有收益率相对你的成本；最大回撤是近 60 个交易日净值从高点的最大跌幅">
          <DataState loading={drawdown.loading} error={drawdown.error} onRetry={drawdown.reload} empty={dd && dd.funds.length === 0 ? '暂无持仓' : undefined}>
            <Table head={[{ label: '标的' }, { label: '持有收益率', right: true }, { label: '最大回撤', right: true }, { label: '回撤持续', right: true }, { label: '状态' }]}>
              {(dd?.funds ?? []).map((f) => {
                const held = parseFloat(f.value)
                return (
                  <tr key={f.name}>
                    <Td className="font-medium text-ink">{f.name}</Td>
                    <Td right num className={signClass(held)}>{held > 0 ? '+' : ''}{f.value}</Td>
                    <Td right num>{f.max_drawdown_pct}%</Td>
                    <Td right num>{f.recovery_days} 天</Td>
                    <Td>
                      <Tag tone={f.severity === 'high' ? 'pink' : f.severity === 'medium' ? 'yellow' : 'green'}>
                        {f.severity === 'high' ? '需关注' : f.severity === 'medium' ? '留意' : '正常'}
                      </Tag>
                      <span className="ml-2 text-xs text-steel">{f.recovered ? '已修复' : '未修复'}</span>
                    </Td>
                  </tr>
                )
              })}
            </Table>
          </DataState>
        </Section>

        <Section title="健康度" hint="5 个维度，各 0–100 分">
          <DataState loading={health.loading} error={health.error} onRetry={health.reload} empty={h && h.dimensions.length === 0 ? '暂无持仓' : undefined}>
            <div className="h-[230px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={(h?.dimensions ?? []).map((d) => ({ name: d.name, score: d.score }))} outerRadius="78%">
                  <PolarGrid stroke="var(--hairline)" />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                  <PolarAngleAxis dataKey="name" tick={{ fill: 'var(--steel)', fontSize: 12 }} />
                  <Radar dataKey="score" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.18} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <ul className="mt-2 space-y-2">
              {(h?.dimensions ?? []).map((d) => (
                <li key={d.name} className="flex items-center gap-3 text-sm">
                  <span className="w-20 shrink-0 text-slate">{d.name}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                    <span className={cn('block h-full rounded-full', d.score < 40 ? 'bg-up' : d.score < 70 ? 'bg-warning' : 'bg-primary')} style={{ width: `${d.score}%` }} />
                  </span>
                  <span className="w-7 text-right font-mono tabular-nums">{d.score}</span>
                  <span className="w-12 text-xs text-steel">{d.status}</span>
                </li>
              ))}
            </ul>
          </DataState>
        </Section>
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Section title="相关性矩阵" hint="按日收益率计算。越红越同涨同跌，分散效果越差；蓝色表示走势相反">
          <DataState loading={correlation.loading} error={correlation.error} onRetry={correlation.reload}
            empty={codes.length < 2 ? '至少需要 2 只有净值历史的持仓才能计算' : undefined}>
            <div className="overflow-x-auto">
              <table className="border-separate border-spacing-1 font-mono text-xs">
                <thead>
                  <tr><th />{codes.map((c) => <th key={c} title={names[c]} className="px-1 pb-1 font-normal text-steel">{c}</th>)}</tr>
                </thead>
                <tbody>
                  {codes.map((r) => (
                    <tr key={r}>
                      <th title={names[r]} className="max-w-[9rem] truncate pr-2 text-left font-sans font-normal text-slate">{names[r] ?? r}</th>
                      {codes.map((c) => {
                        const v = correlation.data!.matrix[r][c]
                        return (
                          <td key={c} className="h-9 w-16 rounded-sm text-center tabular-nums text-ink"
                            style={{ background: r === c ? 'var(--surface)' : heat(v) }}>{r === c ? '—' : v.toFixed(2)}</td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DataState>
        </Section>

        <Section title="预警" hint={alerts.data ? `持有收益率跌破 ${alerts.data.threshold}% 时触发` : undefined}>
          <DataState loading={alerts.loading} error={alerts.error} onRetry={alerts.reload}
            empty={alerts.data?.alerts.length === 0 ? '当前没有触发预警' : undefined}>
            <ul className="space-y-2.5">
              {(alerts.data?.alerts ?? []).map((a, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm">
                  <Tag tone={a.severity === 'high' ? 'pink' : 'yellow'} className="mt-0.5">{a.severity === 'high' ? '高' : '中'}</Tag>
                  <span className="text-slate">{a.message}</span>
                </li>
              ))}
            </ul>
          </DataState>
        </Section>
      </div>
    </Page>
  )
}

export default RiskPage
