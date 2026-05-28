export function MetricBox({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className="metric-box">
      <div className="metric-val" style={{ color }}>{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  )
}

export function MetricGrid({ children }: { children: React.ReactNode }) {
  return <div className="metric-grid">{children}</div>
}
