import { apiFetch, apiPost, apiPut, apiDelete } from './client'

export interface Holding {
  id: number
  fund_code: string
  fund_name: string
  shares: number
  cost_price: number
  buy_date: string
  category: string
  industry: string
  latest_nav?: number
  market_value?: number
  total_return?: number
  return_pct?: number
}

export interface HoldingCreate {
  fund_code: string
  fund_name: string
  shares: number
  cost_price: number
  buy_date: string
  category: string
  industry?: string
}

export const portfolioApi = {
  list: () => apiFetch<Holding[]>('/api/portfolio', []),

  add: (data: HoldingCreate) =>
    apiPost<HoldingCreate, Holding | null>('/api/portfolio', data, null),

  update: (id: number, data: Partial<HoldingCreate>) =>
    apiPut<Partial<HoldingCreate>, Holding>(`/api/portfolio/${id}`, data),

  remove: (id: number) => apiDelete(`/api/portfolio/${id}`),
}
