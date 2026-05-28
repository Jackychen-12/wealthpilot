export function Tag({ color, bg, children }: { color: string; bg: string; children: React.ReactNode }) {
  return (
    <span className="tag" style={{ background: bg, color }}>
      {children}
    </span>
  )
}
