import { useState, useEffect, useCallback, useRef } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { Skeleton } from '../components/Skeleton'
import { colors } from '../utils/theme'
import { portfolioApi, type Holding, type HoldingCreate } from '../api/portfolio'
import { useAppNavigate } from '../hooks/useAppNavigate'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function Portfolio() {
  const go = useAppNavigate()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const csvInputRef = useRef<HTMLInputElement>(null)
  const ocrInputRef = useRef<HTMLInputElement>(null)

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
    setFundCode(''); setFundName(''); setShares(''); setCostPrice(''); setBuyDate('')
    loadHoldings()
  }

  const handleDelete = async (id: number) => {
    await portfolioApi.remove(id)
    loadHoldings()
  }

  const handleCsvImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImportStatus('正在导入...')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const token = localStorage.getItem('wp_token')
      const resp = await fetch(`${API_BASE}/api/portfolio/import/csv`, {
        method: 'POST', body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await resp.json()
      if (resp.ok) {
        setImportStatus(`✅ 成功导入 ${data.imported_count} 条持仓`)
        loadHoldings()
      } else {
        setImportStatus(`❌ ${data.detail || '导入失败'}`)
      }
    } catch {
      setImportStatus('❌ 网络错误，请确认后端已启动')
    }
    if (csvInputRef.current) csvInputRef.current.value = ''
  }

  const handleOcrImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImportStatus('🔍 正在 OCR 识别...')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const token = localStorage.getItem('wp_token')
      const resp = await fetch(`${API_BASE}/api/portfolio/import/ocr`, {
        method: 'POST', body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await resp.json()
      if (resp.ok) {
        setImportStatus(`✅ OCR 识别并导入 ${data.imported_count} 条持仓`)
        loadHoldings()
      } else {
        setImportStatus(`❌ ${data.detail || 'OCR 失败'}`)
      }
    } catch {
      setImportStatus('❌ OCR 需要后端配置 ANTHROPIC_API_KEY')
    }
    if (ocrInputRef.current) ocrInputRef.current.value = ''
  }

  const categoryLabel: Record<string, string> = {
    equity: '权益', bond: '债券', money: '货币', hybrid: '混合',
  }

  return (
    <div className="screen">
      <Notch />
      <NavBar title="持仓管理" onBack={() => go('overview')} />
      <div className="content">
        {/* 导入区 */}
        <div className="card">
          <div className="card-title">快速导入</div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <div onClick={() => csvInputRef.current?.click()} style={importBtnStyle}>
              📄 CSV/Excel 导入
            </div>
            <div onClick={() => ocrInputRef.current?.click()} style={importBtnStyle}>
              📷 截图 OCR 识别
            </div>
          </div>
          <input ref={csvInputRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleCsvImport} style={{ display: 'none' }} />
          <input ref={ocrInputRef} type="file" accept="image/*" onChange={handleOcrImport} style={{ display: 'none' }} />
          {importStatus && (
            <div style={{ fontSize: 12, color: importStatus.startsWith('✅') ? colors.success : importStatus.startsWith('❌') ? colors.danger : colors.primary, marginTop: 6 }}>
              {importStatus}
            </div>
          )}
          <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 6 }}>
            CSV 支持天天基金导出格式；OCR 需要后端配置 Claude API Key
          </div>
        </div>

        {/* 持仓列表 */}
        <div className="card">
          <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>我的持仓（{holdings.length}）</span>
            <div onClick={() => setShowForm(!showForm)} style={{ background: colors.primary, color: '#fff', borderRadius: 8, padding: '5px 12px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
              {showForm ? '取消' : '+ 手动添加'}
            </div>
          </div>

          {showForm && (
            <div style={{ padding: '12px 0', borderBottom: `1px solid ${colors.border}`, marginBottom: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                <input placeholder="基金代码 (如 007340)" value={fundCode} onChange={e => setFundCode(e.target.value)} style={inputStyle} />
                <input placeholder="基金名称" value={fundName} onChange={e => setFundName(e.target.value)} style={inputStyle} />
                <input placeholder="持有份额" type="number" value={shares} onChange={e => setShares(e.target.value)} style={inputStyle} />
                <input placeholder="成本净值" type="number" step="0.0001" value={costPrice} onChange={e => setCostPrice(e.target.value)} style={inputStyle} />
                <input type="date" value={buyDate} onChange={e => setBuyDate(e.target.value)} style={inputStyle} />
                <select value={category} onChange={e => setCategory(e.target.value)} style={inputStyle}>
                  <option value="equity">权益类</option>
                  <option value="bond">债券类</option>
                  <option value="money">货币类</option>
                  <option value="hybrid">混合类</option>
                </select>
              </div>
              <div onClick={handleAdd} style={{ background: colors.primary, color: '#fff', borderRadius: 8, padding: '8px 0', textAlign: 'center', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
                确认添加
              </div>
            </div>
          )}

          {loading ? (
            <div style={{ padding: 20 }}>
              <Skeleton width="60%" height={14} style={{ marginBottom: 12 }} />
              <Skeleton width="100%" height={48} style={{ marginBottom: 8 }} />
              <Skeleton width="100%" height={48} style={{ marginBottom: 8 }} />
              <Skeleton width="100%" height={48} />
            </div>
          ) : holdings.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: colors.textMuted }}>
              暂无持仓，使用上方导入或手动添加
            </div>
          ) : (
            holdings.map(h => (
              <div key={h.id} style={{ display: 'flex', alignItems: 'center', padding: '10px 0', borderBottom: `1px solid ${colors.borderLight}` }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>{h.fund_name}</div>
                  <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                    {h.fund_code} · {categoryLabel[h.category] || h.category} · {h.shares}份
                  </div>
                  {h.return_pct != null && (
                    <div style={{ fontSize: 12, marginTop: 2, color: h.return_pct >= 0 ? colors.success : colors.danger, fontWeight: 600 }}>
                      {h.return_pct >= 0 ? '+' : ''}{h.return_pct}% · 市值 {h.market_value?.toLocaleString()}元
                    </div>
                  )}
                </div>
                <div onClick={() => handleDelete(h.id)} style={{ color: colors.danger, fontSize: 12, cursor: 'pointer', padding: '4px 8px' }}>
                  删除
                </div>
              </div>
            ))
          )}
        </div>

        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <div onClick={() => go('overview')} style={{ display: 'inline-block', background: colors.primaryLight, color: colors.primary, borderRadius: 8, padding: '8px 20px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
            查看持仓分析 →
          </div>
        </div>
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #E5E6EB', fontSize: 13, outline: 'none', background: '#F7F8FA',
}

const importBtnStyle: React.CSSProperties = {
  flex: 1, padding: '10px 0', textAlign: 'center', borderRadius: 8, border: `1px dashed ${colors.border}`, fontSize: 13, color: colors.primary, fontWeight: 500, cursor: 'pointer', background: colors.primaryLight,
}
