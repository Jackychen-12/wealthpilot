/**
 * 研究会话的状态放在模块级 store 里，而不是页面组件里 ——
 * 切到别的页面再回来，对话和正在跑的研究都还在。
 */
import { useSyncExternalStore } from 'react'
import { streamChat, type Checkpoint, type Debate, type Depth, type Proposal, type Security, type StreamEvent, type SummaryCard, type Usage } from '../api'

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
  /** 后端存下的消息 ID —— 之后“更短一点”这类改写靠它找到这次研究的证据 */
  messageId: number | null
  /** 这是基于哪一次回答改写的（界面上显示成“改写”而不是新的研究） */
  rewriteOf: number | null
}

interface State { turns: Turn[]; selected: number | null; focusEvidence: string }

let state: State = { turns: [], selected: null, focusEvidence: '' }
const listeners = new Set<() => void>()
let controller: AbortController | null = null
let nextId = 1
// 同一次会话里的问答共用一个 ID，后端据此把它们存进研究记录
let conversationId = crypto.randomUUID()

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
    case 'resolved': return { ...turn, securities: e.securities || [] }
    case 'checkpoints': return { ...turn, checkpoints: e.items || [], proposals: e.proposals || [] }
    case 'plan':
      return { ...turn, playbook: e.playbook || '', intent: e.intent || '', fallbackPlan: e.source === 'fallback', criteria: e.success_criteria || [], eta: e.eta_seconds || 0,
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
        summary: e.meta?.summary ?? null, messageId: e.meta?.message_id ?? null, playbook: turn.playbook || e.meta?.playbook || '' }
    default: return turn
  }
}

export const research = {
  select: (id: number) => emit({ ...state, selected: id, focusEvidence: '' }),
  focus: (turnId: number, evidenceId: string) => emit({ ...state, selected: turnId, focusEvidence: evidenceId }),
  stop: () => controller?.abort(),
  clear: () => { controller?.abort(); conversationId = crypto.randomUUID(); emit({ turns: [], selected: null, focusEvidence: '' }) },
  get busy() { return state.turns.some(t => t.running) },

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
      eta: 0, depth: options.depth ?? 'auto', summary: null, debate: null, messageId: null, rewriteOf: source?.messageId ? source.id : null }
    emit({ turns: [...state.turns, turn], selected: id, focusEvidence: '' })
    const wasHidden = () => typeof document !== 'undefined' && document.hidden

    const started = Date.now()
    const clock = setInterval(() => patch(id, t => ({ ...t, seconds: (Date.now() - started) / 1000 })), 500)
    controller = new AbortController()
    try {
      for await (const event of streamChat(turn.question, history, controller.signal, conversationId,
        { depth: turn.depth, rewriteOf: source?.messageId ?? null })) patch(id, t => apply(t, event))
      patch(id, t => (t.running ? { ...t, running: false, status: 'failed', error: '连接中断，没有收到完整回答' } : t))
      const finished = state.turns.find(t => t.id === id)
      if (finished && wasHidden()) announce(finished)
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === 'AbortError'
      patch(id, t => ({ ...t, running: false, status: aborted ? 'stopped' : 'failed', error: aborted ? '已停止' : err instanceof Error ? err.message : '请求失败' }))
    } finally {
      clearInterval(clock)
      controller = null
      patch(id, t => ({ ...t, seconds: (Date.now() - started) / 1000 }))
    }
  },
}

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
