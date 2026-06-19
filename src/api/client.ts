/**
 * API 客户端 — 封装后端调用 + demo 模式 fallback。
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const MAX_RETRIES = 2

let _demoMode = false
export function isDemoMode() { return _demoMode }

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('wp_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function fetchWithRetry(url: string, init: RequestInit, retries = MAX_RETRIES): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(url, init)
      if (res.ok || res.status < 500 || attempt >= retries) return res
      console.warn(`[api] ${url} returned ${res.status}, retry ${attempt + 1}/${retries}`)
    } catch (err) {
      if (attempt >= retries) throw err
      console.warn(`[api] ${url} failed, retry ${attempt + 1}/${retries}`)
    }
    await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
  }
}

export async function apiFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const resp = await fetchWithRetry(`${API_BASE}${path}`, { headers: { ...authHeaders() } })
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch (err) {
    _demoMode = true
    console.warn(`[api] GET ${path} → demo fallback`, err instanceof Error ? err.message : '')
    return fallback
  }
}

export async function apiPost<TReq, TRes>(path: string, body: TReq, fallback: TRes): Promise<TRes> {
  try {
    const resp = await fetchWithRetry(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch (err) {
    _demoMode = true
    console.warn(`[api] POST ${path} → demo fallback`, err instanceof Error ? err.message : '')
    return fallback
  }
}

export async function apiPut<TReq, TRes>(path: string, body: TReq): Promise<TRes | null> {
  try {
    const resp = await fetchWithRetry(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    })
    if (!resp.ok) throw new Error(`${resp.status}`)
    return await resp.json()
  } catch (err) {
    console.warn(`[api] PUT ${path} failed`, err instanceof Error ? err.message : '')
    return null
  }
}

export async function apiDelete(path: string): Promise<boolean> {
  try {
    const resp = await fetchWithRetry(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    })
    return resp.ok
  } catch (err) {
    console.warn(`[api] DELETE ${path} failed`, err instanceof Error ? err.message : '')
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
  agent?: string
  label?: string
  reason?: string
}

export async function* fetchSSE(path: string, body: unknown): AsyncGenerator<SSEEvent> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
        } catch { /* skip malformed SSE */ }
      }
    }
  }
}
