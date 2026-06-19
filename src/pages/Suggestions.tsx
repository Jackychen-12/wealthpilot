import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { analysisApi } from '../api/analysis'
import { suggestions as mockSuggestions, watchSignals } from '../data/mock'
import { useAppNavigate } from '../hooks/useAppNavigate'

const priorityColor = { high: colors.danger, medium: colors.warning, low: colors.primary }
const priorityBg = { high: colors.dangerLight, medium: colors.warningLight, low: colors.primaryLight }

export function Suggestions() {
  const go = useAppNavigate()
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analysisApi.suggestions().then(data => {
      setSuggestions(Array.isArray(data) && data.length > 0 ? data : mockSuggestions.map(s => ({
        title: s.title, desc: s.desc, priority: 'medium', action: s.action,
      })))
      setLoading(false)
    })
  }, [])

  return (
    <div className="screen page-accent-purple">
      <Notch />
      <NavBar title="后续关注建议" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title">基于持仓分析的建议</div>
          {loading ? (
            <div style={{ padding: 20, textAlign: 'center', color: colors.textMuted }}>正在生成建议...</div>
          ) : (
            suggestions.map((s, i) => (
              <div
                key={i}
                className="suggest-item"
                onClick={s.action === 'chat' ? () => go('chat') : undefined}
              >
                <div
                  className="suggest-icon"
                  style={{
                    background: priorityBg[s.priority as keyof typeof priorityBg] || colors.primaryLight,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 14,
                  }}
                >
                  {s.priority === 'high' ? '⚠️' : s.priority === 'medium' ? '👀' : '💡'}
                </div>
                <div className="suggest-body">
                  <div className="suggest-title" style={{
                    color: s.priority === 'high' ? colors.danger : colors.text,
                  }}>
                    {s.title}
                  </div>
                  <div className="suggest-desc">{s.desc}</div>
                </div>
                <span style={{ color: '#C9CDD4', fontSize: 20 }}>&rsaquo;</span>
              </div>
            ))
          )}
        </div>

        <div className="card">
          <div className="card-title">近期值得关注的信号</div>
          {watchSignals.map((signal, i) => (
            <div key={i} style={{ padding: '10px 0', borderBottom: i < watchSignals.length - 1 ? '1px solid #F5F6F7' : 'none' }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: colors.text, marginBottom: 3 }}>{signal.title}</div>
              <div style={{ fontSize: 12, color: colors.textMuted }}>{signal.desc}</div>
            </div>
          ))}
        </div>
        <Disclaimer />
      </div>
    </div>
  )
}
