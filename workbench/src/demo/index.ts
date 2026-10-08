/**
 * 在线演示模式（构建时 VITE_DEMO=1）。
 *
 * 在线演示没有后端，这里回放 backend/scripts/record_demo.py 录下的真实结果：
 * 一份示例组合在真实行情、真实工具、真实模型上跑出来的接口返回和研究过程。
 * 只读 —— 任何写操作、以及没录过的查询，都如实告知"演示模式不支持"。
 */
import type { StreamEvent } from '../api'
import fixtures from './fixtures.json'

type Fixtures = {
  recorded_at: string
  get: Record<string, unknown>
  post?: Record<string, { inputs: unknown; result: unknown }>
  tools: Record<string, { inputs: Record<string, unknown>; result: unknown }>
  chats: Record<string, (StreamEvent & { t: number })[]>
}
const data = fixtures as unknown as Fixtures

export const DEMO_RECORDED_AT = data.recorded_at
export const DEMO_QUESTIONS = Object.keys(data.chats)
export const DEMO_FUND = '110011'

/** 键排序后的 JSON，用来比较两组入参是否等价。 */
const canonical = (v: unknown): string =>
  JSON.stringify(v, (_, x: unknown) =>
    x && typeof x === 'object' && !Array.isArray(x)
      ? Object.fromEntries(Object.entries(x as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : x)
const describe = (inputs: Record<string, unknown>) => JSON.stringify(inputs).replace(/[{}"]/g, '').replace(/,/g, '，')

const READ_ONLY = '在线演示是只读的示例数据。在本地运行工作台后才能修改。'
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function demoRequest(path: string, init: RequestInit): Promise<unknown> {
  await sleep(180) // 留一点加载过程，和真实使用的观感一致
  const method = (init.method || 'GET').toUpperCase()

  if (method === 'GET') {
    if (path in data.get) return data.get[path]
    if (path in EMPTY_IN_DEMO) return EMPTY_IN_DEMO[path]
    if (path.startsWith(SEARCH)) return demoSearch(decodeURIComponent(path.slice(SEARCH.length)))
    if (path.startsWith('/api/filings/')) throw new Error('在线演示只录了一条公告的正文')
    if (path.startsWith('/api/market/fund/')) throw new Error(`在线演示只录了 ${DEMO_FUND} 这一只基金的数据`)
    if (path.startsWith('/api/market/stock/')) throw new Error('在线演示只录了贵州茅台（600519）这一只股票的数据')
    throw new Error('在线演示没有录这项数据')
  }

  const tool = path.match(/^\/api\/tools\/(\w+)$/)?.[1]
  if (method === 'POST' && tool) {
    const recorded = data.tools[tool]
    if (!recorded) throw new Error('在线演示没有录这个工具的结果')
    const inputs = JSON.parse(String(init.body || '{}')) as unknown
    // 只在参数与录制时一致才回放 —— 否则会出现"填的是 A、显示的是 B 的结果"
    if (canonical(inputs) !== canonical(recorded.inputs)) {
      throw new Error(`在线演示只录了一组参数的结果：${describe(recorded.inputs)}。换别的参数需要在本地运行。`)
    }
    return recorded.result
  }
  const posted = method === 'POST' ? data.post?.[path] : undefined
  if (posted) {
    const inputs = JSON.parse(String(init.body || '{}')) as Record<string, unknown>
    if (canonical(inputs) !== canonical(posted.inputs)) {
      throw new Error(`在线演示只录了一组条件的结果：${describe(posted.inputs as Record<string, unknown>)}。换别的条件需要在本地运行。`)
    }
    return posted.result
  }
  throw new Error(READ_ONLY)
}

// 录制这份示例数据时还没有的列表：示例账户里它们本来就是空的，照实给空列表，页面显示"还没有"，而不是报错
const EMPTY_IN_DEMO: Record<string, unknown> = {
  '/api/lessons': [], '/api/skills/suggestions': [], '/api/conversations': [], '/api/chat/runs/active': [],
}

const SEARCH = '/api/securities/search?q='
type Hit = { code: string; name: string }
/** 演示里的搜索只在录过的那几只证券里找，找不到就如实返回空。 */
function demoSearch(query: string): Hit[] {
  const q = query.trim().toLowerCase()
  const seen = new Map<string, Hit>()
  for (const [path, hits] of Object.entries(data.get)) {
    if (path.startsWith(SEARCH)) for (const h of hits as Hit[]) seen.set(h.code, h)
  }
  return [...seen.values()].filter((h) => h.code.includes(q) || h.name.replace(/\s/g, '').toLowerCase().includes(q))
}

/** 按录制时的节奏回放一次研究（间隔压缩到原来的 1/4，免得演示时干等）。 */
export async function* demoChat(message: string, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const events = data.chats[message.trim()]
  if (!events) {
    yield { type: 'error', content: '在线演示只能回放预先录好的问题，请从首页的示例问题里选。' }
    yield { type: 'done', content: '在线演示没有连接模型，无法回答新问题。在本地运行工作台并配置模型 Key 后即可自由提问。', meta: { status: 'failed' } }
    return
  }
  let last = 0
  for (const { t, ...event } of events) {
    await sleep(Math.min(1500, Math.max(120, (t - last) * 250)))
    last = t
    if (signal.aborted) throw new DOMException('aborted', 'AbortError')
    yield event
  }
}
