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
  { min: 5, max: 8, type: '保守型', color: colors.success, desc: '追求本金安全，建议以债券基金和货币基金为主（80%+），少量配置权益', emoji: '🛡️' },
  { min: 9, max: 12, type: '稳健型', color: colors.primary, desc: '追求稳定增长，建议债券40-60% + 权益40-60%的均衡配置', emoji: '⚖️' },
  { min: 13, max: 16, type: '积极型', color: colors.warning, desc: '追求较高回报，可承受波动。建议权益60-80% + 债券20-40%', emoji: '📈' },
  { min: 17, max: 20, type: '激进型', color: colors.danger, desc: '追求最大回报，能承受大幅波动。可高配权益80%+，行业集中投资', emoji: '🚀' },
]

export function RiskProfile({ go }: PageProps) {
  const [answers, setAnswers] = useState<number[]>(Array(questions.length).fill(-1))
  const [submitted, setSubmitted] = useState(false)

  const totalScore = answers.reduce((s, a, i) => s + (a >= 0 ? questions[i].scores[a] : 0), 0)
  const allAnswered = answers.every(a => a >= 0)
  const profile = profiles.find(p => totalScore >= p.min && totalScore <= p.max) || profiles[0]

  return (
    <div className="screen">
      <Notch />
      <NavBar title="风险偏好评估" onBack={() => go('overview')} />
      <div className="content">
        {!submitted ? (
          <>
            {questions.map((q, qi) => (
              <div key={qi} className="card" style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.text, marginBottom: 10 }}>
                  {qi + 1}. {q.q}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {q.opts.map((opt, oi) => (
                    <div
                      key={oi}
                      onClick={() => { const n = [...answers]; n[qi] = oi; setAnswers(n) }}
                      style={{
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: `1.5px solid ${answers[qi] === oi ? colors.primary : colors.border}`,
                        background: answers[qi] === oi ? colors.primaryLight : '#fff',
                        fontSize: 13,
                        color: answers[qi] === oi ? colors.primary : colors.text,
                        fontWeight: answers[qi] === oi ? 600 : 400,
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                      }}
                    >
                      {opt}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div
              onClick={() => allAnswered && setSubmitted(true)}
              style={{
                padding: '12px 0', textAlign: 'center', borderRadius: 10,
                background: allAnswered ? colors.primary : colors.border,
                color: '#fff', fontSize: 15, fontWeight: 600, cursor: allAnswered ? 'pointer' : 'not-allowed',
                margin: '16px 0',
              }}
            >
              提交评估（{answers.filter(a => a >= 0).length}/{questions.length}）
            </div>
          </>
        ) : (
          <div className="card" style={{ textAlign: 'center', padding: '30px 20px' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>{profile.emoji}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: profile.color }}>{profile.type}</div>
            <div style={{ fontSize: 13, color: colors.textMuted, margin: '8px 0 20px' }}>
              综合评分：{totalScore} / 20
            </div>
            <div style={{ fontSize: 14, color: colors.text, lineHeight: 1.7, textAlign: 'left', background: '#F7F8FA', borderRadius: 10, padding: 16 }}>
              {profile.desc}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 24, justifyContent: 'center' }}>
              <div onClick={() => { setSubmitted(false); setAnswers(Array(questions.length).fill(-1)) }} style={{ padding: '10px 20px', borderRadius: 8, border: `1px solid ${colors.border}`, fontSize: 13, cursor: 'pointer', color: colors.text }}>
                重新评估
              </div>
              <div onClick={() => go('suggest')} style={{ padding: '10px 20px', borderRadius: 8, background: colors.primary, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                查看配置建议 →
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
