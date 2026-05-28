import type { ScreenKey } from '../types'

const tabs: [ScreenKey, string][] = [
  ['home', '主页'],
  ['overview', '总览'],
  ['attribution', '归因'],
  ['drawdown', '回撤'],
  ['health', '健康度'],
  ['suggest', '建议'],
  ['weekly', '周报'],
  ['chat', '追问'],
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
