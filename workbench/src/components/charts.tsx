/** 图表：K 线、热力图、占比环图、迷你走势。配色跟随 A 股习惯（红涨绿跌）。 */
import type React from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, Treemap, XAxis, YAxis } from 'recharts'

const AXIS = { fill: 'var(--steel)', fontSize: 11 }
export const TOOLTIP = { background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }
const UP = '224,49,49'
const DOWN = '18,137,58'

export interface Candle { nav_date: string; nav: number; open?: number; high?: number; low?: number; volume?: number }

const ma = (rows: Candle[], n: number, i: number) => (i + 1 < n ? null : rows.slice(i + 1 - n, i + 1).reduce((s, r) => s + r.nav, 0) / n)

type ShapeProps = { x?: number; y?: number; width?: number; height?: number; payload?: Candle & { up: boolean } }
const CandleShape = ({ x = 0, y = 0, width = 0, height = 0, payload }: ShapeProps) => {
  if (!payload || payload.high == null || payload.low == null || payload.open == null) return null
  const span = payload.high - payload.low || 1
  const at = (v: number) => y + (height * (payload.high! - v)) / span
  const top = at(Math.max(payload.open, payload.nav))
  const bottom = at(Math.min(payload.open, payload.nav))
  const color = payload.up ? 'var(--up)' : 'var(--down)'
  const body = Math.max(1, Math.min(width * 0.7, 9))
  const cx = x + width / 2
  return (
    <g>
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - body / 2} y={top} width={body} height={Math.max(1, bottom - top)} fill={color} />
    </g>
  )
}

/** 把日线合成周线或月线：开取第一天、收取最后一天、高低取极值、量求和。 */
export function aggregate(rows: Candle[], period: 'day' | 'week' | 'month'): Candle[] {
  if (period === 'day') return rows
  const key = (d: string) => {
    if (period === 'month') return d.slice(0, 7)
    const t = new Date(`${d}T00:00:00`)
    t.setDate(t.getDate() - ((t.getDay() + 6) % 7))   // 回到这一周的周一
    return t.toISOString().slice(0, 10)
  }
  const out: Candle[] = []
  let current = ''
  for (const r of rows) {
    const k = key(r.nav_date)
    const last = out[out.length - 1]
    if (k !== current || !last) {
      current = k
      out.push({ ...r })
    } else {
      last.nav_date = r.nav_date
      last.nav = r.nav
      last.high = Math.max(last.high ?? r.nav, r.high ?? r.nav)
      last.low = Math.min(last.low ?? r.nav, r.low ?? r.nav)
      last.volume = (last.volume ?? 0) + (r.volume ?? 0)
    }
  }
  return out
}

/**
 * K 线：蜡烛 + MA5 / MA20，下方成交量。数据按日期升序。
 * marks 是要在图上标出来的日期（比如每次做研究的那天）——行情软件画不出这条线，因为它不知道你什么时候下过判断。
 */
export const Candles: React.FC<{ data: Candle[]; marks?: { date: string; label: string }[] }> = ({ data, marks = [] }) => {
  // 标记落在非交易日或被合成进周 / 月线时，挂到它之后最近的一根上；比最后一根还晚（今天做的研究）就挂在最后一根
  const pinned = marks.map((m) => ({ ...m, at: (data.find((r) => r.nav_date >= m.date) ?? data[data.length - 1])?.nav_date })).filter((m) => m.at)
  const rows = data.map((r, i) => ({ ...r, up: r.nav >= (r.open ?? r.nav), range: [r.low ?? r.nav, r.high ?? r.nav] as [number, number], ma5: ma(data, 5, i), ma20: ma(data, 20, i) }))
  const tick = (v: string) => v.slice(5)
  return (
    <div className="rounded-lg border border-hairline p-3">
      <div className="mb-1 flex gap-4 px-1 text-xs text-steel">
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--primary)] align-middle" />MA5</span>
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--warning)] align-middle" />MA20</span>
        {pinned.length ? <span><i className="mr-1 inline-block h-3 w-0 border-l border-dashed border-[var(--primary)] align-middle" />做过研究的日子</span> : null}
      </div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} syncId="kline" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
            <XAxis dataKey="nav_date" hide />
            <YAxis domain={['auto', 'auto']} tick={AXIS} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => v.toFixed(v >= 100 ? 0 : 2)} />
            <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: 'var(--steel)' }}
              formatter={(v, name) => (name === 'range' ? [null, null] : [Number(v).toFixed(2), name])}
              labelFormatter={(label, items) => {
                const p = items?.[0]?.payload as Candle | undefined
                return p ? `${label}  开 ${p.open}  高 ${p.high}  低 ${p.low}  收 ${p.nav}` : label
              }} />
            <Bar dataKey="range" shape={<CandleShape />} isAnimationActive={false} />
            {pinned.map((m) => (
              <ReferenceLine key={`${m.date}-${m.label}`} x={m.at} stroke="var(--primary)" strokeDasharray="3 3" strokeOpacity={0.7}
                label={{ value: m.label, position: 'insideTopLeft', fill: 'var(--primary)', fontSize: 11 }} />
            ))}
            <Line type="monotone" dataKey="ma5" name="MA5" stroke="var(--primary)" strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="ma20" name="MA20" stroke="var(--warning)" strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="h-[70px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} syncId="kline" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="nav_date" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={48} tickFormatter={tick} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => (v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v))} />
            <Tooltip contentStyle={TOOLTIP} formatter={(v) => [`${Number(v).toLocaleString()} 手`, '成交量']} labelStyle={{ color: 'var(--steel)' }} />
            <Bar dataKey="volume" isAnimationActive={false}>{rows.map((r) => <Cell key={r.nav_date} fill={r.up ? 'var(--up)' : 'var(--down)'} fillOpacity={0.55} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export interface HeatItem { name: string; size: number; change: number | null; code?: string; sub?: string }
type HeatCell = { x?: number; y?: number; width?: number; height?: number; name?: string; change?: number | null; sub?: string; limit: number; onPick?: (i: HeatItem) => void; code?: string; size?: number }
const HeatContent = ({ x = 0, y = 0, width = 0, height = 0, name, change, sub, limit, onPick, code, size = 0 }: HeatCell) => {
  if (!name) return null
  const strength = change == null ? 0 : Math.min(Math.abs(change) / limit, 1)
  const fill = change == null || change === 0 ? 'var(--surface)' : `rgba(${change > 0 ? UP : DOWN},${0.14 + strength * 0.7})`
  const text = strength > 0.55 ? '#fff' : 'var(--ink)'
  const show = width > 46 && height > 26
  return (
    <g onClick={onPick ? () => onPick({ name, size, change: change ?? null, code }) : undefined} style={onPick ? { cursor: 'pointer' } : undefined}>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="var(--canvas)" strokeWidth={2} rx={3} />
      {show ? <text x={x + 6} y={y + 16} fontSize={12} fontWeight={500} fill={text}>{name.length * 12 > width - 8 ? `${name.slice(0, Math.max(1, Math.floor((width - 14) / 12)))}…` : name}</text> : null}
      {show && height > 40 && change != null ? <text x={x + 6} y={y + 32} fontSize={11} fill={text} opacity={0.9}>{`${change > 0 ? '+' : ''}${change.toFixed(2)}%${sub && width > 110 ? ` · ${sub}` : ''}`}</text> : null}
    </g>
  )
}

/** 热力图：块的大小是权重，颜色是涨跌（越深幅度越大）。 */
export const Heatmap: React.FC<{ items: HeatItem[]; height?: number; limit?: number; onPick?: (i: HeatItem) => void }> = ({ items, height = 260, limit = 4, onPick }) => (
  <div style={{ height }} className="overflow-hidden rounded-lg border border-hairline p-1">
    <ResponsiveContainer width="100%" height="100%">
      <Treemap data={items.filter((i) => i.size > 0).map((i) => ({ ...i }) as Record<string, unknown>)} dataKey="size" isAnimationActive={false} content={<HeatContent limit={limit} onPick={onPick} />} />
    </ResponsiveContainer>
  </div>
)

const PALETTE = ['#5645d4', '#0075de', '#dd5b00', '#12893a', '#a02e6d', '#b8860b', '#787671', '#3aa6a6']

/** 占比环图，右侧图例带百分比。 */
export const Donut: React.FC<{ title: string; data: { name: string; value: number }[] }> = ({ title, data }) => {
  const total = data.reduce((s, d) => s + d.value, 0)
  const rows = [...data].sort((a, b) => b.value - a.value)
  return (
    <div className="flex min-w-0 flex-1 items-center gap-4 rounded-lg border border-hairline p-4">
      <div className="h-[132px] w-[132px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={rows} dataKey="value" nameKey="name" innerRadius={40} outerRadius={62} paddingAngle={1.5} stroke="none" isAnimationActive={false}>
              {rows.map((d, i) => <Cell key={d.name} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip contentStyle={TOOLTIP} formatter={(v, name) => [`${Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元`, name]} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="min-w-0 flex-1">
        <p className="mb-1.5 text-[13px] font-medium text-steel">{title}</p>
        {rows.slice(0, 6).map((d, i) => (
          <div key={d.name} className="flex items-center gap-2 py-0.5 text-[13px]">
            <i className="h-2 w-2 shrink-0 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="min-w-0 flex-1 truncate text-charcoal">{d.name}</span>
            <span className="tabular-nums text-steel">{total ? ((d.value / total) * 100).toFixed(1) : 0}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 横向盈亏条：每行一个标的，红盈绿亏。 */
export const PnlBars: React.FC<{ data: { name: string; value: number }[] }> = ({ data }) => (
  <div className="rounded-lg border border-hairline p-3" style={{ height: Math.max(120, data.length * 30 + 30) }}>
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v: number) => v.toLocaleString()} />
        <YAxis type="category" dataKey="name" tick={{ ...AXIS, fontSize: 12 }} tickLine={false} axisLine={false} width={112} />
        <ReferenceLine x={0} stroke="var(--hairline-strong)" />
        <Tooltip contentStyle={TOOLTIP} formatter={(v) => [`${Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元`, '持有收益']} cursor={{ fill: 'var(--surface-soft)' }} />
        <Bar dataKey="value" barSize={14} radius={2} isAnimationActive={false}>{data.map((d) => <Cell key={d.name} fill={d.value >= 0 ? 'var(--up)' : 'var(--down)'} />)}</Bar>
      </BarChart>
    </ResponsiveContainer>
  </div>
)

/** 迷你走势线：只看形状，不带坐标。 */
export const Sparkline: React.FC<{ values: number[]; height?: number }> = ({ values, height = 44 }) => {
  const up = values.length > 1 && values[values.length - 1] >= values[0]
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={values.map((v, i) => ({ i, v }))} margin={{ top: 3, right: 2, bottom: 3, left: 2 }}>
          <YAxis domain={['dataMin', 'dataMax']} hide />
          <Line type="monotone" dataKey="v" stroke={up ? 'var(--up)' : 'var(--down)'} strokeWidth={1.6} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 估值走势：一条线加历史中位数参考线。 */
export const SeriesLine: React.FC<{ data: { date: string; value: number | null }[]; median?: number; label: string }> = ({ data, median, label }) => (
  <div className="h-[220px] rounded-lg border border-hairline p-3">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
        <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={64} tickFormatter={(v: string) => v.slice(0, 7)} />
        <YAxis domain={['auto', 'auto']} tick={AXIS} tickLine={false} axisLine={false} width={44} />
        {median != null ? <ReferenceLine y={median} stroke="var(--stone)" strokeDasharray="4 4" label={{ value: `中位 ${median}`, fill: 'var(--steel)', fontSize: 11, position: 'insideTopRight' }} /> : null}
        <Tooltip contentStyle={TOOLTIP} formatter={(v) => [Number(v).toFixed(2), label]} labelStyle={{ color: 'var(--steel)' }} />
        <Line type="monotone" dataKey="value" stroke="var(--primary)" strokeWidth={1.6} dot={false} isAnimationActive={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  </div>
)
