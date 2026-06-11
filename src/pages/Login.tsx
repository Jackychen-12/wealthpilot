import { useState } from 'react'
import { Notch } from '../components/Notch'
import { NavBar } from '../components/NavBar'
import { colors } from '../utils/theme'
import type { PageProps } from '../types'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function Login({ go }: PageProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!username || !password) { setError('请填写用户名和密码'); return }
    setLoading(true); setError('')

    const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register'
    const body = mode === 'login'
      ? { username, password }
      : { username, password, email }

    try {
      const resp = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await resp.json()
      if (resp.ok) {
        localStorage.setItem('wp_token', data.access_token)
        localStorage.setItem('wp_user', data.username)
        go('home')
      } else {
        setError(data.detail || '操作失败')
      }
    } catch {
      setError('网络错误，请确认后端已启动')
    }
    setLoading(false)
  }

  const isLoggedIn = !!localStorage.getItem('wp_token')
  const displayName = localStorage.getItem('wp_user') || '用户'

  return (
    <div className="screen page-accent-warm">
      <Notch />
      <NavBar title="我的" />
      <div className="content">
        {isLoggedIn ? (
          <>
            <div className="card" style={{ textAlign: 'center', padding: '24px 16px 16px' }}>
              <div className="profile-avatar" style={{ background: 'linear-gradient(135deg, #F97316, #FB923C)' }}>
                {displayName.slice(0, 1).toUpperCase()}
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: colors.text }}>{displayName}</div>
              <div style={{ fontSize: 12, color: colors.textMuted, marginTop: 2 }}>
                <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: colors.success, marginRight: 4, verticalAlign: 'middle' }} />
                已登录
              </div>
              <div className="profile-stats">
                <div className="profile-stat">
                  <div className="profile-stat-val" style={{ color: colors.primary }}>--</div>
                  <div className="profile-stat-label">持仓数</div>
                </div>
                <div className="profile-stat">
                  <div className="profile-stat-val" style={{ color: colors.success }}>--</div>
                  <div className="profile-stat-label">总收益</div>
                </div>
                <div className="profile-stat">
                  <div className="profile-stat-val" style={{ color: colors.warning }}>--</div>
                  <div className="profile-stat-label">风险等级</div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="profile-menu-item" onClick={() => go('portfolio')}>
                <div className="profile-menu-icon" style={{ background: '#ECFDF5' }}>💼</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>持仓管理</div>
                  <div style={{ fontSize: 12, color: colors.textMuted }}>查看和管理基金持仓</div>
                </div>
                <span style={{ color: '#C9CDD4', fontSize: 18 }}>&rsaquo;</span>
              </div>
              <div className="profile-menu-item" onClick={() => go('risk-profile')}>
                <div className="profile-menu-icon" style={{ background: '#FFF7ED' }}>📝</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>风险评估</div>
                  <div style={{ fontSize: 12, color: colors.textMuted }}>评估您的风险偏好</div>
                </div>
                <span style={{ color: '#C9CDD4', fontSize: 18 }}>&rsaquo;</span>
              </div>
              <div className="profile-menu-item" onClick={() => go('weekly')}>
                <div className="profile-menu-icon" style={{ background: '#EFF6FF' }}>📋</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>AI 周报</div>
                  <div style={{ fontSize: 12, color: colors.textMuted }}>查看 AI 生成的复盘报告</div>
                </div>
                <span style={{ color: '#C9CDD4', fontSize: 18 }}>&rsaquo;</span>
              </div>
              <div className="profile-menu-item" onClick={() => go('chat')}>
                <div className="profile-menu-icon" style={{ background: '#F5F3FF' }}>🤖</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 500, color: colors.text }}>AI 对话</div>
                  <div style={{ fontSize: 12, color: colors.textMuted }}>与 Pilot AI 多智能体对话</div>
                </div>
                <span style={{ color: '#C9CDD4', fontSize: 18 }}>&rsaquo;</span>
              </div>
            </div>

            <div
              className="form-btn form-btn-danger"
              onClick={() => { localStorage.removeItem('wp_token'); localStorage.removeItem('wp_user'); setError('') }}
              style={{ marginTop: 8 }}
            >
              退出登录
            </div>
          </>
        ) : (
          <>
            <div className="card" style={{ textAlign: 'center', padding: '28px 20px 24px' }}>
              <div className="profile-avatar" style={{ background: 'linear-gradient(135deg, #2563EB, #3B82F6)' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0110 0v4" />
                </svg>
              </div>
              <div style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>
                {mode === 'login' ? '登录 WealthPilot' : '注册新账号'}
              </div>
              <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
                {mode === 'login' ? '登录后持仓数据与你的账号绑定' : '注册后即可使用所有功能'}
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <input className="form-input" placeholder="用户名" value={username} onChange={e => setUsername(e.target.value)} />
                {mode === 'register' && (
                  <input className="form-input" placeholder="邮箱（可选）" value={email} onChange={e => setEmail(e.target.value)} />
                )}
                <input className="form-input" placeholder="密码" type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()} />

                {error && <div style={{ fontSize: 12, color: colors.danger }}>{error}</div>}

                <div className="form-btn form-btn-primary" onClick={handleSubmit} style={{ opacity: loading ? 0.6 : 1 }}>
                  {loading ? '处理中...' : mode === 'login' ? '登录' : '注册'}
                </div>

                <div style={{ textAlign: 'center', fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
                  {mode === 'login' ? (
                    <>还没有账号？<span onClick={() => { setMode('register'); setError('') }} style={{ color: colors.primary, cursor: 'pointer', fontWeight: 500 }}>注册</span></>
                  ) : (
                    <>已有账号？<span onClick={() => { setMode('login'); setError('') }} style={{ color: colors.primary, cursor: 'pointer', fontWeight: 500 }}>登录</span></>
                  )}
                </div>
              </div>
            </div>

            <div onClick={() => go('home')} style={{ textAlign: 'center', fontSize: 12, color: colors.textMuted, marginTop: 12, cursor: 'pointer' }}>
              跳过，不登录直接使用 →
            </div>
          </>
        )}
      </div>
    </div>
  )
}
