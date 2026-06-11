import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { RadarChart } from '../components/RadarChart'
import { Tag } from '../components/Tag'
import { AiInsight } from '../components/AiInsight'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { analysisApi } from '../api/analysis'
import { healthDimensions as mockHealth } from '../data/mock'
import type { PageProps } from '../types'

const severityColor = { high: colors.danger, medium: colors.warning, low: colors.success }
const severityBg = { high: colors.dangerLight, medium: colors.warningLight, low: colors.successLight }

export function Health({ go }: PageProps) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analysisApi.health().then(d => {
      setData(d)
      setLoading(false)
    })
  }, [])

  const dimensions = data?.dimensions || mockHealth.map(d => ({
    ...d, score: d.severity === 'low' ? 80 : d.severity === 'medium' ? 55 : 30,
  }))
  const overall = data?.overall_score ?? Math.round(dimensions.reduce((s: number, d: any) => s + (d.score || 60), 0) / dimensions.length)
  const overallStatus = data?.overall_status ?? (overall >= 75 ? '优秀' : overall >= 60 ? '良好' : '需改善')

  const weakPoints = dimensions.filter((d: any) => d.severity !== 'low')

  return (
    <div className="screen page-accent-green">
      <Notch />
      <NavBar title="组合健康度" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>组合健康度雷达</span>
            <span style={{
              fontSize: 13,
              fontWeight: 700,
              color: overall >= 70 ? colors.success : overall >= 50 ? colors.warning : colors.danger,
            }}>
              {loading ? '...' : `${overall}分 · ${overallStatus}`}
            </span>
          </div>
          <RadarChart scores={dimensions.map((d: any) => d.score ?? 60)} />
          {dimensions.map((d: any, i: number) => (
            <div key={i} className="risk-row">
              <div className="risk-dot" style={{ background: severityColor[d.severity as keyof typeof severityColor] || colors.success }} />
              <span className="risk-name">{d.name}</span>
              {d.score != null && (
                <span style={{ fontSize: 12, color: colors.textMuted, marginRight: 4 }}>{d.score}分</span>
              )}
              <Tag
                color={severityColor[d.severity as keyof typeof severityColor] || colors.success}
                bg={severityBg[d.severity as keyof typeof severityBg] || colors.successLight}
              >
                {d.status}
              </Tag>
            </div>
          ))}
          <AiInsight>
            {weakPoints.length > 0
              ? `组合主要短板：${weakPoints.map((d: any) => d.name).join('、')}。建议重点关注${weakPoints[0]?.name}维度，可通过调整持仓结构改善。`
              : '组合各维度表现均衡，整体状态健康。建议继续保持当前配置。'
            }
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
