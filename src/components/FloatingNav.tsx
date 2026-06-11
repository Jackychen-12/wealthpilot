import { useRef, useEffect, useState } from 'react'
import type { ScreenKey } from '../types'

const tabs: [ScreenKey, string][] = [
  ['home', '主页'],
  ['portfolio', '持仓'],
  ['overview', '总览'],
  ['attribution', '归因'],
  ['health', '健康度'],
  ['weekly', '周报'],
  ['chat', 'AI'],
  ['risk-profile', '风评'],
  ['login', '我的'],
]

export function FloatingNav({ current, onNav }: { current: ScreenKey; onNav: (k: ScreenKey) => void }) {
  const navRef = useRef<HTMLDivElement>(null)
  const [indicator, setIndicator] = useState({ left: 0, width: 0 })

  useEffect(() => {
    if (!navRef.current) return
    const activeEl = navRef.current.querySelector('.active') as HTMLElement | null
    if (activeEl) {
      setIndicator({
        left: activeEl.offsetLeft,
        width: activeEl.offsetWidth,
      })
    }
  }, [current])

  return (
    <div className="floating-nav" ref={navRef}>
      <div
        className="floating-nav-indicator"
        style={{ left: indicator.left, width: indicator.width }}
      />
      {tabs.map(([key, label]) => (
        <div key={key} className={current === key ? 'active' : ''} onClick={() => onNav(key)}>
          {label}
        </div>
      ))}
    </div>
  )
}
