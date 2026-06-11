import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { MetricBox } from '../components/MetricBox'
import { AiInsight } from '../components/AiInsight'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { apiFetch } from '../api/client'
import { portfolioSummary, weeklyKeyPoints as mockKeyPoints, weeklyFocus as mockFocus } from '../data/mock'
import type { PageProps } from '../types'

export function WeeklyReport({ go }: PageProps) {
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiFetch('/api/report/weekly', null).then(data => {
      setReport(data)
      setLoading(false)
    })
  }, [])

  const overview = report?.overview || {}
  const wr = overview.weekly_return ?? portfolioSummary.weeklyReturn
  const wg = overview.weekly_growth_pct != null
    ? `${overview.weekly_growth_pct >= 0 ? '+' : ''}${overview.weekly_growth_pct.toFixed(2)}%`
    : portfolioSummary.weeklyGrowth
  const ex = overview.excess_return_pct != null
    ? `${overview.excess_return_pct >= 0 ? '+' : ''}${overview.excess_return_pct.toFixed(2)}%`
    : portfolioSummary.excessReturn

  const keyPoints = report?.key_points || mockKeyPoints
  const focus = report?.next_week_focus || mockFocus
  const insight = report?.ai_insight || '暂无 AI 洞察（需配置后端 API）'
  const weekRange = report?.week_start && report?.week_end
    ? `${report.week_start} — ${report.week_end}`
    : '本周'

  return (
    <div className="screen">
      <Notch />
      <NavBar title="AI 周复盘报告" onBack={() => go('overview')} />
      <div className="content">
        <div className="weekly-head">
          <div style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>AI 周复盘报告</div>
          <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>{weekRange}</div>
          <div style={{ fontSize: 12, color: colors.primary, marginTop: 6, fontWeight: 600 }}>
            {loading ? '正在生成...' : (report?.summary || '报告已生成')}
          </div>
        </div>

        <div className="card">
          <div className="card-title">本周收益变化</div>
          <div className="metric-grid">
            <MetricBox value={typeof wr === 'number' ? `${wr >= 0 ? '+' : ''}${wr.toFixed(0)}` : wr} label="本周收益" color={colors.danger} />
            <MetricBox value={wg} label="涨幅" color={colors.danger} />
            <MetricBox value={ex} label="超额" color={colors.primary} />
          </div>
          <AiInsight>{insight}</AiInsight>
        </div>

        <div className="card">
          <div className="card-title">关键归因点</div>
          {keyPoints.map((point: any, i: number) => (
            <div key={i} style={{ padding: '10px 0', borderBottom: i < keyPoints.length - 1 ? '1px solid #F5F6F7' : 'none' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{point.title}</div>
              <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{point.desc}</div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">下周关注</div>
          {focus.map((text: string, i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', fontSize: 13, color: colors.textSecondary }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: colors.primary, flexShrink: 0 }} />
              {text}
            </div>
          ))}
        </div>

        <div className="action-row">
          <div className="action-btn" onClick={() => go('attribution')}>查看归因详情</div>
          <div className="action-btn" onClick={() => go('health')}>组合健康度</div>
        </div>

        <FollowUpBar placeholder="针对本周复盘继续追问..." onClick={() => go('chat')} />
        <Disclaimer />
      </div>
    </div>
  )
}
