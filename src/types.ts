export type ScreenKey =
  | 'home'
  | 'overview'
  | 'attribution'
  | 'drawdown'
  | 'health'
  | 'suggest'
  | 'weekly'
  | 'chat'

export interface PageProps {
  go: (screen: ScreenKey) => void
}

export type Severity = 'high' | 'medium' | 'low'
