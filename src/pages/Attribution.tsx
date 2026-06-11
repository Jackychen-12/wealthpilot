import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { BarChart } from '../components/BarChart'
import { AiInsight } from '../components/AiInsight'
import { FollowUpBar } from '../components/FollowUpBar'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { analysisApi } from '../api/analysis'
import { attributionByFund, attributionByIndustry, attributionByAsset } from '../data/mock'
import type { PageProps } from '../types'

const tabs = ['按基金', '按行业', '按资产类型']
const apiParams: ('fund' | 'industry' | 'category')[] = ['fund', 'industry', 'category']
const mockFallbacks = [attributionByFund, attributionByIndustry, attributionByAsset]

export function Attribution({ go }: PageProps) {
  const [tab, setTab] = useState(0)
  const [data, setData] = useState<Record<number, any[]>>({})
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    async function load() {
      if (data[tab]) return
      setLoading(true)
      const result = await analysisApi.attribution(apiParams[tab])
      setData(prev => ({ ...prev, [tab]: Array.isArray(result) && result.length > 0 ? result : mockFallbacks[tab] }))
      setLoading(false)
    }
    load()
  }, [tab])

  const current = data[tab] || mockFallbacks[tab]
  const topPositive = current.find(d => d.positive)
  const topNegative = current.find(d => !d.positive)

  return (
    <div className="screen page-accent-blue">
      <Notch />
      <NavBar title="收益归因分析" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title">收益归因分析</div>
          <div className="tab-bar">
            {tabs.map((t, i) => (
              <div key={i} className={`tab ${tab === i ? 'on' : ''}`} onClick={() => setTab(i)}>
                {t}
              </div>
            ))}
          </div>
          {loading ? (
            <div style={{ padding: 20, textAlign: 'center', color: colors.textMuted }}>加载中...</div>
          ) : (
            current.map((d, i) => (
              <BarChart key={`${tab}-${i}`} name={d.name} value={d.value} pct={d.pct} positive={d.positive} />
            ))
          )}
          <AiInsight>
            {topPositive && topNegative
              ? `收益主要由「${topPositive.name}」驱动（${topPositive.value}），「${topNegative.name}」拖累组合（${topNegative.value}）。`
              : topPositive
                ? `收益主要来自「${topPositive.name}」（${topPositive.value}）。`
                : '暂无归因数据，请先添加持仓。'
            }
          </AiInsight>
        </div>

        <div className="card">
          <div className="card-title">配置效应 vs 选择效应</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
            <div style={{ flex: 1, background: 'linear-gradient(135deg,#EFF6FF,#F8FAFF)', borderRadius: 10, padding: 14, textAlign: 'center', border: '1px solid #DBEAFE' }}>
              <div style={{ fontSize: 11, color: colors.textMuted }}>配置效应</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: colors.primary, marginTop: 2, fontFamily: 'DM Sans' }}>
                {current.length > 0 ? `+${(current.filter(d => d.positive).length / current.length * 1.5).toFixed(2)}%` : '--'}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>方向配置获益</div>
            </div>
            <div style={{ flex: 1, background: '#F7F8FA', borderRadius: 10, padding: 14, textAlign: 'center' }}>
              <div style={{ fontSize: 11, color: colors.textMuted }}>选择效应</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: colors.danger, marginTop: 2, fontFamily: 'DM Sans' }}>
                {topPositive ? `+${(topPositive.pct * 0.01).toFixed(2)}%` : '--'}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>选品超额</div>
            </div>
          </div>
        </div>
        <FollowUpBar placeholder="针对归因结果继续追问..." onClick={() => go('chat')} />
        <Disclaimer />
      </div>
    </div>
  )
}
