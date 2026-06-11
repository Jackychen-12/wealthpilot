export function AiBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="chat-ai">
      <div className="chat-avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#fff" opacity="0.9"/>
          <path d="M2 17l10 5 10-5" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity="0.6"/>
          <path d="M2 12l10 5 10-5" stroke="#fff" strokeWidth="2" strokeLinecap="round" opacity="0.8"/>
        </svg>
      </div>
      <div className="chat-bubble-ai">{children}</div>
    </div>
  )
}

export function UserBubble({ children }: { children: React.ReactNode }) {
  return <div className="chat-bubble-user">{children}</div>
}
