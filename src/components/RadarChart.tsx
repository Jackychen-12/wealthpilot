import { colors } from '../utils/theme'

const labels = ['收益表现', '波动控制', '分散度', '风格匹配', '风险收益比']
const dataPoints = [
  [115, 34],
  [172, 85],
  [152, 178],
  [62, 172],
  [60, 82],
]
const dotColors = [colors.primary, colors.primary, colors.warning, colors.danger, colors.primary]

export function RadarChart() {
  const cx = 115
  const cy = 115

  const rings = [1, 0.7, 0.4].map((scale, i) => {
    const r = 85 * scale
    const points = [0, 1, 2, 3, 4]
      .map((j) => {
        const angle = ((j * 72 - 90) * Math.PI) / 180
        return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`
      })
      .join(' ')
    return <polygon key={i} points={points} fill="none" stroke="#E5E6EB" strokeWidth="0.5" />
  })

  const dataPolygon = dataPoints.map((p) => p.join(',')).join(' ')

  const labelPositions = [
    [115, 18],
    [210, 88],
    [175, 192],
    [20, 192],
    [14, 82],
  ]

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 16px' }}>
      <svg width="230" height="230" viewBox="0 0 230 230">
        {rings}
        <polygon
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
      </svg>
    </div>
  )
}
