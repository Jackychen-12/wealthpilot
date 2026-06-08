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
  return (
    <div className="floating-nav">
      {tabs.map(([key, label]) => (
        <div key={key} className={current === key ? 'active' : ''} onClick={() => onNav(key)}>
          {label}
        </div>
      ))}
    </div>
  )
}
