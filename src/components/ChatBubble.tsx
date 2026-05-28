export function AiBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="chat-ai">
      <div className="chat-avatar">AI</div>
      <div className="chat-bubble-ai">{children}</div>
    </div>
  )
}

export function UserBubble({ children }: { children: React.ReactNode }) {
  return <div className="chat-bubble-user">{children}</div>
}
