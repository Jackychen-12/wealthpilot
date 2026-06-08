import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { MetricBox } from '../components/MetricBox'
import { Tag } from '../components/Tag'
import { Disclaimer } from '../components/Disclaimer'
import { colors } from '../utils/theme'
import { analysisApi } from '../api/analysis'
import { portfolioSummary, topContributors, topDetractors } from '../data/mock'
import type { PageProps } from '../types'

const B = colors.primary

export function Overview({ go }: PageProps) {
  const [overview, setOverview] = useState<any>(null)
  const [attribution, setAttribution] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [ov, attr] = await Promise.all([
        analysisApi.overview(),
        analysisApi.attribution('fund'),
      ])
      setOverview(ov)
      setAttribution(Array.isArray(attr) ? attr : [])
      setLoading(false)
    }
    load()
  }, [])

  const wr = overview?.weekly_return ?? portfolioSummary.weeklyReturn
  const wg = overview?.weekly_growth_pct != null
    ? `${overview.weekly_growth_pct >= 0 ? '+' : ''}${overview.weekly_growth_pct.toFixed(2)}%`
    : portfolioSummary.weeklyGrowth
  const ex = overview?.excess_return_pct != null
    ? `${overview.excess_return_pct >= 0 ? '+' : ''}${overview.excess_return_pct.toFixed(2)}%`
    : portfolioSummary.excessReturn
  const vol = overview?.volatility_status ?? portfolioSummary.volatility
  const desc = overview?.description ?? portfolioSummary.fullDescription
  const sharpe = overview?.sharpe_ratio

  const contributors = attribution.filter(a => a.positive).slice(0, 2)
  const detractors = attribution.filter(a => !a.positive).slice(0, 2)

  return (
    <div className="screen">
      <Notch />
      <NavBar title="AI 持仓复盘" onBack={() => go('home')} />
      <div className="content">
        <div className="card">
          <div className="card-title">
            {loading ? '加载中...' : '本周持仓总览'}
            {sharpe != null && (
              <span style={{ marginLeft: 'auto', fontSize: 12, color: colors.textMuted }}>
                Sharpe {sharpe.toFixed(2)}
              </span>
            )}
          </div>
          <div style={{ background: 'linear-gradient(135deg,#EFF6FF,#F8FAFF)', borderRadius: 10, padding: 14, marginBottom: 14, border: '1px solid #DBEAFE' }}>
            <div style={{ fontSize: 14, color: colors.text, lineHeight: 1.65 }}>{desc}</div>
          </div>
          <div className="metric-grid">
            <MetricBox value={typeof wr === 'number' ? `${wr >= 0 ? '+' : ''}${wr.toFixed(0)}` : wr} label="本周收益(元)" color={colors.danger} />
            <MetricBox value={wg} label="组合涨幅" color={colors.danger} />
            <MetricBox value={ex} label="超额收益" color={B} />
            <MetricBox value={vol} label="波动状态" color={B} />
          </div>

          {contributors.length > 0 && (
            <>
              <div style={{ fontSize: 13, color: colors.textSecondary, fontWeight: 600, marginBottom: 8 }}>收益贡献 TOP</div>
              {contributors.map((f, i) => (
                <div key={i} className="fund-row">
                  <Tag color={colors.danger} bg={colors.dangerLight}>贡献</Tag>
                  <span className="fund-name">{f.name}</span>
                  <span className="fund-val" style={{ color: colors.danger }}>{f.value}</span>
                </div>
              ))}
            </>
          )}
          {detractors.length > 0 && (
            <>
              <div style={{ fontSize: 13, color: colors.textSecondary, fontWeight: 600, margin: '12px 0 8px' }}>收益拖累 TOP</div>
              {detractors.map((f, i) => (
                <div key={i} className="fund-row">
                  <Tag color={colors.warning} bg={colors.warningLight}>拖累</Tag>
                  <span className="fund-name">{f.name}</span>
                  <span className="fund-val" style={{ color: colors.success }}>{f.value}</span>
                </div>
              ))}
            </>
          )}

          {!loading && attribution.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: colors.textMuted, fontSize: 13 }}>
              暂无归因数据，请先
              <span style={{ color: B, cursor: 'pointer' }} onClick={() => go('portfolio')}> 添加持仓</span>
            </div>
          )}
        </div>

        <div className="module-grid">
          {([
            ['收益归因分析', '查看收益来源拆解', 'attribution', B],
            ['回撤分析', '了解下跌原因和影响', 'drawdown', colors.danger],
            ['组合健康度', '5维度持仓体检', 'health', colors.success],
            ['后续关注建议', '下一步该关注什么', 'suggest', colors.warning],
          ] as const).map(([title, desc, key, color], i) => (
            <div key={i} className="module-card" onClick={() => go(key)}>
              <div className="module-title">{title}</div>
              <div className="module-desc">{desc}</div>
              <div className="module-link" style={{ color }}>查看详情 &rsaquo;</div>
            </div>
          ))}
        </div>

        {([
          ['weekly', 'AI 周复盘报告', '每周五收盘后自动生成', B],
          ['chat', '对话式追问', '针对复盘结果继续深入提问', colors.primaryLight],
          ['portfolio', '持仓管理', '添加、编辑你的基金持仓', colors.successLight],
        ] as const).map(([key, title, desc, bg], i) => (
          <div key={i} className="card card-click" onClick={() => go(key)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 40, height: 40, background: bg, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', color: i === 0 ? '#fff' : B, fontSize: 18, fontWeight: 700 }}>
                {i === 0 ? 'W' : i === 1 ? 'Q' : '💼'}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: colors.text }}>{title}</div>
                <div style={{ fontSize: 12, color: colors.textMuted }}>{desc}</div>
              </div>
              <span style={{ color: '#C9CDD4', fontSize: 20 }}>&rsaquo;</span>
            </div>
          </div>
        ))}
        <Disclaimer />
      </div>
    </div>
  )
}
