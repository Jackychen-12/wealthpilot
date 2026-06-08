import { useState, useEffect, useCallback } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { colors } from '../utils/theme'
import { portfolioApi, type Holding, type HoldingCreate } from '../api/portfolio'
import type { PageProps } from '../types'

export function Portfolio({ go }: PageProps) {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  const [fundCode, setFundCode] = useState('')
  const [fundName, setFundName] = useState('')
  const [shares, setShares] = useState('')
  const [costPrice, setCostPrice] = useState('')
  const [buyDate, setBuyDate] = useState('')
  const [category, setCategory] = useState('equity')

  const loadHoldings = useCallback(async () => {
    setLoading(true)
    const data = await portfolioApi.list()
    setHoldings(data)
    setLoading(false)
  }, [])

  useEffect(() => { loadHoldings() }, [loadHoldings])

  const handleAdd = async () => {
    if (!fundCode || !fundName || !shares || !costPrice || !buyDate) return
    const data: HoldingCreate = {
      fund_code: fundCode,
      fund_name: fundName,
      shares: parseFloat(shares),
      cost_price: parseFloat(costPrice),
      buy_date: buyDate,
      category,
    }
    await portfolioApi.add(data)
    setShowForm(false)
    setFundCode('')
    setFundName('')
    setShares('')
    setCostPrice('')
    setBuyDate('')
    loadHoldings()
  }

  const handleDelete = async (id: number) => {
    await portfolioApi.remove(id)
    loadHoldings()
  }

  const categoryLabel: Record<string, string> = {
    equity: '权益',
    bond: '债券',
    money: '货币',
    hybrid: '混合',
  }

  return (
    <div className="screen">
      <Notch />
      <NavBar title="持仓管理" onBack={() => go('overview')} />
      <div className="content">
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>我的持仓（{holdings.length}）</span>
            <div
              onClick={() => setShowForm(!showForm)}
              style={{
                background: colors.primary,
                color: '#fff',
                borderRadius: 8,
                padding: '5px 12px',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              {showForm ? '取消' : '+ 添加'}
            </div>
          </div>

          {showForm && (
            <div style={{ padding: '12px 0', borderBottom: `1px solid ${colors.border}`, marginBottom: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <input
                  placeholder="基金代码 (如 007340)"
                  value={fundCode}
                  onChange={e => setFundCode(e.target.value)}
                  style={inputStyle}
                />
                <input
                  placeholder="基金名称"
                  value={fundName}
                  onChange={e => setFundName(e.target.value)}
                  style={inputStyle}
                />
                <input
                  placeholder="持有份额"
                  type="number"
                  value={shares}
                  onChange={e => setShares(e.target.value)}
                  style={inputStyle}
                />
                <input
                  placeholder="成本净值"
                  type="number"
                  step="0.0001"
                  value={costPrice}
                  onChange={e => setCostPrice(e.target.value)}
                  style={inputStyle}
                />
                <input
                  type="date"
                  value={buyDate}
                  onChange={e => setBuyDate(e.target.value)}
                  style={inputStyle}
                />
                <select value={category} onChange={e => setCategory(e.target.value)} style={inputStyle}>
                  <option value="equity">权益类</option>
                  <option value="bond">债券类</option>
                  <option value="money">货币类</option>
                  <option value="hybrid">混合类</option>
                </select>
              </div>
              <div
                onClick={handleAdd}
                style={{
                  background: colors.primary,
                  color: '#fff',
                  borderRadius: 8,
                  padding: '8px 0',
                  textAlign: 'center',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                确认添加
              </div>
            </div>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: 20, color: colors.textMuted }}>加载中...</div>
          ) : holdings.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: colors.textMuted }}>
              暂无持仓，点击上方"+ 添加"录入你的基金
            </div>
          ) : (
            holdings.map(h => (
              <div key={h.id} style={{
                display: 'flex',
                alignItems: 'center',
                padding: '10px 0',
                borderBottom: `1px solid ${colors.borderLight}`,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>{h.fund_name}</div>
                  <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                    {h.fund_code} · {categoryLabel[h.category] || h.category} · {h.shares}份 · 成本{h.cost_price}
                  </div>
                </div>
                <div
                  onClick={() => handleDelete(h.id)}
                  style={{ color: colors.danger, fontSize: 12, cursor: 'pointer', padding: '4px 8px' }}
                >
                  删除
                </div>
              </div>
            ))
          )}
        </div>

        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div
            onClick={() => go('overview')}
            style={{
              display: 'inline-block',
              background: colors.primaryLight,
              color: colors.primary,
              borderRadius: 8,
              padding: '8px 20px',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            查看持仓分析 →
          </div>
        </div>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 8,
  border: '1px solid #E5E6EB',
  fontSize: 13,
  outline: 'none',
  background: '#F7F8FA',
}
