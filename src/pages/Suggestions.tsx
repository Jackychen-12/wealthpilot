import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { suggestions, watchSignals } from '../data/mock'

const bgMap: Record<string, string> = {
  primaryLight: colors.primaryLight,
  warningLight: colors.warningLight,
  successLight: colors.successLight,
  accent: '#F0FEFF',
}

export function Suggestions({ go }: { go: (k: string) => void }) {
  return (
    <div className="screen">
      <Notch />
      <NavBar title="后续关注建议" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title">基于本次复盘的建议</div>
          {suggestions.map((s, i) => (
            <div
              key={i}
              className="suggest-item"
              onClick={s.action === 'chat' ? () => go('chat') : undefined}
            >
              <div className="suggest-icon" style={{ background: bgMap[s.bg] || s.bg }} />
              <div className="suggest-body">
                <div className="suggest-title">{s.title}</div>
                <div className="suggest-desc">{s.desc}</div>
              </div>
              {s.toggle ? (
                <div className="switch-track">
                  <div className="switch-thumb" />
                </div>
              ) : (
                <span style={{ color: '#C9CDD4', fontSize: 20 }}>&rsaquo;</span>
              )}
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">近期值得关注的信号</div>
          {watchSignals.map((signal, i) => (
            <div
              key={i}
              style={{
                padding: '10px 0',
                borderBottom: i < watchSignals.length - 1 ? '1px solid #F5F6F7' : 'none',
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 500, color: colors.text, marginBottom: 3 }}>
                {signal.title}
              </div>
              <div style={{ fontSize: 12, color: colors.textMuted }}>{signal.desc}</div>
            </div>
          ))}
        </div>
        <Disclaimer />
      </div>
    </div>
  )
}
