import { useState, useRef, useEffect, useCallback } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { AiBubble, UserBubble } from '../components/ChatBubble'
import { StreamingBubble } from '../components/StreamingBubble'
import { ChatInput } from '../components/ChatInput'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { chatMessages, aiResponses, defaultResponse } from '../data/mock'
import type { PageProps } from '../types'

interface Message {
  id: number
  role: 'user' | 'ai'
  content: string
  streaming?: boolean
}

let nextId = 100

function findResponse(query: string) {
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
    chatMessages.map((msg, i) => ({
      id: i,
      role: msg.role,
      content:
        msg.content === 'analysis'
          ? '这个问题涉及投资决策，我无法直接给出买卖建议。但可以提供几个观察角度供您参考：\n\n1. 基金本身：该基金经理管理经验5年+，历史回撤控制中等偏上，当前跑输更多来自行业因素而非基金管理问题。\n\n2. 行业趋势：集采政策对仿制药影响较大，但创新药赛道政策面偏暖。可关注该基金创新药持仓占比。\n\n3. 您的组合：医疗仓位占总持仓12%，属于中等配置，不构成集中度风险。'
          : msg.content === 'table'
            ? `${msg.intro}\n\n• 创新药及CXO — 38.2%（高亮）\n• 仿制药及原料药 — 22.5%\n• 医疗器械 — 18.7%\n• 医疗服务及其他 — 20.6%\n\n创新药占比38.2%，同类中等偏上。相比上季度提升3.1个百分点，基金经理正在主动调整方向。`
            : msg.content,
    }))
  )
  const [followUps, setFollowUps] = useState<string[]>([
    '这只基金同类排名如何？',
    '和其他医疗基金对比',
    '半导体基金还能追吗？',
  ])
  const [streaming, setStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const container = scrollRef.current.closest('.phone-inner')
      if (container) {
        setTimeout(() => {
          container.scrollTop = container.scrollHeight
        }, 50)
      }
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleSend = useCallback(
    (text: string) => {
      if (streaming) return

      const userMsg: Message = { id: nextId++, role: 'user', content: text }
      const response = findResponse(text)

      setMessages((prev) => [...prev, userMsg])
      setFollowUps([])
      setStreaming(true)

      setTimeout(() => {
        const aiMsg: Message = {
          id: nextId++,
          role: 'ai',
          content: response.text,
          streaming: true,
        }
        setMessages((prev) => [...prev, aiMsg])
      }, 600)

      setTimeout(() => {
        setFollowUps(response.followUps)
      }, 600 + response.text.length * 20 + 300)

      setTimeout(() => {
        setStreaming(false)
        setMessages((prev) =>
          prev.map((m) => (m.streaming ? { ...m, streaming: false } : m))
        )
      }, 600 + response.text.length * 20 + 200)
    },
    [streaming]
  )

  return (
    <div className="screen">
      <Notch />
      <NavBar title="Pilot AI · 持仓追问" onBack={() => go('overview')} />
      <div className="content" ref={scrollRef}>
        <div
          style={{
            textAlign: 'center',
            fontSize: 12,
            color: colors.textMuted,
            margin: '8px 0 18px',
          }}
        >
          基于您的持仓复盘结果，可以继续追问
        </div>

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

        {streaming && messages[messages.length - 1]?.role === 'user' && (
          <div className="chat-ai">
            <div className="chat-avatar">AI</div>
            <div className="chat-bubble-ai">
              <span className="typing-dots">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}

        {followUps.length > 0 && !streaming && (
          <div className="quick-pills fade-in-up">
            {followUps.map((q, i) => (
              <div key={i} className="quick-pill" onClick={() => handleSend(q)}>
                {q}
              </div>
            ))}
          </div>
        )}

        <Disclaimer />
      </div>

      <div className="chat-bottom">
        <ChatInput
          onSend={handleSend}
          disabled={streaming}
          placeholder={streaming ? 'Pilot AI 正在思考...' : '输入您的问题...'}
        />
      </div>
    </div>
  )
}
