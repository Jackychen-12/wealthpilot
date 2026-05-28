export function QuickPills({ items }: { items: string[] }) {
  return (
    <div className="quick-pills">
      {items.map((q, i) => (
        <div key={i} className="quick-pill">{q}</div>
      ))}
    </div>
  )
}
