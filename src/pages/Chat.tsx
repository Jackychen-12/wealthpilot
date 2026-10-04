import { useState, useRef, useEffect, useCallback } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { AiBubble, UserBubble } from '../components/ChatBubble'
import { StreamingBubble } from '../components/StreamingBubble'
import { ChatInput } from '../components/ChatInput'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { streamChat, type ChatMsg } from '../api/chat'
import { chatMessages, aiResponses, defaultResponse } from '../data/mock'
import { useAppNavigate } from '../hooks/useAppNavigate'
import { Markdown } from '../components/Markdown'
import { ResearchTrace, agentMeta, emptyTrace, type Trace } from '../components/ResearchTrace'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Message {
  id: number
  role: 'user' | 'ai'
  content: string
  streaming?: boolean
  trace?: Trace
}

const clip = (v: unknown, max = 1200) => {
  const text = typeof v === 'string' ? v : JSON.stringify(v)
  return text.length > max ? `${text.slice(0, max)}…` : text
}

let nextId = 100

function findMockResponse(query: string) {
  const direct = aiResponses[query]
  if (direct) return direct
  for (const [key, val] of Object.entries(aiResponses)) {
    const keywords = key.replace(/[？?！!，。]/g, '').split('')
    const matchCount = keywords.filter((ch) => query.includes(ch)).length
    if (matchCount > key.length * 0.4) return val
  }
  return defaultResponse
}

export function Chat() {
  const go = useAppNavigate()
  const [messages, setMessages] = useState<Message[]>(() =>
    chatMessages.slice(0, 2).map((msg, i) => ({
      id: i,
      role: msg.role,
      content: msg.role === 'ai'
        ? '你好！我是 WealthPilot 多智能体 AI。每个问题我会先拆成任务，交给市场、持仓、风险、量化 4 个专业 Agent 并行取证，回答通过校验后才会发布——每个数字都能点开看到出处。'
        : msg.content,
    }))
  )
  const [followUps, setFollowUps] = useState<string[]>([
    '📊 查看最新市场动态',
    '💼 分析我的持仓收益',
    '🛡️ 评估持仓风险',
  ])
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [activeAgent, setActiveAgent] = useState('')
  const [toolCalls, setToolCalls] = useState<string[]>([])
  const [liveTrace, setLiveTrace] = useState<Trace | null>(null)
  const [focus, setFocus] = useState<{ msg: number; id: string } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking')
  const [errorMsg, setErrorMsg] = useState('')
  const [conversationId] = useState(() => crypto.randomUUID())

  useEffect(() => {
    const controller = new AbortController()
    const token = localStorage.getItem('wp_token')
    fetch(`${API_BASE}/health`, {
      signal: controller.signal,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => {
        if (r.ok) {
          setApiStatus('connected')
        } else {
          setApiStatus('disconnected')
          setErrorMsg(`后端返回 ${r.status}，请检查服务是否正常运行`)
        }
      })
      .catch(() => {
        setApiStatus('disconnected')
        setErrorMsg(`无法连接到 ${API_BASE}，请确认后端已启动（make backend）`)
      })
    return () => controller.abort()
  }, [])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const container = scrollRef.current.closest('.phone-inner')
      if (container) {
        setTimeout(() => { container.scrollTop = container.scrollHeight }, 50)
      }
    }
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, streamingText, liveTrace, scrollToBottom])

  const handleSend = useCallback(async (text: string) => {
    if (streaming) return

    const userMsg: Message = { id: nextId++, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setFollowUps([])
    setStreaming(true)
    setStreamingText('')
    setActiveAgent('')
    setToolCalls([])
    setLiveTrace(null)
    setErrorMsg('')

    if (apiStatus === 'connected') {
      try {
        const history: ChatMsg[] = messages.map(m => ({ role: m.role, content: m.content }))
        const started = Date.now()
        let trace = emptyTrace()
        let fullContent = ''
        let finished = false
        const update = (fn: (t: Trace) => Trace) => {
          trace = { ...fn(trace), seconds: (Date.now() - started) / 1000 }
          setLiveTrace(trace)
        }
        const setTask = (id: string | undefined, agent: string | undefined, goal: string | undefined, state: Trace['tasks'][number]['state']) =>
          update(t => {
            const known = t.tasks.some(x => x.id === id)
            const tasks = known
              ? t.tasks.map(x => (x.id === id ? { ...x, state } : x))
              : [...t.tasks, { id: id || String(t.tasks.length), agent: agent || '', goal: goal || '', state }]
            return { ...t, tasks }
          })
        setLiveTrace(trace)

        for await (const event of streamChat(text, history, conversationId)) {
          if (event.type === 'plan') {
            update(t => ({
              ...t,
              intent: event.intent || '',
              fallbackPlan: event.source === 'fallback',
              criteria: event.success_criteria || [],
              tasks: (event.tasks || []).map(x => ({ id: x.id, agent: x.agent, goal: x.goal, state: 'pending' as const })),
            }))
          } else if (event.type === 'task_start') {
            setTask(event.id, event.agent, event.goal, 'running')
          } else if (event.type === 'task_done') {
            setTask(event.id, event.agent, event.goal, event.status === 'completed' ? 'done' : 'failed')
          } else if (event.type === 'evidence' && event.evidence?.id) {
            const ev = event.evidence
            update(t => ({
              ...t,
              evidence: [...t.evidence, {
                id: ev.id || '', tool: ev.tool || '', agent: event.agent || '', ok: ev.status === 'ok',
                input: clip(ev.input ?? {}, 200), output: clip(ev.output ?? ''),
              }],
            }))
          } else if (event.type === 'critic') {
            const name = event.gate === 'evidence' ? '证据审核' : `回答校验 · 第 ${event.attempt ?? 1} 稿`
            const issues = (event.issues || []).join('；')
            update(t => ({
              ...t,
              steps: [...t.steps, { kind: 'critic', passed: event.passed, text: `${name}${event.passed ? '通过' : `打回：${issues}`}` }],
            }))
          } else if (event.type === 'replan') {
            update(t => ({ ...t, steps: [...t.steps, { kind: 'replan', text: `补充查证：${(event.tasks || []).map(x => x.goal.replace(/^补充查证：/, '')).join('；')}` }] }))
          } else if (event.type === 'synthesizing') {
            update(t => ({ ...t, steps: [...t.steps, { kind: 'synth', text: '整合各任务证据，撰写回答' }] }))
          } else if (event.type === 'error') {
            // Agent 级别的错误不等于整轮失败 —— 记进过程里，最终以 done 的状态为准
            update(t => ({ ...t, steps: [...t.steps, { kind: 'error', passed: false, text: event.content }] }))
          } else if (event.type === 'delta') {
            fullContent += event.content
            setStreamingText(fullContent)
          } else if (event.type === 'done') {
            finished = true
            fullContent = event.content
            update(t => ({ ...t, status: event.meta?.status || 'passed', running: false }))
            setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: fullContent, trace }])
            setStreamingText('')
            setLiveTrace(null)
            if (event.follow_ups) setFollowUps(event.follow_ups)
          }
        }
        if (!finished) throw new Error('连接中断，未收到完整回答')
      } catch (e) {
        setApiStatus('disconnected')
        setLiveTrace(null)
        setErrorMsg(`连接失败: ${e instanceof Error ? e.message : '网络错误'}，已切换到演示模式`)
        const response = findMockResponse(text)
        if (response.agent) setActiveAgent(response.agent)
        if (response.tools) setToolCalls(response.tools)
        setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: response.text }])
        setStreamingText('')
        setFollowUps(response.followUps)
      }
    } else {
      const response = findMockResponse(text)
      if (response.agent) setActiveAgent(response.agent)
      setTimeout(() => {
        if (response.tools) {
          response.tools.forEach((tool, i) => {
            setTimeout(() => setToolCalls(prev => [...prev, tool]), i * 400)
          })
        }
        const toolDelay = (response.tools?.length ?? 0) * 400 + 600
        setTimeout(() => {
          let charIndex = 0
          const interval = setInterval(() => {
            charIndex += Math.floor(Math.random() * 3) + 2
            if (charIndex >= response.text.length) {
              clearInterval(interval)
              setStreamingText('')
              setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: response.text }])
              setFollowUps(response.followUps)
              setStreaming(false)
              setActiveAgent('')
              setToolCalls([])
            } else {
              setStreamingText(response.text.slice(0, charIndex))
            }
          }, 25)
        }, toolDelay)
      }, 500)
      return
    }

    setStreaming(false)
  }, [streaming, messages, apiStatus, conversationId])

  const handleRetryConnect = useCallback(() => {
    setApiStatus('checking')
    setErrorMsg('')
    const t = localStorage.getItem('wp_token')
    fetch(`${API_BASE}/health`, {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    })
      .then(r => {
        setApiStatus(r.ok ? 'connected' : 'disconnected')
        if (!r.ok) setErrorMsg(`后端返回 ${r.status}`)
      })
      .catch(() => {
        setApiStatus('disconnected')
        setErrorMsg(`无法连接到 ${API_BASE}`)
      })
  }, [])

  const statusText = apiStatus === 'checking'
    ? '🔄 正在连接后端...'
    : apiStatus === 'connected'
      ? '🟢 已连接 AI Agent（多智能体模式）'
      : '🟡 演示模式（预设回答）'

  return (
    <div className="screen" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Notch />
      <NavBar title="Pilot AI · 多智能体对话" onBack={() => go('overview')} />
      <div className="content" ref={scrollRef} style={{ flex: 1, paddingBottom: 8, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ textAlign: 'center', fontSize: 12, color: colors.textMuted, margin: '8px 0 18px' }}>
          {statusText}
          {apiStatus === 'connected' && (
            <div style={{ fontSize: 10, color: colors.textMuted, opacity: 0.6, marginTop: 2 }}>
              会话 {conversationId.slice(0, 8)}
            </div>
          )}
          {apiStatus === 'disconnected' && (
            <div style={{ marginTop: 4 }}>
              <span
                onClick={handleRetryConnect}
                style={{ fontSize: 11, color: colors.primary, cursor: 'pointer', textDecoration: 'underline' }}
              >
                点击重试连接
              </span>
            </div>
          )}
        </div>

        {errorMsg && (
          <div style={{
            background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 8,
            padding: '8px 12px', margin: '0 0 12px', fontSize: 12, color: '#C2410C', lineHeight: 1.5,
          }}>
            {errorMsg}
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return <UserBubble key={msg.id}>{msg.content}</UserBubble>
          }
          if (msg.streaming) {
            return <StreamingBubble key={msg.id} text={msg.content} />
          }
          return (
            <AiBubble key={msg.id} wide={!!msg.trace}>
              {msg.trace && <ResearchTrace trace={msg.trace} focusId={focus?.msg === msg.id ? focus.id : undefined} />}
              <Markdown text={msg.content} onCite={id => setFocus({ msg: msg.id, id })} />
            </AiBubble>
          )
        })}

        {streaming && (liveTrace || streamingText) && (
          <AiBubble wide={!!liveTrace}>
            {liveTrace && <ResearchTrace trace={liveTrace} />}
            {streamingText && <Markdown text={streamingText} />}
            {streamingText && <span className="typing-cursor" />}
          </AiBubble>
        )}

        {streaming && !liveTrace && !streamingText && (
          <AiBubble>
            {activeAgent && <div className="agent-badge">{agentMeta(activeAgent).label}</div>}
            {toolCalls.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                {toolCalls.map((tool, i) => (
                  <span key={i} className="tool-chip">{tool}</span>
                ))}
              </div>
            )}
            <span className="typing-dots"><span /><span /><span /></span>
          </AiBubble>
        )}

        <div style={{ flex: 1 }} />

        {followUps.length > 0 && !streaming && (
          <div className="quick-pills fade-in-up">
            {followUps.map((q, i) => (
              <div key={i} className="quick-pill" onClick={() => handleSend(q)}>{q}</div>
            ))}
          </div>
        )}
      </div>

      <div className="chat-bottom">
        <ChatInput
          onSend={handleSend}
          disabled={streaming}
          placeholder={streaming ? 'Pilot AI 正在分析...' : '输入您的问题...'}
        />
        <Disclaimer />
      </div>
    </div>
  )
}
