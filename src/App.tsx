import { useState, useCallback } from 'react'
import { PhoneFrame } from './components/PhoneFrame'
import { FloatingNav } from './components/FloatingNav'
import { Home } from './pages/Home'
import { Overview } from './pages/Overview'
import { Attribution } from './pages/Attribution'
import { Drawdown } from './pages/Drawdown'
import { Health } from './pages/Health'
import { Suggestions } from './pages/Suggestions'
import { WeeklyReport } from './pages/WeeklyReport'
import { Chat } from './pages/Chat'
import { Portfolio } from './pages/Portfolio'
import type { ScreenKey, PageProps } from './types'

const screens: Record<ScreenKey, React.ComponentType<PageProps>> = {
  home: Home,
  overview: Overview,
  attribution: Attribution,
  drawdown: Drawdown,
  health: Health,
  suggest: Suggestions,
  weekly: WeeklyReport,
  chat: Chat,
  portfolio: Portfolio,
}

export function App() {
  const [screen, setScreen] = useState<ScreenKey>('home')
  const [transitioning, setTransitioning] = useState(false)

  const navigate = useCallback((target: ScreenKey) => {
    if (target === screen) return
    setTransitioning(true)
    setTimeout(() => {
      setScreen(target)
      setTransitioning(false)
    }, 150)
  }, [screen])

  const Comp = screens[screen]

  return (
    <>
      <div className="app-layout">
        <PhoneFrame resetScroll={screen}>
          <div className={`screen-transition ${transitioning ? 'exit' : 'enter'}`}>
            <Comp go={navigate} />
          </div>
        </PhoneFrame>
      </div>

      <FloatingNav current={screen} onNav={navigate} />
    </>
  )
}
