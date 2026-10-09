import type React from 'react'
import { useState } from 'react'
import { HashRouter, Route, Routes } from 'react-router-dom'
import { api, session, useApi } from './api'
import { useResearch } from './api/researchStore'
import { Button, Callout, Drawer, Input } from './components/kit'
import { Shell } from './components/layout/Shell'
import ResearchPage from './pages/ResearchPage'
import HoldingsPage from './pages/HoldingsPage'
import RiskPage from './pages/RiskPage'
import StressPage from './pages/StressPage'
import ReportPage from './pages/ReportPage'
import ProfilePage from './pages/ProfilePage'
import LookthroughPage from './pages/LookthroughPage'
import RebalancePage from './pages/RebalancePage'
import FundPage from './pages/FundPage'
import BacktestPage from './pages/BacktestPage'
import StockPage from './pages/StockPage'
import ConnectorsPage from './pages/ConnectorsPage'
import TodayPage from './pages/TodayPage'
import MarketPage, { MacroPage } from './pages/MarketPage'
import WatchlistPage from './pages/WatchlistPage'
import ScreenerPage from './pages/ScreenerPage'
import HistoryPage from './pages/HistoryPage'
import ReviewPage from './pages/ReviewPage'
import GlossaryPage from './pages/GlossaryPage'
import TradesPage from './pages/TradesPage'
import AutomationsPage from './pages/AutomationsPage'
import BrokerPage from './pages/BrokerPage'
import SettingsPage from './pages/SettingsPage'
import { AuditPage, MemoryPage, SkillsPage } from './pages/AgentPages'

const App: React.FC = () => {
  // 登录状态变化后换 key，让所有页面重新取数
  const [epoch, setEpoch] = useState(0)
  const [authOpen, setAuthOpen] = useState(false)
  const backend = useApi(api.health, [epoch])
  const alerts = useApi(api.alerts, [epoch])
  const { turns } = useResearch()

  return (
    <HashRouter>
      <Routes>
        <Route
          element={(
            <Shell
              backend={backend.error ? 'down' : backend.data ? 'ok' : 'checking'}
              username={session.username}
              alertCount={alerts.data?.alerts.length ?? 0}
              researchBusy={turns.some((t) => t.running)}
              onLogin={() => setAuthOpen(true)}
              onLogout={() => { session.clear(); setEpoch((e) => e + 1) }}
            />
          )}
        >
          <Route path="/" element={<TodayPage key={epoch} />} />
          <Route path="/research" element={<ResearchPage key={epoch} />} />
          <Route path="/market" element={<MarketPage key={epoch} />} />
          <Route path="/macro" element={<MacroPage key={epoch} />} />
          <Route path="/screener" element={<ScreenerPage key={epoch} />} />
          <Route path="/watchlist" element={<WatchlistPage key={epoch} />} />
          <Route path="/skills" element={<SkillsPage key={epoch} />} />
          <Route path="/memory" element={<MemoryPage key={epoch} />} />
          <Route path="/audit" element={<AuditPage key={epoch} />} />
          <Route path="/settings" element={<SettingsPage key={epoch} />} />
          <Route path="/broker" element={<BrokerPage key={epoch} />} />
          <Route path="/automations" element={<AutomationsPage key={epoch} />} />
          <Route path="/review" element={<ReviewPage key={epoch} />} />
          <Route path="/trades" element={<TradesPage key={epoch} />} />
          <Route path="/glossary" element={<GlossaryPage />} />
          <Route path="/history/:id?" element={<HistoryPage key={epoch} />} />
          <Route path="/overview" element={<HoldingsPage key={`${epoch}-a`} initialTab="analysis" />} />
          <Route path="/holdings" element={<HoldingsPage key={epoch} />} />
          <Route path="/risk" element={<RiskPage key={epoch} />} />
          <Route path="/stress" element={<StressPage key={epoch} />} />
          <Route path="/lookthrough" element={<LookthroughPage key={epoch} />} />
          <Route path="/rebalance" element={<RebalancePage key={epoch} />} />
          <Route path="/fund/:code?" element={<FundPage key={epoch} />} />
          <Route path="/backtest" element={<BacktestPage key={epoch} />} />
          <Route path="/stock/:code?" element={<StockPage key={epoch} />} />
          <Route path="/connectors" element={<ConnectorsPage key={epoch} />} />
          <Route path="/report" element={<ReportPage key={epoch} />} />
          <Route path="/profile" element={<ProfilePage key={epoch} />} />
          <Route path="*" element={<TodayPage key={epoch} />} />
        </Route>
      </Routes>
      <AuthDrawer open={authOpen} onClose={() => setAuthOpen(false)} onDone={() => { setAuthOpen(false); setEpoch((e) => e + 1) }} />
    </HashRouter>
  )
}

const AuthDrawer: React.FC<{ open: boolean; onClose: () => void; onDone: () => void }> = ({ open, onClose, onDone }) => {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await (mode === 'login' ? api.login : api.register)(username, password)
      session.set(res.access_token, res.username)
      setPassword('')
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : '失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer open={open} onClose={onClose} title={mode === 'login' ? '登录' : '注册'} width="max-w-sm">
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <p className="text-sm text-steel">登录后看到的是你自己账户下的持仓与画像；不登录使用本机的匿名档。</p>
        <Input id="auth-user" label="用户名" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <Input id="auth-pass" label="密码" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={4} />
        {error ? <Callout tone="danger">{error}</Callout> : null}
        <div className="flex items-center gap-2">
          <Button type="submit" loading={busy}>{mode === 'login' ? '登录' : '注册并登录'}</Button>
          <Button variant="ghost" onClick={() => setMode((m) => (m === 'login' ? 'register' : 'login'))}>
            {mode === 'login' ? '没有账户？注册' : '已有账户？登录'}
          </Button>
        </div>
      </form>
    </Drawer>
  )
}

export default App
