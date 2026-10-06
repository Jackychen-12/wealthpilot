/** 图表：K 线、热力图、占比环图、迷你走势。配色跟随 A 股习惯（红涨绿跌）。 */
import type React from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, Treemap, XAxis, YAxis } from 'recharts'

const AXIS = { fill: 'var(--steel)', fontSize: 11 }
export const TOOLTIP = { background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, fontSize: 13, boxShadow: 'rgba(15,15,15,0.08) 0 4px 12px' }
const UP = '224,49,49'
const DOWN = '18,137,58'

export interface Candle { nav_date: string; nav: number; open?: number; high?: number; low?: number; volume?: number }

const ma = (rows: Candle[], n: number, i: number) => (i + 1 < n ? null : rows.slice(i + 1 - n, i + 1).reduce((s, r) => s + r.nav, 0) / n)

/** MACD(12,26,9)：DIF 是快慢两条指数均线的差，DEA 是 DIF 的 9 日均线，柱子是两者之差的两倍。 */
function macd(rows: Candle[]): { dif: number; dea: number; bar: number }[] {
  let fast = 0
  let slow = 0
  let dea = 0
  return rows.map((r, i) => {
    fast = i === 0 ? r.nav : (fast * 11 + r.nav * 2) / 13
    slow = i === 0 ? r.nav : (slow * 25 + r.nav * 2) / 27
    const dif = fast - slow
    dea = i === 0 ? dif : (dea * 8 + dif * 2) / 10
    return { dif, dea, bar: (dif - dea) * 2 }
  })
}

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
export const Candles: React.FC<{ data: Candle[]; marks?: { date: string; label: string }[]; showMacd?: boolean }> = ({ data, marks = [], showMacd }) => {
  // 标记落在非交易日或被合成进周 / 月线时，挂到它之后最近的一根上；比最后一根还晚（今天做的研究）就挂在最后一根
  const pinned = marks.map((m) => ({ ...m, at: (data.find((r) => r.nav_date >= m.date) ?? data[data.length - 1])?.nav_date })).filter((m) => m.at)
  const signals = showMacd ? macd(data) : []
  const rows = data.map((r, i) => ({ ...r, up: r.nav >= (r.open ?? r.nav), range: [r.low ?? r.nav, r.high ?? r.nav] as [number, number],
    ma5: ma(data, 5, i), ma20: ma(data, 20, i), ma60: ma(data, 60, i), ...(signals[i] ?? {}) }))
  const tick = (v: string) => v.slice(5)
  return (
    <div className="rounded-lg border border-hairline p-3">
      <div className="mb-1 flex gap-4 px-1 text-xs text-steel">
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--primary)] align-middle" />MA5</span>
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--warning)] align-middle" />MA20</span>
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--stone)] align-middle" />MA60</span>
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
            <Line type="monotone" dataKey="ma60" name="MA60" stroke="var(--stone)" strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls />
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
      {showMacd ? (
        <div className="mt-1 h-[90px] border-t border-hairline-soft pt-1">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} syncId="kline" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <XAxis dataKey="nav_date" hide />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => v.toFixed(Math.abs(v) >= 10 ? 0 : 2)} />
              <ReferenceLine y={0} stroke="var(--hairline-strong)" />
              <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: 'var(--steel)' }} formatter={(v, name) => [Number(v).toFixed(3), name]} />
              <Bar dataKey="bar" name="MACD" isAnimationActive={false}>{rows.map((r) => <Cell key={r.nav_date} fill={(r.bar ?? 0) >= 0 ? 'var(--up)' : 'var(--down)'} fillOpacity={0.7} />)}</Bar>
              <Line type="monotone" dataKey="dif" name="DIF" stroke="var(--primary)" strokeWidth={1.1} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="dea" name="DEA" stroke="var(--warning)" strokeWidth={1.1} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </div>
  )
}

export interface MinutePoint { time: string; price: number; avg: number | null; volume: number }

/**
 * 分时：价格线、均价线、昨收参考线，下方每分钟成交量。单日时纵轴以昨收为中心上下对称，
 * 一眼看出是在昨收上方还是下方；五日连在一起看时不做对称。
 */
export const MinuteChart: React.FC<{ points: MinutePoint[]; prevClose: number | null; multiDay?: boolean }> = ({ points, prevClose, multiDay }) => {
  const last = points[points.length - 1]?.price ?? 0
  const up = prevClose == null ? true : last >= prevClose
  const color = up ? 'var(--up)' : 'var(--down)'
  const prices = points.map((p) => p.price)
  const swing = prevClose != null && !multiDay ? Math.max(...prices.map((v) => Math.abs(v - prevClose)), prevClose * 0.005) * 1.08 : null
  const domain: [number | string, number | string] = swing != null && prevClose != null ? [prevClose - swing, prevClose + swing] : ['auto', 'auto']
  // 单日：刻度以昨收为中心对称排开，中间那根就是昨收
  const ticks = swing != null && prevClose != null ? [-1, -0.5, 0, 0.5, 1].map((k) => Number((prevClose + swing * k).toFixed(2))) : undefined
  const rows = points.map((p, i) => ({ ...p, rise: i === 0 ? true : p.price >= points[i - 1].price }))
  const pct = (v: number) => (prevClose ? `${v >= prevClose ? '+' : ''}${(((v - prevClose) / prevClose) * 100).toFixed(2)}%` : '')
  const tick = (v: string) => (multiDay ? v.slice(5, 10) : v.slice(-5))
  return (
    <div className="rounded-lg border border-hairline p-3">
      <div className="mb-1 flex gap-4 px-1 text-xs text-steel">
        <span><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: color }} />价格</span>
        <span><i className="mr-1 inline-block h-0.5 w-3 bg-[var(--warning)] align-middle" />当日均价</span>
        {prevClose != null ? <span><i className="mr-1 inline-block h-0 w-3 border-t border-dashed border-[var(--stone)] align-middle" />昨收 {prevClose}</span> : null}
      </div>
      <div className="h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} syncId="minute" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
            <XAxis dataKey="time" hide />
            <YAxis domain={domain} ticks={ticks} tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => v.toFixed(v >= 100 ? 1 : 2)} />
            {prevClose != null ? <ReferenceLine y={prevClose} stroke="var(--stone)" strokeDasharray="4 4" /> : null}
            <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: 'var(--steel)' }}
              formatter={(v, name) => [name === '价格' ? `${Number(v).toFixed(2)}  ${pct(Number(v))}` : Number(v).toFixed(2), name]} />
            <Line type="linear" dataKey="price" name="价格" stroke={color} strokeWidth={1.4} dot={false} isAnimationActive={false} />
            {multiDay ? null : <Line type="linear" dataKey="avg" name="均价" stroke="var(--warning)" strokeWidth={1.1} dot={false} isAnimationActive={false} connectNulls />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="h-[70px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} syncId="minute" margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="time" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={multiDay ? 80 : 56} tickFormatter={tick} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => (v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v))} />
            <Tooltip contentStyle={TOOLTIP} formatter={(v) => [`${Number(v).toLocaleString()} 手`, '成交量']} labelStyle={{ color: 'var(--steel)' }} />
            <Bar dataKey="volume" isAnimationActive={false}>{rows.map((r) => <Cell key={r.time} fill={r.rise ? 'var(--up)' : 'var(--down)'} fillOpacity={0.55} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/**
 * 一组数叠在股价上看：左轴是柱子或线（资金净流入、融资余额、股东户数），右轴是收盘价。
 * 资金类数据单看没有意义，要和价格放在一起才知道"钱进来的时候股价涨没涨"。
 */
export const PriceOverlay: React.FC<{
  data: { label: string; value: number | null; close: number | null }[]
  name: string; unit: string; kind?: 'bar' | 'line'; signed?: boolean; height?: number
}> = ({ data, name, unit, kind = 'bar', signed, height = 230 }) => (
  <div className="rounded-lg border border-hairline p-3" style={{ height }}>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} minTickGap={36} />
        <YAxis yAxisId="left" domain={kind === 'line' ? ['auto', 'auto'] : undefined} tick={AXIS} tickLine={false} axisLine={false} width={52}
          tickFormatter={(v: number) => (Math.abs(v) >= 1e4 ? `${(v / 1e4).toFixed(1)}万` : String(Number(v.toFixed(2))))} />
        <YAxis yAxisId="right" orientation="right" domain={['auto', 'auto']} tick={AXIS} tickLine={false} axisLine={false} width={52}
          tickFormatter={(v: number) => v.toFixed(v >= 100 ? 0 : 2)} />
        {signed ? <ReferenceLine yAxisId="left" y={0} stroke="var(--hairline-strong)" /> : null}
        <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: 'var(--steel)' }}
          formatter={(v, key) => (key === '收盘价' ? [Number(v).toFixed(2), key] : [`${Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`, key])} />
        {kind === 'bar'
          ? <Bar yAxisId="left" dataKey="value" name={name} isAnimationActive={false} maxBarSize={18}>
            {data.map((d) => <Cell key={d.label} fill={signed ? ((d.value ?? 0) >= 0 ? 'var(--up)' : 'var(--down)') : 'var(--primary)'} fillOpacity={signed ? 0.75 : 0.45} />)}
          </Bar>
          : <Line yAxisId="left" type="monotone" dataKey="value" name={name} stroke="var(--primary)" strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls />}
        <Line yAxisId="right" type="monotone" dataKey="close" name="收盘价" stroke="var(--stone)" strokeWidth={1.3} strokeDasharray="4 3" dot={false} isAnimationActive={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  </div>
)

/** 简单柱状图：每根柱子一个标签一个数，正红负绿（signed）或统一主色。柱顶直接标数，不用把鼠标挪上去。 */
export const ValueBars: React.FC<{ title: string; data: { label: string; value: number | null; muted?: boolean }[]; unit: string; signed?: boolean; height?: number }> = ({ title, data, unit, signed, height = 220 }) => (
  <div className="min-w-0 flex-1 rounded-lg border border-hairline p-3">
    <p className="mb-1 px-1 text-[13px] font-medium text-steel">{title}</p>
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--hairline-soft)" vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--hairline)' }} interval={0} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
          {signed ? <ReferenceLine y={0} stroke="var(--hairline-strong)" /> : null}
          <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: 'var(--steel)' }} cursor={{ fill: 'var(--surface-soft)' }}
            formatter={(v) => [`${Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} ${unit}`, title]} />
          <Bar dataKey="value" isAnimationActive={false} maxBarSize={34} radius={[2, 2, 0, 0]}
            label={{ position: 'top', fill: 'var(--steel)', fontSize: 11, formatter: (v: unknown) => (typeof v === 'number' ? Number(v.toFixed(Math.abs(v) >= 100 ? 0 : 2)).toLocaleString() : '') }}>
            {data.map((d) => <Cell key={d.label} fill={signed ? ((d.value ?? 0) >= 0 ? 'var(--up)' : 'var(--down)') : 'var(--primary)'} fillOpacity={d.muted ? 0.35 : 0.8} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)

const RATING_COLOR: Record<string, string> = { 买入: 'var(--up)', 增持: '#f08c8c', 中性: 'var(--stone)', 减持: '#74c69d', 卖出: 'var(--down)' }

/** 评级分布：一条分段的横条，每段的宽度是给这个评级的机构数。 */
export const RatingBar: React.FC<{ ratings: Record<string, number> }> = ({ ratings }) => {
  const entries = Object.entries(ratings).filter(([, n]) => n > 0)
  const total = entries.reduce((s, [, n]) => s + n, 0)
  if (!total) return null
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-surface">
        {entries.map(([name, n]) => <span key={name} style={{ width: `${(n / total) * 100}%`, background: RATING_COLOR[name] ?? 'var(--stone)' }} title={`${name} ${n} 家`} />)}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[13px] text-steel">
        {Object.entries(ratings).map(([name, n]) => (
          <span key={name} className={n ? 'text-charcoal' : 'text-stone'}><i className="mr-1 inline-block h-2 w-2 rounded-full align-middle" style={{ background: RATING_COLOR[name] ?? 'var(--stone)', opacity: n ? 1 : 0.35 }} />{name} {n}</span>
        ))}
      </div>
    </div>
  )
}

/** 一段区间和一个当前位置：比如券商目标价区间和现价。现价在区间外时也画得出来；三个数都标在各自的位置上。 */
export const RangeMarker: React.FC<{ low: number; high: number; current: number; currentLabel: string }> = ({ low, high, current, currentLabel }) => {
  const min = Math.min(low, current)
  const max = Math.max(high, current)
  const pad = (max - min || 1) * 0.06
  const at = (v: number) => ((v - (min - pad)) / (max - min + pad * 2)) * 100
  const label = (v: number, text: string, strong?: boolean) => (
    <span className={`absolute top-0 -translate-x-1/2 whitespace-nowrap ${strong ? 'font-medium text-ink' : 'text-steel'}`} style={{ left: `${at(v)}%` }}>{text}</span>
  )
  return (
    <div>
      <div className="relative h-2 rounded-full bg-surface">
        <span className="absolute inset-y-0 rounded-full bg-[var(--primary)] opacity-30" style={{ left: `${at(low)}%`, width: `${at(high) - at(low)}%` }} />
        <span className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" style={{ left: `${at(current)}%` }} />
      </div>
      <div className="relative mt-1.5 h-5 text-[13px]">
        {label(low, String(low))}{label(high, String(high))}{label(current, currentLabel, true)}
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
