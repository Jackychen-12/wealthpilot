export function AiInsight({ children }: { children: React.ReactNode }) {
  return (
    <div className="ai-note">
      <div className="ai-note-label">Pilot AI 解读</div>
      {children}
    </div>
  )
}
