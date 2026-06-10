import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { Tag } from '../components/Tag'
import { MetricBox } from '../components/MetricBox'
import { colors } from '../utils/theme'
import { marketIndices as mockIndices, marketNews as mockNews, portfolioSummary } from '../data/mock'
import { marketApi } from '../api/market'
import { analysisApi } from '../api/analysis'
import type { PageProps } from '../types'

const B = colors.primary
const Bb = colors.primaryLight

export function Home({ go }: PageProps) {
  const [indices, setIndices] = useState(mockIndices)
  const [news, setNews] = useState(mockNews)
  const [overview, setOverview] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [idx, nws, ov] = await Promise.all([
        marketApi.indices(),
        marketApi.news(),
        analysisApi.overview(),
      ])
      setIndices(idx)
      setNews(nws)
      setOverview(ov)
      setLoading(false)
    }
    load()
  }, [])

  const weeklyReturn = overview?.weekly_return ?? portfolioSummary.weeklyReturn
  const weeklyGrowth = overview?.weekly_growth_pct
    ? `${overview.weekly_growth_pct >= 0 ? '+' : ''}${overview.weekly_growth_pct}%`
    : portfolioSummary.weeklyGrowth
  const volatility = overview?.volatility_status ?? portfolioSummary.volatility

  return (
    <div className="screen">
      <Notch />
      <div className="nav" style={{ justifyContent: 'space-between' }}>
        <span className="nav-back">&lsaquo;</span>
        <div
          style={{
            background: Bb,
            borderRadius: 22,
            padding: '5px 16px',
            fontSize: 13,
            color: B,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <rect x="3" y="8" width="3" height="10" rx="1.5" fill={B} />
            <rect x="8" y="4" width="3" height="14" rx="1.5" fill={B} opacity=".6" />
            <rect x="13" y="6" width="3" height="12" rx="1.5" fill={B} opacity=".8" />
            <rect x="18" y="3" width="3" height="15" rx="1.5" fill={B} opacity=".4" />
          </svg>
          Market Briefing &#9654;
        </div>
        <span style={{ fontSize: 22, color: colors.text }}>&equiv;</span>
      </div>
      <div className="content">
        <div className="card">
          <div className="card-title">
            行情追踪
            <span style={{ marginLeft: 'auto', color: B, fontSize: 20, cursor: 'pointer' }}>&#8635;</span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {indices.map((idx, i) => (
              <div key={i} style={{ flex: 1, background: '#F7F8FA', borderRadius: 10, padding: '10px 8px' }}>
                <div style={{ fontSize: 12, color: colors.textMuted }}>{idx.name}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: idx.up ? colors.success : colors.danger, fontFamily: 'DM Sans', letterSpacing: '-0.5px' }}>
                  {idx.value}
                </div>
                <div style={{ fontSize: 12, color: idx.up ? colors.success : colors.danger, fontWeight: 500 }}>
                  {idx.change}
                </div>
              </div>
            ))}
          </div>
          {news.map((item, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', fontSize: 14, color: colors.textSecondary }}>
              <Tag color={colors.primary} bg={colors.primaryLight}>{item.tag}</Tag>
              <span style={{ flex: 1 }}>{item.text}</span>
            </div>
          ))}
          <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 10 }}>
            WealthPilot AI Engine · {loading ? '加载中...' : '实时数据'}
          </div>
        </div>

        <div className="card" onClick={() => go('portfolio')} style={{ cursor: 'pointer' }}>
          <div className="card-title">我的持仓</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 42, height: 42, background: colors.primaryLight, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
              💼
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 500, color: colors.text }}>持仓管理</div>
              <div style={{ fontSize: 13, color: colors.textMuted }}>添加、编辑你的基金持仓</div>
            </div>
            <span style={{ color: '#C9CDD4', fontSize: 20 }}>&rsaquo;</span>
          </div>
        </div>

        <div className="entry-card" onClick={() => go('overview')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{ width: 36, height: 36, background: B, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 700, color: colors.text }}>
                AI 持仓复盘<span className="entry-badge">NEW</span>
              </div>
              <div style={{ fontSize: 12, color: colors.textMuted }}>基于您的持仓，智能分析本周表现</div>
            </div>
          </div>
          <div className="entry-summary">
            <div style={{ fontSize: 14, color: colors.text, lineHeight: 1.65 }}>
              {overview?.description || portfolioSummary.description}
            </div>
          </div>
          <div className="metric-grid">
            <MetricBox value={typeof weeklyReturn === 'number' ? `${weeklyReturn >= 0 ? '+' : ''}${weeklyReturn.toFixed(0)}` : weeklyReturn} label="本周收益(元)" color={colors.danger} />
            <MetricBox value={weeklyGrowth} label="组合涨幅" color={colors.danger} />
            <MetricBox value={volatility} label="波动状态" color={B} />
          </div>
          <div className="entry-cta">查看完整复盘报告 &rsaquo;</div>
          <div style={{ fontSize: 11, color: '#C9CDD4', marginTop: 10, textAlign: 'center' }}>
            WealthPilot AI Engine · {loading ? '加载中' : '已更新'}
          </div>
        </div>
      </div>
      <div className="bottom-bar">
        <div className="bottom-input" onClick={() => go('chat')}>问 Pilot AI 多智能体任何投资问题</div>
        <div className="bottom-pills">
          <div className="bottom-pill"><span className="dot" style={{ background: Bb }} /> 深度思考</div>
          <div className="bottom-pill"><span className="dot" style={{ background: '#F0EDFF' }} /> 金融技能</div>
        </div>
        <div className="bottom-disclaimer">内容由AI生成，仅供参考</div>
      </div>
    </div>
  )
}
