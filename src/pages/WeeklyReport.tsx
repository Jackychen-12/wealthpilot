import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { MetricBox } from '../components/MetricBox'
import { AiInsight } from '../components/AiInsight'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { portfolioSummary, weeklyKeyPoints, weeklyFocus } from '../data/mock'
import type { PageProps } from '../types'

export function WeeklyReport({ go }: PageProps) {
  return (
    <div className="screen">
      <Notch />
      <NavBar title="AI 周复盘报告" onBack={() => go('overview')} />
      <div className="content">
        <div className="weekly-head">
          <div style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>AI 周复盘报告</div>
          <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 2 }}>2025年3月17日 - 3月21日</div>
          <div style={{ fontSize: 12, color: colors.primary, marginTop: 6, fontWeight: 600 }}>
            已为您生成第12期周复盘
          </div>
        </div>

        <div className="card">
          <div className="card-title">本周收益变化</div>
          <div className="metric-grid">
            <MetricBox value={portfolioSummary.weeklyReturn} label="本周收益" color={colors.danger} />
            <MetricBox value={portfolioSummary.weeklyGrowth} label="涨幅" color={colors.danger} />
            <MetricBox value={portfolioSummary.excessReturn} label="超额" color={colors.primary} />
          </div>
          <AiInsight>
            本周A股先抑后扬，沪深300周涨0.75%。组合跑赢基准0.67个百分点，主要受益于半导体板块的超额贡献。
          </AiInsight>
        </div>

        <div className="card">
          <div className="card-title">关键归因点</div>
          {weeklyKeyPoints.map((point, i) => (
            <div
              key={i}
              style={{
                padding: '10px 0',
                borderBottom: i < weeklyKeyPoints.length - 1 ? '1px solid #F5F6F7' : 'none',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.text }}>{point.title}</div>
              <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>{point.desc}</div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">下周关注</div>
          {weeklyFocus.map((text, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '7px 0',
                fontSize: 13,
                color: colors.textSecondary,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: colors.primary,
                  flexShrink: 0,
                }}
              />
              {text}
            </div>
          ))}
        </div>

        <div className="action-row">
          <div className="action-btn" onClick={() => go('attribution')}>查看归因详情</div>
          <div className="action-btn" onClick={() => go('health')}>组合健康度</div>
        </div>

        <FollowUpBar placeholder="针对本周复盘继续追问..." />
        <Disclaimer />
      </div>
    </div>
  )
}
