export function MetricBox({ value, label, color }: { value: string; label: string; color: string }) {
  const dotColor = value.startsWith('+') ? '#10B981' : value.startsWith('-') ? '#EF4444' : 'transparent'
  return (
    <div className="metric-box">
      <div className="metric-val" style={{ color }}>
        <span className="metric-dot" style={{ background: dotColor }} />
        {value}
      </div>
      <div className="metric-label">{label}</div>
    </div>
  )
}

export function MetricGrid({ children }: { children: React.ReactNode }) {
  return <div className="metric-grid">{children}</div>
}
