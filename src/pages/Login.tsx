import { useState } from 'react'
import { Notch } from '../components/Notch'
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

  return (
    <div className="screen">
      <Notch />
      <div className="content" style={{ padding: '40px 20px' }}>
        {isLoggedIn ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>👤</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: colors.text }}>
              {localStorage.getItem('wp_user')}
            </div>
            <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>已登录</div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 24 }}>
              <div onClick={() => go('home')} style={btnStyle}>进入首页</div>
              <div onClick={() => { localStorage.removeItem('wp_token'); localStorage.removeItem('wp_user'); setError(''); }} style={{ ...btnStyle, background: colors.dangerLight, color: colors.danger }}>退出登录</div>
            </div>
          </div>
        ) : (
          <>
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>🔐</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: colors.text }}>
                {mode === 'login' ? '登录 WealthPilot' : '注册新账号'}
              </div>
              <div style={{ fontSize: 13, color: colors.textMuted, marginTop: 4 }}>
                {mode === 'login' ? '登录后持仓数据与你的账号绑定' : '注册后即可使用所有功能'}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input placeholder="用户名" value={username} onChange={e => setUsername(e.target.value)} style={inputStyle} />
              {mode === 'register' && (
                <input placeholder="邮箱（可选）" value={email} onChange={e => setEmail(e.target.value)} style={inputStyle} />
              )}
              <input placeholder="密码" type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSubmit()} style={inputStyle} />

              {error && <div style={{ fontSize: 12, color: colors.danger }}>{error}</div>}

              <div onClick={handleSubmit} style={{ ...btnStyle, opacity: loading ? 0.6 : 1 }}>
                {loading ? '处理中...' : mode === 'login' ? '登录' : '注册'}
              </div>

              <div style={{ textAlign: 'center', fontSize: 13, color: colors.textMuted, marginTop: 8 }}>
                {mode === 'login' ? (
                  <>还没有账号？<span onClick={() => { setMode('register'); setError('') }} style={{ color: colors.primary, cursor: 'pointer' }}>注册</span></>
                ) : (
                  <>已有账号？<span onClick={() => { setMode('login'); setError('') }} style={{ color: colors.primary, cursor: 'pointer' }}>登录</span></>
                )}
              </div>

              <div onClick={() => go('home')} style={{ textAlign: 'center', fontSize: 12, color: colors.textMuted, marginTop: 16, cursor: 'pointer' }}>
                跳过，不登录直接使用 →
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '12px 14px', borderRadius: 10, border: '1px solid #E5E6EB', fontSize: 14, outline: 'none', background: '#F7F8FA',
}

const btnStyle: React.CSSProperties = {
  padding: '12px 0', textAlign: 'center', borderRadius: 10, background: colors.primary, color: '#fff', fontSize: 15, fontWeight: 600, cursor: 'pointer',
}
