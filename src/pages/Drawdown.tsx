import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { Tag } from '../components/Tag'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { drawdownFunds, historicalDrawdown, riskPoints } from '../data/mock'
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

export function Drawdown({ go }: PageProps) {
  return (
    <div className="screen">
      <Notch />
      <NavBar title="回撤分析" onBack={() => go('overview')} />
      <div className="content">
        <div className="alert-box">
          <div className="alert-title">&#9888; 本次回撤提醒</div>
          <div className="alert-text">
            组合近5个交易日累计回撤 <b>-3.2%</b>，超过风险偏好阈值。以下是 Pilot AI 为您生成的回撤分析。
          </div>
        </div>

        <div className="card">
          <div className="card-title">三层归因分析</div>

          <div className="layer" style={{ borderLeftColor: colors.primary }}>
            <div className="layer-num" style={{ color: colors.primary }}>Layer 1 · 宏观归因</div>
            <div className="layer-title">发生了什么</div>
            <div className="layer-text">
              央行意外释放流动性收紧信号，7天逆回购利率上调5BP，市场对加息预期升温，A股主要指数全线回调。
            </div>
          </div>

          <div className="layer" style={{ borderLeftColor: colors.warning }}>
            <div className="layer-num" style={{ color: colors.warning }}>Layer 2 · 持仓影响</div>
            <div className="layer-title">对您意味着什么</div>
            <div className="layer-text">
              持有的5只基金中3只权益基金受影响，拖累组合 -2.8%。其中半导体基金跌幅最大（-4.1%）。
            </div>
            <div style={{ marginTop: 10 }}>
              {drawdownFunds.map((f, i) => (
                <div key={i} className="risk-row">
                  <div className="risk-dot" style={{ background: severityColor[f.severity] }} />
                  <span className="risk-name">{f.name}</span>
                  <span style={{ fontWeight: 600, color: severityColor[f.severity], fontFamily: 'DM Sans' }}>
                    {f.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="layer" style={{ borderLeftColor: colors.success }}>
            <div className="layer-num" style={{ color: colors.success }}>Layer 3 · 历史参照</div>
            <div className="layer-title">历史上类似情况如何</div>
            <div className="layer-text">过去5次类似利率信号引发的回撤中：</div>
            <div className="hist-grid">
              {historicalDrawdown.map((h, i) => (
                <div key={i} className="hist-item">
                  <div className="hist-num">{h.value}</div>
                  <div className="hist-label">{h.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-title">当前风险点</div>
          {riskPoints.map((r, i) => (
            <div key={i} className="risk-row">
              <div className="risk-dot" style={{ background: severityColor[r.severity] }} />
              <span className="risk-name">{r.name}</span>
              <Tag color={severityColor[r.severity]} bg={severityBg[r.severity]}>{r.status}</Tag>
            </div>
          ))}
        </div>

        <div className="action-row">
          <div className="action-btn" onClick={() => go('suggest')}>了解利率周期</div>
          <div className="action-btn">对比同类基金</div>
          <div className="action-btn" onClick={() => go('chat')}>Ask Pilot AI</div>
        </div>

        <FollowUpBar placeholder="这次回撤正常吗？继续追问..." />
        <Disclaimer />
      </div>
    </div>
  )
}
