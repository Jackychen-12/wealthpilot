import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { RadarChart } from '../components/RadarChart'
import { Tag } from '../components/Tag'
import { AiInsight } from '../components/AiInsight'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { healthDimensions } from '../data/mock'
import type { PageProps } from '../types'

const severityColor = {
  high: colors.danger,
  medium: colors.warning,
  low: colors.success,
}
const severityBg = {
  high: colors.dangerLight,
  medium: colors.warningLight,
  low: colors.successLight,
}

export function Health({ go }: PageProps) {
  return (
    <div className="screen">
      <Notch />
      <NavBar title="组合健康度" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title">组合健康度雷达</div>
          <RadarChart />
          {healthDimensions.map((d, i) => (
            <div key={i} className="risk-row">
              <div className="risk-dot" style={{ background: severityColor[d.severity] }} />
              <span className="risk-name">{d.name}</span>
              <Tag color={severityColor[d.severity]} bg={severityBg[d.severity]}>{d.status}</Tag>
              <span style={{ color: '#C9CDD4', fontSize: 16 }}>&rsaquo;</span>
            </div>
          ))}
          <AiInsight>
            组合收益和波动表现良好，但持仓分散度偏低（前2只权益基金重仓股重叠度达68%），且实际风格偏离稳健型偏好。建议关注持仓结构。
          </AiInsight>
        </div>
        <div className="action-row">
          <div className="action-btn" onClick={() => go('suggest')}>查看关注建议</div>
          <div className="action-btn" onClick={() => go('chat')}>深入分析</div>
        </div>
        <Disclaimer />
      </div>
    </div>
  )
}
