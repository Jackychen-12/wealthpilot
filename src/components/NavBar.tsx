export function NavBar({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <div className="nav">
      {onBack ? (
        <span className="nav-back" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </span>
      ) : (
        <span style={{ width: 32 }} />
      )}
      <span className="nav-title">{title}</span>
      <span style={{ width: 32 }} />
    </div>
  )
}
