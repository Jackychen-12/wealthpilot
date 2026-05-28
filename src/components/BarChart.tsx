import { colors } from '../utils/theme'

export function BarChart({
  name,
  value,
  pct,
  positive,
}: {
  name: string
  value: string
  pct: number
  positive: boolean
}) {
  const color = positive ? colors.danger : colors.success
  return (
    <div className="bar-wrap">
      <div className="bar-head">
        <span style={{ color: colors.text }}>{name}</span>
        <span style={{ fontWeight: 600, color, fontFamily: 'DM Sans' }}>{value}</span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}
