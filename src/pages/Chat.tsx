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
import type { PageProps } from '../types'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Message {
  id: number
  role: 'user' | 'ai'
  content: string
  streaming?: boolean
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

export function Chat({ go }: PageProps) {
  const [messages, setMessages] = useState<Message[]>(() =>
    chatMessages.slice(0, 2).map((msg, i) => ({
      id: i,
      role: msg.role,
      content: msg.role === 'ai'
        ? '你好！我是 WealthPilot 多智能体 AI。我由 Router 智能分流到 3 个专业 Agent（市场/持仓/风险），配备 12 个实时工具，为你提供深度投资分析。试着问我任何问题吧！'
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

  useEffect(() => { scrollToBottom() }, [messages, streamingText, scrollToBottom])

  const handleSend = useCallback(async (text: string) => {
    if (streaming) return

    const userMsg: Message = { id: nextId++, role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setFollowUps([])
    setStreaming(true)
    setStreamingText('')
    setActiveAgent('')
    setToolCalls([])
    setErrorMsg('')

    if (apiStatus === 'connected') {
      try {
        const history: ChatMsg[] = messages.map(m => ({ role: m.role, content: m.content }))
        let fullContent = ''

        for await (const event of streamChat(text, history, conversationId)) {
          if (event.type === 'agent_route') {
            setActiveAgent(event.label || event.agent || '')
          } else if (event.type === 'delta') {
            fullContent += event.content
            setStreamingText(fullContent)
          } else if (event.type === 'done') {
            fullContent = event.content
            setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: fullContent }])
            setStreamingText('')
            if (event.follow_ups) {
              setFollowUps(event.follow_ups)
            }
          } else if (event.type === 'tool_call') {
            setToolCalls(prev => [...prev, event.tool || ''])
          } else if (event.type === 'error') {
            setApiStatus('disconnected')
            setErrorMsg(`AI 服务返回错误: ${event.content}`)
            const response = findMockResponse(text)
            setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: response.text }])
            setStreamingText('')
            setFollowUps(response.followUps)
          }
        }
      } catch (e) {
        setApiStatus('disconnected')
        setErrorMsg(`连接失败: ${e instanceof Error ? e.message : '网络错误'}，已切换到演示模式`)
        const response = findMockResponse(text)
        setMessages(prev => [...prev, { id: nextId++, role: 'ai', content: response.text }])
        setStreamingText('')
        setFollowUps(response.followUps)
      }
    } else {
      const response = findMockResponse(text)
      setTimeout(() => {
        const aiMsg: Message = { id: nextId++, role: 'ai', content: response.text, streaming: true }
        setMessages(prev => [...prev, aiMsg])
        setTimeout(() => {
          setFollowUps(response.followUps)
          setMessages(prev => prev.map(m => m.streaming ? { ...m, streaming: false } : m))
        }, response.text.length * 20 + 200)
      }, 600)
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
    <div className="screen">
      <Notch />
      <NavBar title="Pilot AI · 多智能体对话" onBack={() => go('overview')} />
      <div className="content" ref={scrollRef} style={{ paddingBottom: 8, display: 'flex', flexDirection: 'column' }}>
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
            <AiBubble key={msg.id}>
              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
            </AiBubble>
          )
        })}

        {streaming && streamingText && (
          <div className="chat-ai">
            <div className="chat-avatar">AI</div>
            <div className="chat-bubble-ai" style={{ whiteSpace: 'pre-wrap' }}>
              {activeAgent && (
                <div className="agent-badge">{activeAgent}</div>
              )}
              {toolCalls.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                  {toolCalls.map((tool, i) => (
                    <span key={i} className="tool-chip">🔧 {tool}</span>
                  ))}
                </div>
              )}
              {streamingText}
              <span className="typing-cursor" />
            </div>
          </div>
        )}

        {streaming && !streamingText && (
          <div className="chat-ai">
            <div className="chat-avatar">AI</div>
            <div className="chat-bubble-ai">
              {activeAgent && (
                <div className="agent-badge">{activeAgent}</div>
              )}
              {toolCalls.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                  {toolCalls.map((tool, i) => (
                    <span key={i} className="tool-chip">🔧 {tool}</span>
                  ))}
                </div>
              )}
              <span className="typing-dots"><span /><span /><span /></span>
            </div>
          </div>
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
