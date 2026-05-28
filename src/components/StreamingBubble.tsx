import { useEffect, useRef } from 'react'
import { useTypingEffect } from '../hooks/useTypingEffect'

export function StreamingBubble({ text, onDone }: { text: string; onDone?: () => void }) {
  const { displayed, done } = useTypingEffect(text, 20)
  const calledRef = useRef(false)

  useEffect(() => {
    if (done && onDone && !calledRef.current) {
      calledRef.current = true
      onDone()
    }
  }, [done, onDone])

  return (
    <div className="chat-ai">
      <div className="chat-avatar">AI</div>
      <div className="chat-bubble-ai" style={{ whiteSpace: 'pre-wrap' }}>
        {displayed}
        {!done && <span className="typing-cursor" />}
      </div>
    </div>
  )
}
