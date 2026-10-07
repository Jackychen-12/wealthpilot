/**
 * 研究会话的状态放在模块级 store 里，而不是页面组件里 ——
 * 切到别的页面再回来，对话和正在跑的研究都还在。
 */
import { useSyncExternalStore } from 'react'
import { DEMO, api, attachRun, streamChat, type ActiveRun, type Checkpoint, type ConversationTurn, type Debate, type Depth, type Proposal, type Reused, type Security, type StreamEvent, type SummaryCard, type Usage } from '../api'

export interface Evidence { id: string; tool: string; agent: string; taskId: string; ok: boolean; input: string; output: string; asOf: string; source: string }
export interface Task { id: string; agent: string; goal: string; state: 'pending' | 'running' | 'done' | 'failed' }
export interface Check { tone: 'ok' | 'bad' | 'warn' | 'info'; text: string }
export interface Turn {
  id: number; question: string; answer: string; status: string; running: boolean
  intent: string; fallbackPlan: boolean; tasks: Task[]; criteria: string[]; evidence: Evidence[]; checks: Check[]
  missing: string[]; followUps: string[]; seconds: number; error: string
  playbook: string; securities: Security[]; checkpoints: Checkpoint[]; proposals: Proposal[]; usage: Usage | null
  /** 预计用时（秒，来自同类研究的历史耗时）；0 表示还不知道 */
  eta: number
  depth: Depth; summary: SummaryCard | null
  /** 多空辩论：看多、看空两方就同一批证据各自给出的理由 */
  debate: Debate | null
  /** 服务端这次研究的编号：页面刷新后凭它接回来，点停止时凭它叫停 */
  runId: string
  /** 开跑前估的 token 消耗（同类研究最近几次的平均）；没有记录时是 0 */
  etaTokens: number
  /** 研究没成是因为模型用不了：balance / auth / model / rate_limit / network / budget / not_configured */
  reason: string
  /** 这次没有重新取数，沿用了之前那次研究的数据 */
  reused: Reused | null
  /** 后端存下的消息 ID —— 之后“更短一点”这类改写靠它找到这次研究的证据 */
  messageId: number | null
  /** 这是基于哪一次回答改写的（界面上显示成“改写”而不是新的研究） */
  rewriteOf: number | null
}

interface State { turns: Turn[]; selected: number | null; focusEvidence: string }

// 会话存在浏览器本地：刷新页面、关了再开，问过的和答过的都还在。只留最近几轮，证据原文截短，免得把本地存储撑满。
const STORE_KEY = 'wp_research_v1'
const KEEP_TURNS = 6
function load(): { turns: Turn[]; conversationId: string } {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null') as { turns?: Turn[]; conversationId?: string } | null
    if (saved?.conversationId && Array.isArray(saved.turns)) {
      // 上次离开时还在跑的那一轮先标成中断；真还在服务端跑着的话，下面会把它接回来
      return { conversationId: saved.conversationId, turns: saved.turns.map(t => (t.running ? { ...t, running: false, status: 'failed', error: '页面刷新时这次研究还没跑完' } : t)) }
    }
  } catch { /* 存的东西坏了就当没有 */ }
  return { turns: [], conversationId: crypto.randomUUID() }
}
function persist() {
  try {
    const turns = state.turns.slice(-KEEP_TURNS).map(t => ({ ...t, evidence: t.evidence.map(e => ({ ...e, output: e.output.slice(0, 1200) })) }))
    localStorage.setItem(STORE_KEY, JSON.stringify({ conversationId, turns }))
  } catch { /* 存不下就只在本次生效 */ }
}

const restored = DEMO ? { turns: [] as Turn[], conversationId: crypto.randomUUID() } : load()
let state: State = { turns: restored.turns, selected: restored.turns[restored.turns.length - 1]?.id ?? null, focusEvidence: '' }
const listeners = new Set<() => void>()
let controller: AbortController | null = null
let nextId = restored.turns.reduce((max, t) => Math.max(max, t.id), 0) + 1
// 同一次会话里的问答共用一个 ID，后端据此把它们存进研究记录
let conversationId = restored.conversationId

const emit = (next: State) => { state = next; listeners.forEach(l => l()) }
const patch = (id: number, fn: (t: Turn) => Turn) => emit({ ...state, turns: state.turns.map(t => (t.id === id ? fn(t) : t)) })
const clip = (v: unknown, max: number) => {
  const s = typeof v === 'string' ? v : JSON.stringify(v, null, 1)
  return s.length > max ? `${s.slice(0, max)}…` : s
}

function apply(turn: Turn, e: StreamEvent): Turn {
  const setTask = (state: Task['state']): Task[] =>
    turn.tasks.some(t => t.id === e.id)
      ? turn.tasks.map(t => (t.id === e.id ? { ...t, state } : t))
      : [...turn.tasks, { id: e.id || String(turn.tasks.length), agent: e.agent || '', goal: e.goal || '', state }]
  switch (e.type) {
    case 'run': return { ...turn, runId: e.run_id || '' }
    case 'ping': return turn
    case 'reused':
      return { ...turn, reused: { message_id: e.message_id ?? 0, age: e.age || '', age_minutes: 0, saved_tokens: e.saved_tokens ?? null, mode: e.mode === 'replay' ? 'replay' : 'evidence' } }
    case 'resolved': return { ...turn, securities: e.securities || [] }
    case 'checkpoints': return { ...turn, checkpoints: e.items || [], proposals: e.proposals || [] }
    case 'plan':
      return { ...turn, playbook: e.playbook || '', intent: e.intent || '', fallbackPlan: e.source === 'fallback', criteria: e.success_criteria || [], eta: e.eta_seconds || 0, etaTokens: e.eta_tokens || 0,
        tasks: (e.tasks || []).map(t => ({ ...t, state: 'pending' as const })) }
    case 'task_start': return { ...turn, tasks: setTask('running') }
    case 'task_done': return { ...turn, tasks: setTask(e.status === 'completed' ? 'done' : 'failed') }
    case 'evidence': {
      const v = e.evidence
      if (!v) return turn
      const asOf = Object.values(v.provenance?.as_of || {}).filter(Boolean).sort().pop() || ''
      // 同一个 Agent 可能先后跑两个任务（补查），证据归到当时正在跑的那个
      const owner = [...turn.tasks].reverse().find(t => t.agent === e.agent && t.state === 'running')
      return { ...turn, evidence: [...turn.evidence, {
        id: v.id, tool: v.tool, agent: e.agent || '', taskId: owner?.id || '', ok: v.status === 'ok',
        input: clip(v.input ?? {}, 300), output: clip(v.output ?? '', 4000),
        asOf: asOf as string, source: v.provenance?.sources?.[0]?.url || '',
      }] }
    }
    case 'critic': {
      const name = e.gate === 'evidence' ? '证据审核' : `回答校验（第 ${e.attempt ?? 1} 稿）`
      return { ...turn, checks: [...turn.checks, e.passed
        ? { tone: 'ok', text: `${name}通过` }
        : { tone: 'bad', text: `${name}打回：${(e.issues || []).join('；')}` }] }
    }
    case 'debate':
      return e.bull && e.bear ? { ...turn, debate: { bull: e.bull, bear: e.bear }, checks: [...turn.checks, { tone: 'info', text: '多空两方已各自陈述，开始撰写' }] } : turn
    case 'replan':
      return { ...turn, checks: [...turn.checks, { tone: 'warn', text: `补充查证：${(e.tasks || []).map(t => t.goal.replace(/^补充查证：/, '')).join('；')}` }] }
    case 'synthesizing':
      return { ...turn, checks: [...turn.checks, { tone: 'info', text: e.mode === 'rewrite' ? '基于已有证据改写' : e.mode === 'repair' ? '按校验意见修订' : `整合 ${e.agents?.length ?? 0} 个任务的证据，撰写回答` }] }
    case 'grounding_warning': return { ...turn, checks: [...turn.checks, { tone: 'warn', text: `数字未能溯源：${(e.ungrounded || []).join('、')}` }] }
    case 'error': return { ...turn, checks: [...turn.checks, { tone: 'bad', text: e.content || '出错' }] }
    case 'delta': return { ...turn, answer: turn.answer + (e.content || '') }
    case 'done':
      return { ...turn, answer: e.content || turn.answer, status: e.meta?.status || 'passed', running: false,
        missing: e.meta?.missing_evidence || [], followUps: e.follow_ups || [], usage: e.meta?.usage ?? null,
        summary: e.meta?.summary ?? null, messageId: e.meta?.message_id ?? null, playbook: turn.playbook || e.meta?.playbook || '',
        reason: e.meta?.reason || '', reused: e.meta?.reused ?? turn.reused, debate: turn.debate ?? e.meta?.debate ?? null }
    default: return turn
  }
}

export const research = {
  select: (id: number) => emit({ ...state, selected: id, focusEvidence: '' }),
  focus: (turnId: number, evidenceId: string) => emit({ ...state, selected: turnId, focusEvidence: evidenceId }),
  /** 停止：研究在服务端独立运行，光断开连接它不会停，要明确告诉后端 */
  stop: () => {
    const running = state.turns.find(t => t.running)
    if (running?.runId) void api.stopRun(running.runId).catch(() => undefined)
    controller?.abort()
  },
  clear: () => { research.stop(); conversationId = crypto.randomUUID(); emit({ turns: [], selected: null, focusEvidence: '' }); persist() },
  get busy() { return state.turns.some(t => t.running) },
  get conversationId() { return conversationId },

  /** 打开一个以前的会话：把每一轮连同当时的证据恢复出来，之后的提问接在它后面。 */
  async open(id: string) {
    if (research.busy) return
    const data = await api.conversation(id)
    const turns = data.turns.map((r, i) => fromRecord(r, i + 1))
    conversationId = id
    nextId = turns.length + 1
    emit({ turns, selected: turns[turns.length - 1]?.id ?? null, focusEvidence: '' })
    persist()
  },

  /**
   * 提问。options.depth 选快速还是深入；options.rewriteOf 给了某一轮的 id，就不重新研究，
   * 只基于那一轮已经取到的证据按新的要求重写（几秒钟）。
   */
  async ask(question: string, options: { depth?: Depth; rewriteOf?: number } = {}) {
    if (research.busy || !question.trim()) return
    const id = nextId++
    const source = options.rewriteOf != null ? state.turns.find(t => t.id === options.rewriteOf) : undefined
    const history = state.turns.filter(t => t.status && t.answer).slice(-5)
      .flatMap(t => [{ role: 'user', content: t.question }, { role: 'assistant', content: t.answer }])
    const turn: Turn = { id, question: question.trim(), answer: '', status: '', running: true, intent: '', fallbackPlan: false,
      tasks: [], criteria: [], evidence: [], checks: [], missing: [], followUps: [], seconds: 0, error: '', playbook: '',
      securities: source?.securities ?? [], checkpoints: [], proposals: [], usage: null,
      eta: 0, depth: options.depth ?? 'auto', summary: null, debate: null, runId: '', etaTokens: 0, reason: '', reused: null, messageId: null, rewriteOf: source?.messageId ? source.id : null }
    emit({ turns: [...state.turns, turn], selected: id, focusEvidence: '' })
    const wasHidden = () => typeof document !== 'undefined' && document.hidden

    controller = new AbortController()
    await follow(id, Date.now(), streamChat(turn.question, history, controller.signal, conversationId,
      { depth: turn.depth, rewriteOf: source?.messageId ?? null }), wasHidden)
  },
}

/** 研究记录里的一轮 → 页面上的一轮。证据的原文截短，够点开看就行。 */
function fromRecord(r: ConversationTurn, id: number): Turn {
  const meta = r.meta || {}
  const evidence: Evidence[] = (meta.evidence || []).map(v => ({
    id: v.id, tool: v.tool, agent: '', taskId: '', ok: v.status === 'ok', input: clip(v.input ?? {}, 300), output: clip(v.output ?? '', 1200),
    asOf: (Object.values(v.provenance?.as_of || {}).filter(Boolean).sort().pop() as string) || '', source: v.provenance?.sources?.[0]?.url || '',
  }))
  return {
    id, question: r.question, answer: r.answer, status: meta.status || 'passed', running: false, intent: meta.intent || '', fallbackPlan: false,
    tasks: (meta.tasks || []).map(t => ({ ...t, state: 'done' as const })), criteria: [], evidence, checks: [], missing: meta.missing_evidence || [],
    followUps: [], seconds: meta.seconds || 0, error: '', playbook: meta.playbook || '', securities: meta.securities || [],
    checkpoints: r.checkpoints || [], proposals: r.proposals || [], usage: meta.usage ?? null,
    eta: 0, depth: (meta.depth as Depth) || 'auto', summary: meta.summary ?? null, debate: meta.debate ?? null, runId: '', etaTokens: 0, reason: '',
    reused: meta.reused ?? null, messageId: r.message_id, rewriteOf: meta.playbook === 'rewrite' ? 0 : null,
  }
}

/** 跟着一次研究的事件流走到结束。新发起的和刷新后接回来的都走这里。 */
async function follow(id: number, started: number, events: AsyncGenerator<StreamEvent>, wasHidden: () => boolean) {
  const clock = setInterval(() => patch(id, t => ({ ...t, seconds: (Date.now() - started) / 1000 })), 500)
  try {
    for await (const event of events) patch(id, t => apply(t, event))
    patch(id, t => (t.running ? { ...t, running: false, status: 'failed', error: '连接中断，没有收到完整回答。研究可能还在后台跑，刷新页面可以接回来' } : t))
    const finished = state.turns.find(t => t.id === id)
    if (finished && wasHidden()) announce(finished)
  } catch (err) {
    const aborted = err instanceof DOMException && err.name === 'AbortError'
    patch(id, t => ({ ...t, running: false, status: aborted ? 'stopped' : 'failed', error: aborted ? '已停止' : err instanceof Error ? err.message : '请求失败' }))
  } finally {
    clearInterval(clock)
    controller = null
    patch(id, t => ({ ...t, seconds: (Date.now() - started) / 1000 }))
    persist()
  }
}

/** 页面刷新之后：服务端要是还有这个会话的研究在跑，把它接回来，从头重放已经发生的过程。 */
async function resume() {
  let runs: ActiveRun[] = []
  try { runs = await api.activeRuns() } catch { return }
  const run = runs.find(r => r.conversation_id === conversationId) ?? runs[0]
  if (!run || state.turns.some(t => t.running)) return
  const stale = state.turns.find(t => !t.running && t.error === '页面刷新时这次研究还没跑完' && t.question === run.question)
  const id = stale?.id ?? nextId++
  const fresh: Turn = { id, question: run.question, answer: '', status: '', running: true, intent: '', fallbackPlan: false,
    tasks: [], criteria: [], evidence: [], checks: [], missing: [], followUps: [], seconds: 0, error: '', playbook: '',
    securities: [], checkpoints: [], proposals: [], usage: null,
    eta: 0, depth: run.depth, summary: null, debate: null, runId: run.run_id, etaTokens: 0, reason: '', reused: null, messageId: null, rewriteOf: null }
  emit({ ...state, turns: stale ? state.turns.map(t => (t.id === id ? fresh : t)) : [...state.turns, fresh], selected: id })
  controller = new AbortController()
  await follow(id, run.started_at * 1000, attachRun(run.run_id, controller.signal), () => typeof document !== 'undefined' && document.hidden)
}
if (!DEMO && typeof window !== 'undefined') void resume()

/** 研究跑完时人不在这个页面：改标题、发一条系统通知（用户同意过的话），回来一眼就知道好了。 */
function announce(turn: Turn) {
  const ok = turn.status === 'passed' || turn.status === 'partial'
  const original = document.title
  document.title = `${ok ? '✓ 研究好了' : '研究没有完成'} · ${original.replace(/^[✓✗].*? · /, '')}`
  const restore = () => { if (!document.hidden) { document.title = original; document.removeEventListener('visibilitychange', restore) } }
  document.addEventListener('visibilitychange', restore)
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      const note = new Notification(ok ? '研究好了' : '研究没有完成', { body: turn.summary?.conclusion || turn.question, tag: `wp-research-${turn.id}` })
      note.onclick = () => { window.focus(); note.close() }
    }
  } catch { /* 浏览器不支持或被禁用：标题已经改了，够用 */ }
}

/** 第一次发起较长的研究时问一次要不要通知。只问一次；拒绝了就不再提。 */
export function askNotifyPermission() {
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') void Notification.requestPermission()
  } catch { /* 忽略 */ }
}

export function useResearch(): State {
  return useSyncExternalStore(cb => { listeners.add(cb); return () => listeners.delete(cb) }, () => state)
}
