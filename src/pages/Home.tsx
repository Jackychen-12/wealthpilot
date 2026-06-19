import { useState, useEffect } from 'react'
import { Notch } from '../components/Notch'
import { Tag } from '../components/Tag'
import { MetricBox } from '../components/MetricBox'
import { Skeleton } from '../components/Skeleton'
import { colors } from '../utils/theme'
import { marketIndices as mockIndices, marketNews as mockNews, portfolioSummary } from '../data/mock'
import { marketApi } from '../api/market'
import { analysisApi } from '../api/analysis'
import { useAppNavigate } from '../hooks/useAppNavigate'

const B = colors.primary
const Bb = colors.primaryLight

function ArrowIcon({ up }: { up: boolean }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ marginRight: 2 }}>
      {up
        ? <path d="M5 1L9 6H1L5 1Z" fill="currentColor" />
        : <path d="M5 9L1 4H9L5 9Z" fill="currentColor" />}
    </svg>
  )
}

export function Home() {
  const go = useAppNavigate()
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
        <span style={{ width: 32 }} />
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
          WealthPilot
        </div>
        <span style={{ width: 32 }} />
      </div>
      <div className="content">
        <div className="card">
          <div className="card-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={B} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 6 }}>
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            行情追踪
            <svg onClick={() => {}} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={B} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: 'auto', cursor: 'pointer' }}>
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {indices.map((idx, i) => (
              <div key={i} style={{
                flex: 1,
                background: idx.up ? 'rgba(16,185,129,0.06)' : 'rgba(239,68,68,0.06)',
                borderRadius: 10,
                padding: '10px 8px',
                border: `1px solid ${idx.up ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'}`,
              }}>
                <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 2 }}>{idx.name}</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: idx.up ? colors.success : colors.danger, fontFamily: 'DM Sans', letterSpacing: '-0.5px' }}>
                  {idx.value}
                </div>
                <div style={{ fontSize: 12, color: idx.up ? colors.success : colors.danger, fontWeight: 500, display: 'flex', alignItems: 'center' }}>
                  <ArrowIcon up={idx.up} />
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
            WealthPilot AI Engine · {loading ? <Skeleton width={48} height={12} style={{ display: 'inline-block', verticalAlign: 'middle' }} /> : '实时数据'}
          </div>
        </div>

        <div className="card card-click" onClick={() => go('portfolio')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 42, height: 42, background: 'linear-gradient(135deg, #ECFDF5, #D1FAE5)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={colors.portfolioAccent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16" />
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 500, color: colors.text }}>持仓管理</div>
              <div style={{ fontSize: 13, color: colors.textMuted }}>添加、编辑你的基金持仓</div>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#C9CDD4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </div>
        </div>

        <div className="entry-card" onClick={() => go('overview')}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <div style={{ width: 36, height: 36, background: 'linear-gradient(135deg, #7C3AED, #6366F1)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
            WealthPilot AI Engine · {loading ? <Skeleton width={36} height={12} style={{ display: 'inline-block', verticalAlign: 'middle' }} /> : '已更新'}
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
