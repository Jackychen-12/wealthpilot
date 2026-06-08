import { apiFetch } from './client'
import {
  portfolioSummary,
  attributionByFund,
  attributionByIndustry,
  attributionByAsset,
  drawdownFunds,
  healthDimensions,
  suggestions,
} from '../data/mock'

export const analysisApi = {
  overview: () =>
    apiFetch('/api/analysis/overview', {
      weekly_return: 1280,
      weekly_growth_pct: 1.42,
      excess_return_pct: 0.67,
      volatility_status: portfolioSummary.volatility,
      description: portfolioSummary.description,
      total_market_value: 90000,
    }),

  attribution: (by: string = 'fund') => {
    const fallback =
      by === 'industry' ? attributionByIndustry :
      by === 'category' ? attributionByAsset :
      attributionByFund
    return apiFetch(`/api/analysis/attribution?by=${by}`, fallback)
  },

  drawdown: () =>
    apiFetch('/api/analysis/drawdown', drawdownFunds),

  health: () =>
    apiFetch('/api/analysis/health', healthDimensions.map(d => ({
      name: d.name,
      score: d.severity === 'low' ? 80 : d.severity === 'medium' ? 55 : 30,
      status: d.status,
      severity: d.severity,
    }))),

  suggestions: () =>
    apiFetch('/api/analysis/suggestions', suggestions.map(s => ({
      title: s.title,
      desc: s.desc,
      priority: 'medium',
    }))),
}
