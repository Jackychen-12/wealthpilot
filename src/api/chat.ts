import { fetchSSE, type SSEEvent } from './client'

export interface ChatMsg {
  role: 'user' | 'ai'
  content: string
}

export function streamChat(message: string, history: ChatMsg[], conversationId?: string): AsyncGenerator<SSEEvent> {
  return fetchSSE('/api/chat', {
    message,
    history: history.map(m => ({ role: m.role === 'ai' ? 'assistant' : 'user', content: m.content })),
    conversation_id: conversationId,
  })
}
