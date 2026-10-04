import { useEffect, useRef, useState } from 'react'
import { colors } from '../utils/theme'
import { Tag } from './Tag'

/** 一次研究的全过程：规划 → 各 Agent 取证 → 校验 → 结论状态。 */

export interface TraceEvidence {
  id: string
  tool: string
  agent: string
  ok: boolean
  input: string
  output: string
}

export interface TraceStep {
  kind: 'task' | 'critic' | 'replan' | 'synth' | 'error'
  text: string
  agent?: string
  passed?: boolean
}

export interface Trace {
  intent: string
  fallbackPlan: boolean
  tasks: { id: string; agent: string; goal: string; state: 'pending' | 'running' | 'done' | 'failed' }[]
  criteria: string[]
  evidence: TraceEvidence[]
  steps: TraceStep[]
  status: string
  seconds: number
  running: boolean
}

export const emptyTrace = (): Trace => ({
  intent: '', fallbackPlan: false, tasks: [], criteria: [], evidence: [], steps: [], status: '', seconds: 0, running: true,
})

const AGENTS: Record<string, { label: string; color: string; bg: string }> = {
  market: { label: '市场分析', color: colors.marketAccent, bg: colors.marketTint },
  portfolio: { label: '持仓分析', color: colors.portfolioAccent, bg: colors.portfolioTint },
  risk: { label: '风险评估', color: colors.riskAccent, bg: colors.riskTint },
  quant: { label: '量化验证', color: colors.aiAccent, bg: colors.aiTint },
}

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  passed: { label: '已通过校验', color: colors.success, bg: colors.successLight },
  partial: { label: '部分证据缺失', color: colors.warning, bg: colors.warningLight },
  rejected: { label: '未通过校验 · 未发布', color: colors.danger, bg: colors.dangerLight },
  insufficient_data: { label: '证据不足 · 未发布', color: colors.danger, bg: colors.dangerLight },
  failed: { label: '执行失败', color: colors.danger, bg: colors.dangerLight },
}

export const agentMeta = (agent: string) => AGENTS[agent] ?? { label: agent, color: colors.primary, bg: colors.primaryLight }

function phase(trace: Trace): string {
  if (!trace.tasks.length) return '正在规划任务'
  const last = trace.steps[trace.steps.length - 1]
  if (last?.kind === 'synth') return '正在撰写并校验回答'
  if (last?.kind === 'critic') return last.passed ? '校验通过，整理中' : '校验未通过，正在处理'
  if (last?.kind === 'replan') return '正在补充证据'
  return '正在取证'
}

export function ResearchTrace({ trace, focusId }: { trace: Trace; focusId?: string }) {
  const [open, setOpen] = useState(trace.running)
  const [expanded, setExpanded] = useState<string>('')
  const focusRef = useRef<HTMLDivElement>(null)

  // 运行中展开；结束后收起成一行摘要，不挡回答
  useEffect(() => { setOpen(trace.running) }, [trace.running])
  // 点了回答里的证据标签：展开并定位到那条证据
  useEffect(() => {
    if (!focusId) return
    setOpen(true)
    setExpanded(focusId)
    setTimeout(() => focusRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60)
  }, [focusId])

  const status = STATUS[trace.status]
  const rejected = trace.steps.filter(s => s.kind === 'critic' && s.passed === false).length

  return (
    <div className="trace">
      <div className="trace-head" onClick={() => setOpen(o => !o)} role="button" aria-expanded={open}>
        <span className={`trace-caret${open ? ' open' : ''}`}>›</span>
        <span className="trace-title">
          {trace.running ? <><span className="trace-live" />{phase(trace)}</> : '研究过程'}
        </span>
        <span className="trace-summary">
          {trace.tasks.length > 0 && `${trace.tasks.length} 个任务 · `}{trace.evidence.length} 条证据{trace.seconds > 0 && ` · ${trace.seconds.toFixed(0)} 秒`}
        </span>
        {status && <Tag color={status.color} bg={status.bg}>{status.label}</Tag>}
      </div>

      {open && (
        <div className="trace-body">
          {trace.tasks.length > 0 && (
            <div className="trace-section">
              <div className="trace-label">任务规划{trace.intent && ` · ${trace.intent}`}{trace.fallbackPlan && ' · 关键词兜底'}</div>
              {trace.tasks.map(task => {
                const meta = agentMeta(task.agent)
                const mine = trace.evidence.filter(e => e.agent === task.agent)
                return (
                  <div key={task.id} className="trace-task" style={{ borderLeftColor: meta.color }}>
                    <div className="trace-task-head">
                      <Tag color={meta.color} bg={meta.bg}>{meta.label}</Tag>
                      <span className={`trace-state ${task.state}`}>
                        {{ pending: '等待', running: '进行中', done: '完成', failed: '失败' }[task.state]}
                      </span>
                    </div>
                    <div className="trace-goal">{task.goal}</div>
                    {mine.length > 0 && (
                      <div className="trace-tools">
                        {mine.map(e => (
                          <div key={e.id} ref={e.id === focusId ? focusRef : undefined}>
                            <button
                              type="button"
                              className={`evidence-chip${e.ok ? '' : ' empty'}${expanded === e.id ? ' active' : ''}`}
                              onClick={() => setExpanded(x => (x === e.id ? '' : e.id))}
                            >
                              {e.tool}<span className="evidence-id">{e.id.slice(2, 6)}</span>
                            </button>
                            {expanded === e.id && (
                              <div className="evidence-detail">
                                <div className="evidence-meta">入参 {e.input} · {e.ok ? '取到数据' : '未取到数据'}</div>
                                <pre>{e.output}</pre>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {trace.steps.filter(s => s.kind !== 'task').length > 0 && (
            <div className="trace-section">
              <div className="trace-label">校验{rejected > 0 && ` · 打回 ${rejected} 次`}</div>
              {trace.steps.filter(s => s.kind !== 'task').map((s, i) => (
                <div key={i} className={`trace-step ${s.kind}${s.passed === false ? ' bad' : ''}${s.passed ? ' ok' : ''}`}>
                  <span className="trace-dot" />
                  <span>{s.text}</span>
                </div>
              ))}
            </div>
          )}

          {trace.criteria.length > 0 && (
            <div className="trace-section">
              <div className="trace-label">本轮必须取得的证据</div>
              {trace.criteria.map((c, i) => <div key={i} className="trace-criterion">{c}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
