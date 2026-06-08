export type ScreenKey =
  | 'home'
  | 'overview'
  | 'attribution'
  | 'drawdown'
  | 'health'
  | 'suggest'
  | 'weekly'
  | 'chat'
  | 'portfolio'

export interface PageProps {
  go: (screen: ScreenKey) => void
}

export type Severity = 'high' | 'medium' | 'low'
