import { colors } from '../utils/theme'

const labels = ['收益表现', '波动控制', '分散度', '风格匹配', '风险收益比']

interface RadarChartProps {
  scores?: number[]
}

export function RadarChart({ scores }: RadarChartProps) {
  const cx = 115
  const cy = 115
  const R = 85

  const angles = [0, 1, 2, 3, 4].map(j => ((j * 72 - 90) * Math.PI) / 180)

  const rings = [1, 0.7, 0.4].map((scale, i) => {
    const r = R * scale
    const points = angles.map(a => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`).join(' ')
    return <polygon key={i} points={points} fill="none" stroke="#E5E6EB" strokeWidth="0.5" />
  })

  const axes = angles.map((a, i) => (
    <line key={i} x1={cx} y1={cy} x2={cx + R * Math.cos(a)} y2={cy + R * Math.sin(a)} stroke="#E5E6EB" strokeWidth="0.5" />
  ))

  const values = scores ?? [80, 75, 55, 30, 70]
  const dataPoints = values.map((v, i) => {
    const ratio = Math.max(0, Math.min(100, v)) / 100
    const r = R * ratio
    return [cx + r * Math.cos(angles[i]), cy + r * Math.sin(angles[i])] as [number, number]
  })

  const dotColors = values.map(v => v >= 70 ? colors.primary : v >= 50 ? colors.warning : colors.danger)

  const dataPolygon = dataPoints.map(p => p.join(',')).join(' ')

  const labelPositions = [
    [cx, cy - R - 12],
    [cx + R + 15, cy - 10],
    [cx + R * 0.6, cy + R + 14],
    [cx - R * 0.6, cy + R + 14],
    [cx - R - 20, cy - 10],
  ]

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 16px' }}>
      <svg width="230" height="230" viewBox="0 0 230 230">
        {rings}
        {axes}
        <polygon
          className="radar-polygon"
          points={dataPolygon}
          fill={colors.primary}
          fillOpacity="0.1"
          stroke={colors.primary}
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        {dataPoints.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={4} fill={dotColors[i]} />
        ))}
        {labels.map((text, i) => (
          <text
            key={i}
            x={labelPositions[i][0]}
            y={labelPositions[i][1]}
            textAnchor="middle"
            fontSize="11"
            fill={colors.textSecondary}
            fontWeight="500"
          >
            {text}
          </text>
        ))}
        {values.map((v, i) => (
          <text
            key={`score-${i}`}
            x={dataPoints[i][0]}
            y={dataPoints[i][1] - 8}
            textAnchor="middle"
            fontSize="9"
            fill={dotColors[i]}
            fontWeight="600"
          >
            {v}
          </text>
        ))}
      </svg>
    </div>
  )
}
