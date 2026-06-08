import { apiFetch } from './client'
import { marketIndices, marketNews } from '../data/mock'

export const marketApi = {
  indices: () => apiFetch('/api/market/indices', marketIndices),
  news: () => apiFetch('/api/market/news', marketNews),
  fundInfo: (code: string) => apiFetch(`/api/market/fund/${code}`, null),
  fundNav: (code: string, days = 30) => apiFetch(`/api/market/fund/${code}/nav?days=${days}`, null),
}
