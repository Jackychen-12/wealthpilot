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
  | 'login'
  | 'risk-profile'

/** @deprecated Use useAppNavigate() hook instead */
export interface PageProps {
  go: (screen: ScreenKey) => void
}

export type Severity = 'high' | 'medium' | 'low'
