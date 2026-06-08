/**
 * API 客户端 — 封装后端调用 + mock fallback。
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function apiFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const resp = await fetch(`${API_BASE}${path}`)
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch {
    return fallback
  }
}

export async function apiPost<TReq, TRes>(path: string, body: TReq, fallback: TRes): Promise<TRes> {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch {
    return fallback
  }
}

export async function apiPut<TReq, TRes>(path: string, body: TReq): Promise<TRes | null> {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch {
    return null
  }
}

export async function apiDelete(path: string): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}${path}`, { method: 'DELETE' })
    return resp.ok
  } catch {
    return false
  }
}

// SSE streaming for chat
export interface SSEEvent {
  type: string
  content: string
  follow_ups?: string[]
  tool?: string
  input?: unknown
}

export async function* fetchSSE(path: string, body: unknown): AsyncGenerator<SSEEvent> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!resp.ok) {
    yield { type: 'error', content: `API error: ${resp.status}` }
    return
  }

  const reader = resp.body?.getReader()
  if (!reader) {
    yield { type: 'error', content: 'No response body' }
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6))
        } catch { /* skip */ }
      }
    }
  }
}
