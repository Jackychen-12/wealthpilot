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

export interface OverviewData {
  total_market_value: number
  weekly_return: number
  weekly_growth_pct: number
  excess_return_pct: number
  volatility_status: string
  description: string
  sharpe_ratio?: number
  top_contributors?: { name: string; value: string; pct: number; positive: boolean }[]
  top_detractors?: { name: string; value: string; pct: number; positive: boolean }[]
}

export interface DrawdownFund {
  name: string
  value: string
  severity: Severity
  max_drawdown?: number
  recovery_days?: number
  recovered?: boolean
}

export interface HealthDimension {
  name: string
  status: string
  severity: Severity
  score?: number
}

export interface WeeklyReportData {
  overview?: { weekly_return?: number; weekly_growth_pct?: number; excess_return_pct?: number }
  key_points?: { title: string; desc: string }[]
  next_week_focus?: string[]
  risk_warnings?: string[]
  ai_insight?: string
  summary?: string
  week_start?: string
  week_end?: string
  generated_at?: string
}
