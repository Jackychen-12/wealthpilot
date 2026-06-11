import { useState } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { colors } from '../utils/theme'
import type { PageProps } from '../types'

const questions = [
  {
    q: '您的投资经验有多久？',
    opts: ['不到1年', '1-3年', '3-5年', '5年以上'],
    scores: [1, 2, 3, 4],
  },
  {
    q: '如果持仓一周内下跌10%，您会？',
    opts: ['立即全部卖出', '卖出一部分', '继续观察', '逢低加仓'],
    scores: [1, 2, 3, 4],
  },
  {
    q: '您期望的年化收益目标是？',
    opts: ['3-5%（跑赢通胀）', '5-10%（稳健增长）', '10-20%（积极增长）', '20%以上（高风险高回报）'],
    scores: [1, 2, 3, 4],
  },
  {
    q: '您能接受的最大亏损比例是？',
    opts: ['不能亏损', '5%以内', '10-20%', '20%以上都能接受'],
    scores: [1, 2, 3, 4],
  },
  {
    q: '您的资金计划投资多长时间？',
    opts: ['随时可能要用', '1年以内', '1-3年', '3年以上'],
    scores: [1, 2, 3, 4],
  },
]

const profiles = [
  { min: 5, max: 8, type: '保守型', color: colors.success, bg: '#ECFDF5', desc: '追求本金安全，建议以债券基金和货币基金为主（80%+），少量配置权益', emoji: '🛡️' },
  { min: 9, max: 12, type: '稳健型', color: colors.primary, bg: '#EFF6FF', desc: '追求稳定增长，建议债券40-60% + 权益40-60%的均衡配置', emoji: '⚖️' },
  { min: 13, max: 16, type: '积极型', color: colors.warning, bg: '#FFF7ED', desc: '追求较高回报，可承受波动。建议权益60-80% + 债券20-40%', emoji: '📈' },
  { min: 17, max: 20, type: '激进型', color: colors.danger, bg: '#FEF2F2', desc: '追求最大回报，能承受大幅波动。可高配权益80%+，行业集中投资', emoji: '🚀' },
]

function ScoreRing({ score, max, color }: { score: number; max: number; color: string }) {
  const r = 42
  const circumference = 2 * Math.PI * r
  const pct = score / max
  const offset = circumference * (1 - pct)
  return (
    <div className="score-ring">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#F0F1F3" strokeWidth="6" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" style={{ transition: 'stroke-dashoffset 0.8s ease-out' }} />
      </svg>
      <div className="score-ring-label">
        <div style={{ fontSize: 24, fontWeight: 700, color, fontFamily: 'DM Sans' }}>{score}</div>
        <div style={{ fontSize: 11, color: colors.textMuted }}>/ {max}</div>
      </div>
    </div>
  )
}

export function RiskProfile({ go }: PageProps) {
  const [answers, setAnswers] = useState<number[]>(Array(questions.length).fill(-1))
  const [submitted, setSubmitted] = useState(false)

  const totalScore = answers.reduce((s, a, i) => s + (a >= 0 ? questions[i].scores[a] : 0), 0)
  const answeredCount = answers.filter(a => a >= 0).length
  const allAnswered = answers.every(a => a >= 0)
  const profile = profiles.find(p => totalScore >= p.min && totalScore <= p.max) || profiles[0]

  return (
    <div className="screen page-accent-amber">
      <Notch />
      <NavBar title="风险偏好评估" onBack={() => go('home')} />
      <div className="content">
        {!submitted ? (
          <>
            <div className="progress-bar">
              <div className="progress-fill" style={{
                width: `${(answeredCount / questions.length) * 100}%`,
                background: answeredCount === questions.length
                  ? colors.success
                  : `linear-gradient(90deg, #2563EB, #3B82F6)`,
              }} />
            </div>

            <div style={{ fontSize: 12, color: colors.textMuted, textAlign: 'right', marginBottom: 12, marginTop: -8 }}>
              已完成 {answeredCount}/{questions.length}
            </div>

            {questions.map((q, qi) => (
              <div key={qi} className="card" style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.text, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 22, height: 22, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, fontWeight: 700, color: answers[qi] >= 0 ? '#fff' : colors.textMuted,
                    background: answers[qi] >= 0 ? colors.primary : '#F0F1F3',
                    transition: 'all 0.2s',
                  }}>
                    {answers[qi] >= 0 ? '✓' : qi + 1}
                  </span>
                  {q.q}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {q.opts.map((opt, oi) => {
                    const selected = answers[qi] === oi
                    return (
                      <div
                        key={oi}
                        onClick={() => { const n = [...answers]; n[qi] = oi; setAnswers(n) }}
                        style={{
                          padding: '10px 12px',
                          borderRadius: 8,
                          border: `1.5px solid ${selected ? colors.primary : colors.border}`,
                          background: selected ? colors.primaryLight : '#fff',
                          fontSize: 13,
                          color: selected ? colors.primary : colors.text,
                          fontWeight: selected ? 600 : 400,
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}
                      >
                        {selected && (
                          <span style={{ width: 4, height: 16, borderRadius: 2, background: colors.primary, flexShrink: 0 }} />
                        )}
                        {opt}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
            <div
              className={`form-btn ${allAnswered ? 'form-btn-primary' : ''}`}
              onClick={() => allAnswered && setSubmitted(true)}
              style={{
                background: allAnswered ? undefined : colors.border,
                color: allAnswered ? undefined : '#fff',
                cursor: allAnswered ? 'pointer' : 'not-allowed',
                margin: '16px 0',
                boxShadow: allAnswered ? undefined : 'none',
              }}
            >
              提交评估（{answeredCount}/{questions.length}）
            </div>
          </>
        ) : (
          <div className="card fade-in-up" style={{ textAlign: 'center', padding: '28px 20px' }}>
            <ScoreRing score={totalScore} max={20} color={profile.color} />
            <div style={{ fontSize: 14, marginBottom: 4 }}>{profile.emoji}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: profile.color }}>{profile.type}</div>
            <div style={{ fontSize: 13, color: colors.textMuted, margin: '6px 0 20px' }}>
              综合评分：{totalScore} / 20
            </div>
            <div style={{
              fontSize: 14, color: colors.text, lineHeight: 1.7, textAlign: 'left',
              background: profile.bg, borderRadius: 10, padding: 16,
              border: `1px solid ${profile.color}20`,
            }}>
              {profile.desc}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
              <div className="form-btn form-btn-outline" style={{ flex: 1 }} onClick={() => { setSubmitted(false); setAnswers(Array(questions.length).fill(-1)) }}>
                重新评估
              </div>
              <div className="form-btn form-btn-primary" style={{ flex: 1 }} onClick={() => go('suggest')}>
                查看配置建议 →
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
