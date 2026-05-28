export function NavBar({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <div className="nav">
      {onBack ? (
        <span className="nav-back" onClick={onBack}>&lsaquo;</span>
      ) : (
        <span style={{ width: 32 }} />
      )}
      <span className="nav-title">{title}</span>
      <span className="nav-right">&#8942;</span>
    </div>
  )
}
