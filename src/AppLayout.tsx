import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { PhoneFrame } from './components/PhoneFrame'
import { FloatingNav } from './components/FloatingNav'
import { ROUTE_META } from './router'
import type { ScreenKey } from './types'

const PATH_TO_SCREEN: Record<string, ScreenKey> = {
  '/': 'home',
  '/portfolio': 'portfolio',
  '/overview': 'overview',
  '/attribution': 'attribution',
  '/drawdown': 'drawdown',
  '/health': 'health',
  '/suggestions': 'suggest',
  '/weekly': 'weekly',
  '/chat': 'chat',
  '/login': 'login',
  '/risk-profile': 'risk-profile',
}

const SCREEN_TO_PATH: Record<ScreenKey, string> = Object.fromEntries(
  Object.entries(PATH_TO_SCREEN).map(([path, screen]) => [screen, path])
) as Record<ScreenKey, string>

export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const path = location.pathname
  const info = ROUTE_META[path] ?? ROUTE_META['/']
  const currentScreen = PATH_TO_SCREEN[path] ?? 'home'

  const handleNav = (screen: ScreenKey) => {
    const target = SCREEN_TO_PATH[screen] ?? '/'
    navigate(target)
  }

  return (
    <>
      <div className="landing-layout">
        <div className="landing-info">
          <div className="landing-logo">
            <div className="landing-logo-icon" style={{ background: info.iconBg }}>
              <span style={{ fontSize: 24 }}>{info.icon}</span>
            </div>
            <span className="landing-logo-text">{info.title}</span>
          </div>

          <div className="landing-tagline">{info.subtitle}</div>

          <div className="landing-features">
            {info.points.map((p, i) => (
              <div key={i} className="landing-feature">
                <div style={{ fontSize: 14, lineHeight: 1.6 }}>{p}</div>
              </div>
            ))}
          </div>

          {info.tech && (
            <div className="landing-badges">
              {info.tech.map((t, i) => (
                <span key={i} className="landing-badge">{t}</span>
              ))}
            </div>
          )}
        </div>

        <PhoneFrame resetScroll={path}>
          <Outlet />
        </PhoneFrame>
      </div>

      <FloatingNav current={currentScreen} onNav={handleNav} />
    </>
  )
}
