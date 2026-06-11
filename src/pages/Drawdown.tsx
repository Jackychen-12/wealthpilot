import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { Tag } from '../components/Tag'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { analysisApi } from '../api/analysis'
import { drawdownFunds } from '../data/mock'
import type { PageProps } from '../types'

const severityColor = { high: colors.danger, medium: colors.warning, low: colors.success }
const severityBg = { high: colors.dangerLight, medium: colors.warningLight, low: colors.successLight }

export function Drawdown({ go }: PageProps) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analysisApi.drawdown().then(d => {
      setData(d)
      setLoading(false)
    })
  }, [])

  const funds = data?.funds || (Array.isArray(data) ? data : drawdownFunds)
  const summary = data?.summary || { avg_drawdown_pct: -3.2, avg_recovery_days: 18, high_risk_count: 1 }

  return (
    <div className="screen">
      <Notch />
      <NavBar title="回撤分析" onBack={() => go('overview')} />
      <div className="content">
        <div className="alert-box">
          <div className="alert-title">&#9888; 回撤分析</div>
          <div className="alert-text">
            {loading ? '正在分析持仓回撤...' :
              `组合平均回撤 ${summary.avg_drawdown_pct?.toFixed(1) || '--'}%，` +
              `${summary.high_risk_count || 0} 只基金处于高风险状态。`
            }
          </div>
        </div>

        <div className="card">
          <div className="card-title">三层归因分析</div>

          <div className="layer" style={{ borderLeftColor: colors.primary }}>
            <div className="layer-num" style={{ color: colors.primary }}>Layer 1 · 宏观归因</div>
            <div className="layer-title">市场环境</div>
            <div className="layer-text">
              当前市场处于{summary.high_risk_count > 1 ? '调整' : '震荡'}阶段，需关注宏观政策面变化对组合的影响。
            </div>
          </div>

          <div className="layer" style={{ borderLeftColor: colors.warning }}>
            <div className="layer-num" style={{ color: colors.warning }}>Layer 2 · 持仓影响</div>
            <div className="layer-title">各基金回撤情况</div>
            <div className="layer-text">
              持有的基金中 {funds.filter((f: any) => f.severity === 'high').length} 只处于较大回撤：
            </div>
            <div style={{ marginTop: 10 }}>
              {funds.map((f: any, i: number) => (
                <div key={i} className="risk-row">
                  <div className="risk-dot" style={{ background: severityColor[f.severity as keyof typeof severityColor] }} />
                  <span className="risk-name">{f.name}</span>
                  <span style={{ fontWeight: 600, color: severityColor[f.severity as keyof typeof severityColor], fontFamily: 'DM Sans' }}>
                    {f.value}
                  </span>
                  {f.recovery_days > 0 && (
                    <span style={{ fontSize: 11, color: colors.textMuted, marginLeft: 4 }}>
                      ({f.recovered ? `${f.recovery_days}日恢复` : `已${f.recovery_days}日未恢复`})
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="layer" style={{ borderLeftColor: colors.success }}>
            <div className="layer-num" style={{ color: colors.success }}>Layer 3 · 历史参照</div>
            <div className="layer-title">统计数据</div>
            <div className="hist-grid">
              <div className="hist-item">
                <div className="hist-num">{summary.avg_recovery_days || '--'}</div>
                <div className="hist-label">平均恢复天数</div>
              </div>
              <div className="hist-item">
                <div className="hist-num">{summary.avg_drawdown_pct ? `${summary.avg_drawdown_pct.toFixed(1)}%` : '--'}</div>
                <div className="hist-label">平均最大跌幅</div>
              </div>
              <div className="hist-item">
                <div className="hist-num">{funds.filter((f: any) => f.recovered).length}/{funds.length}</div>
                <div className="hist-label">已恢复比例</div>
              </div>
            </div>
          </div>
        </div>

        <div className="action-row">
          <div className="action-btn" onClick={() => go('suggest')}>查看建议</div>
          <div className="action-btn" onClick={() => go('health')}>健康度</div>
          <div className="action-btn" onClick={() => go('chat')}>Ask Pilot AI</div>
        </div>

        <FollowUpBar placeholder="这次回撤正常吗？继续追问..." onClick={() => go('chat')} />
        <Disclaimer />
      </div>
    </div>
  )
}
