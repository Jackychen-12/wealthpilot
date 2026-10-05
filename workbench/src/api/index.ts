/**
 * 工作台 API 层。
 *
 * 与演示版的区别：请求失败就是失败，抛错给页面显示，绝不回退到示例数据 ——
 * 工作台上的每个数字都必须是后端算出来的。
 */
import { useCallback, useEffect, useState } from 'react'

// 默认走同源：开发时由 Vite 代理到后端，部署时由后端直接托管页面
export const API_BASE: string = import.meta.env.VITE_API_URL || ''
/** 在线演示构建：没有后端，回放录好的真实结果（见 src/demo）。 */
export const DEMO = import.meta.env.VITE_DEMO === '1'
const TOKEN_KEY = 'wp_token'
const USER_KEY = 'wp_user'

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) || '' },
  get username() { return localStorage.getItem(USER_KEY) || '' },
  set(token: string, username: string) { localStorage.setItem(TOKEN_KEY, token); localStorage.setItem(USER_KEY, username) },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY) },
}

const authHeaders = (): Record<string, string> => (session.token ? { Authorization: `Bearer ${session.token}` } : {})

export class ApiError extends Error {}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (DEMO) {
    const { demoRequest } = await import('../demo')
    try {
      return (await demoRequest(path, init)) as T
    } catch (e) {
      throw new ApiError(e instanceof Error ? e.message : '演示数据不可用')
    }
  }
  let resp: Response
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...authHeaders(), ...(init.headers || {}) } })
  } catch {
    throw new ApiError('连不上后端，请确认已运行 make backend')
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new ApiError(body?.detail ? String(body.detail) : `请求失败（${resp.status}）`)
  }
  return resp.json()
}

const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

// ── 类型 ────────────────────────────────────────────────

export interface Holding {
  id: number; asset_type: string; fund_code: string; fund_name: string; shares: number; cost_price: number
  buy_date: string; category: string; industry: string
  latest_nav: number | null; market_value: number | null; total_return: number | null; return_pct: number | null
}
export interface HoldingInput {
  asset_type: string; fund_code: string; fund_name: string; shares: number; cost_price: number
  buy_date: string; category: string; industry: string
}
export interface Overview {
  total_market_value: number; total_cost: number; total_return: number; return_pct: number
  weekly_return: number; weekly_growth_pct: number; excess_return_pct: number | null
  volatility_status: string; sharpe_ratio: number | null; holdings_count?: number
  description?: string; methodology?: string
}
export interface AttributionRow { name: string; value: string; pct: number; positive: boolean }
export interface DrawdownRow { name: string; value: string; severity: string; max_drawdown_pct: number; recovery_days: number; recovered: boolean }
export interface Drawdown { funds: DrawdownRow[]; summary?: { avg_drawdown_pct: number; avg_recovery_days: number; high_risk_count: number } }
export interface Health { dimensions: { name: string; score: number; status: string; severity: string }[]; overall_score: number; overall_status: string }
export interface Correlation { matrix: Record<string, Record<string, number>>; names: Record<string, string> }
export interface Suggestion { title: string; desc: string; priority: string }
export interface IndexQuote { name: string; value: string; change: string; up: boolean }
export interface NewsItem { tag: string; text: string; source_url?: string; published_at?: string }
export interface AlertItem { id?: number; kind: string; severity: string; message: string; fund_name: string; value: number; read?: boolean; created_at?: string }
export interface ScenarioSummary { scenario_key: string; label: string; pnl: number; pnl_pct: number }
export interface ScenarioDetail {
  label: string; total_before: number; total_after: number; pnl: number; pnl_pct: number; error?: string
  holdings: { fund_code: string; fund_name: string; category: string; industry: string; value_before: number; value_after: number; pnl: number; shock_pct: number }[]
}
export interface Profile {
  risk_level: number; risk_label: string; horizon_months: number; max_drawdown_tolerance: number
  liquidity_reserve: number; experience_years: number; available_cash: number | null
  excluded_industries: string[]; updated_at: string; is_stale: boolean
}
export type ProfileInput = Omit<Profile, 'risk_label' | 'updated_at' | 'is_stale'>
export interface WeeklyReport {
  summary?: string; key_points?: { title: string; desc: string }[]; next_week_focus?: string[]
  risk_alert?: string; ai_insight?: string; week_start?: string; week_end?: string; generated_at?: string
}

// ── 接口 ────────────────────────────────────────────────

export const api = {
  health: () => request<{ status: string }>('/health'),
  holdings: () => request<Holding[]>('/api/portfolio'),
  addHolding: (h: HoldingInput) => request<Holding>('/api/portfolio', json('POST', h)),
  updateHolding: (id: number, h: Partial<HoldingInput>) => request<Holding>(`/api/portfolio/${id}`, json('PUT', h)),
  removeHolding: (id: number) => request<unknown>(`/api/portfolio/${id}`, { method: 'DELETE' }),
  importFile: (kind: 'csv' | 'ocr', file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ imported_count: number }>(`/api/portfolio/import/${kind}`, { method: 'POST', body: form })
  },
  overview: () => request<Overview>('/api/analysis/overview'),
  attribution: (by: string) => request<AttributionRow[]>(`/api/analysis/attribution?by=${by}`),
  drawdown: () => request<Drawdown | DrawdownRow[]>('/api/analysis/drawdown').then(d => (Array.isArray(d) ? { funds: d } : d)),
  healthScore: () => request<Health>('/api/analysis/health'),
  correlation: () => request<Correlation>('/api/analysis/correlation'),
  suggestions: () => request<Suggestion[]>('/api/analysis/suggestions'),
  indices: () => request<IndexQuote[]>('/api/market/indices'),
  news: () => request<NewsItem[]>('/api/market/news'),
  alerts: () => request<{ alerts: AlertItem[]; threshold: number }>('/api/alerts'),
  scenarios: () => request<{ scenarios: ScenarioSummary[]; assumption?: string; message?: string }>('/api/scenario'),
  scenario: (key: string) => request<ScenarioDetail>(`/api/scenario/${key}`),
  profile: () => request<Profile | null>('/api/profile'),
  saveProfile: (p: ProfileInput) => request<Profile>('/api/profile', json('PUT', p)),
  weekly: () => request<WeeklyReport>('/api/report/weekly'),
  stockKline: (code: string, days: number) => request<{ count: number; data: NavPoint[]; price_basis?: string }>(`/api/market/stock/${code}/kline?days=${days}`),
  searchSecurities: (q: string) => request<Security[]>(`/api/securities/search?q=${encodeURIComponent(q)}`),
  watchlist: () => request<WatchItem[]>('/api/watchlist'),
  addWatch: (item: { code: string; name: string; asset_type: string; note?: string }) => request<{ id: number; already: boolean }>('/api/watchlist', json('POST', item)),
  updateWatch: (id: number, note: string) => request<unknown>(`/api/watchlist/${id}`, json('PUT', { note })),
  removeWatch: (id: number) => request<unknown>(`/api/watchlist/${id}`, { method: 'DELETE' }),
  screen: (criteria: Record<string, unknown>) => request<ScreenResult>('/api/screener', json('POST', criteria)),
  industries: () => request<{ industry: string; count: number }[]>('/api/screener/industries'),
  researchHistory: () => request<ResearchRecord[]>('/api/research/history'),
  researchDetail: (id: number) => request<ResearchDetail>(`/api/research/history/${id}`),
  checkpoints: (code = '') => request<Checkpoint[]>(`/api/checkpoints${code ? `?code=${code}` : ''}`),
  verifyCheckpoints: () => request<{ checked: number; held: number; broken: number }>('/api/checkpoints/verify', { method: 'POST' }),
  scorecard: () => request<Scorecard>('/api/checkpoints/scorecard'),
  removeCheckpoint: (id: number) => request<unknown>(`/api/checkpoints/${id}`, { method: 'DELETE' }),
  proposals: () => request<Proposal[]>('/api/proposals'),
  authorizeProposal: (id: number, shares: number, price: number | null) => request<Proposal>(`/api/proposals/${id}/authorize`, json('POST', price == null ? { shares } : { shares, price })),
  rejectProposal: (id: number, reason = '') => request<Proposal>(`/api/proposals/${id}/reject`, json('POST', { reason })),
  broker: () => request<BrokerOverview>('/api/broker'),
  brokerOrders: () => request<BrokerOrder[]>('/api/broker/orders'),
  placeOrder: (o: { code: string; name: string; side: 'buy' | 'sell'; shares: number; asset_type: string }) => request<BrokerOrder>('/api/broker/orders', json('POST', o)),
  resetBroker: () => request<BrokerOverview>('/api/broker/reset', { method: 'POST' }),
  digests: () => request<Digest[]>('/api/digest'),
  runDigest: () => request<Digest>('/api/digest/run', { method: 'POST' }),
  filing: (artCode: string, page = 1) => request<FilingText>(`/api/filings/${artCode}?page=${page}`),
  screenBacktest: (criteria: Record<string, unknown>) => request<ScreenBacktest>('/api/screener/backtest', json('POST', { criteria, top_n: 20, years: 2 })),
  valuationSeries: (code: string) => request<{ data: { date: string; pe: number | null; pb: number | null }[] }>(`/api/market/stock/${code}/valuation-history`),
  settings: () => request<AppSettings>('/api/settings'),
  saveSettings: (values: Record<string, unknown>) => request<AppSettings>('/api/settings', json('PUT', values)),
  testModel: () => request<{ ok: boolean; provider: string; model: string; error?: string; reply?: string }>('/api/settings/test', { method: 'POST' }),
  desk: () => request<Desk>('/api/desk'),
  thesis: (code: string) => request<Thesis>(`/api/research/latest?code=${code}`),
  movers: () => request<{ trade_date: string; min_mv_yi: number; gainers: Mover[]; losers: Mover[] }>('/api/market/movers'),
  memory: () => request<MemoryItem[]>('/api/memory'),
  addMemory: (content: string) => request<MemoryItem>('/api/memory', json('POST', { content })),
  removeMemory: (id: number) => request<unknown>(`/api/memory/${id}`, { method: 'DELETE' }),
  audit: () => request<{ events: AuditEntry[]; integrity: { ok: boolean; count: number; broken_at: number | null } }>('/api/audit?limit=200'),
  skills: () => request<{ skills: SkillInfo[]; invalid: { path: string; problems: string[] }[]; dirs: string[]; template: string }>('/api/skills'),
  skill: (name: string) => request<SkillInfo>(`/api/skills/${name}`),
  saveSkill: (name: string, content: string) => request<SkillInfo>(`/api/skills/${name}`, json('PUT', { content })),
  removeSkill: (name: string) => request<unknown>(`/api/skills/${name}`, { method: 'DELETE' }),
  connectors: () => request<{ config_file: string; configured: boolean; connectors: ConnectorInfo[] }>('/api/connectors'),
  testConnector: (name: string) => request<ConnectorTest>(`/api/connectors/${name}/test`, { method: 'POST' }),
  fundNav: (code: string, days: number) => request<{ count: number; data: NavPoint[] }>(`/api/market/fund/${code}/nav?days=${days}`),
  login: (username: string, password: string) =>
    request<{ access_token: string; username: string }>('/api/auth/login', json('POST', { username, password })),
  register: (username: string, password: string) =>
    request<{ access_token: string; username: string }>('/api/auth/register', json('POST', { username, password })),
}

// ── Agent 工具直调 ──────────────────────────────────────
// 功能页和 AI 研究用的是同一批工具，所以页面上的数和 AI 引用的证据一定对得上。

export interface ToolResult<T> { ok: boolean; data: T; as_of: Record<string, string | null> }
export const runTool = <T,>(name: string, inputs: Record<string, unknown> = {}) =>
  request<ToolResult<T>>(`/api/tools/${name}`, json('POST', inputs))

export interface Concentration { weights: Record<string, number>; max_weight: number; max_weight_code: string; hhi: number; effective_holdings: number; count: number }
export interface ExposureStock { stock_code: string; stock_name: string; exposure_pct: number; held_by_funds: number; via_funds: { fund_code: string; weight_pct: number }[] }
export interface Lookthrough {
  stocks: ExposureStock[]; top_exposure: ExposureStock[]; multi_fund_stocks: ExposureStock[]; multi_fund_exposure_pct: number
  covered_fund_count: number; total_fund_count: number; report_dates: Record<string, string>; coverage_by_fund: Record<string, number>; note: string; summary: string
}
export interface Overlap { fund_a: string; fund_b: string; shared_count: number; combined_weight_pct: number; report_dates: Record<string, string>
  shared_stocks: { stock_code: string; stock_name: string; weight_a: number; weight_b: number }[] }
export interface SimSide { total_value: number; weights: Record<string, number>; concentration: Concentration; weighted_max_drawdown: number | null }
export interface Simulation { before: SimSide; after: SimSide; note?: string; error?: string
  changes: { fund_code: string; before_value: number; after_value: number; delta_amount: number }[] }
export interface ConstraintCheck { passed: boolean; violations: string[]; checked: (string | Record<string, unknown>)[]; status?: string }
export interface BacktestLeg { total_return_pct: number; annualized_pct: number; max_drawdown_pct: number }
export interface Backtest {
  period: { start: string; end: string; trading_days: number }
  strategy: BacktestLeg & { trigger_count: number; deployed_pct: number; events: { date: string; action: string; nav: number; signal_date: string; drawdown_pct?: number; amount?: number }[] }
  baseline_lump_sum: BacktestLeg; baseline_dca: BacktestLeg & { installments: number }
  excess_vs_lump_sum_pct: number; excess_vs_dca_pct: number; limitations: string; error?: string
}
export interface FundInfo { code: string; name: string; nav: number; nav_date: string; estimated_change?: number; manager?: string; company?: string; scale?: string; type?: string; benchmark?: string
  return_1w?: string; return_1m?: string; return_3m?: string; return_1y?: string }
export interface NavPoint { nav_date: string; nav: number; daily_return: number; open?: number; high?: number; low?: number; volume?: number }
export interface AppSettings { values: Record<string, string | number | boolean>; secrets: Record<string, { set: boolean; hint: string }>; overridden: string[]; active_model: string; env_file: string }
export interface StockQuote { code: string; name: string; price: number; prev_close: number; open: number; high: number; low: number
  change: number; change_pct: number; amount_yi: number | null; turnover_pct: number | null; pe_ttm: number | null; pb: number | null
  total_mv_yi: number | null; quote_time: string }
export interface StockValuation { price_range_1y?: { period_high: number; period_low: number; range_position_pct: number | null; trading_days: number }; note: string }
export interface StockKline { trading_days: number; start_date: string; end_date: string; period_return_pct: number | null; period_high: number; period_low: number; range_position_pct: number | null }
export interface StockReport { report_date: string; revenue_yi: number | null; revenue_yoy_pct: number | null; net_profit_yi: number | null; net_profit_yoy_pct: number | null
  roe_pct: number | null; eps: number | null; gross_margin_pct: number | null }
export interface StockProfile { code: string; name: string; industry: string; listing_board: string; total_mv_yi: number | null }
export interface Security { code: string; name: string; asset_type: 'stock' | 'etf' | 'fund'; type_label?: string; industry?: string }
export interface WatchItem { id: number; code: string; name: string; asset_type: string; note: string; created_at: string; price: number | null; change_pct: number | null }
export interface ScreenStock { code: string; name: string; industry: string; price: number | null; change_pct: number | null; total_mv_yi: number | null
  pe_ttm: number | null; pb: number | null; roe_pct: number | null; roe_annual_pct?: number | null; revenue_yoy_pct: number | null; profit_yoy_pct: number | null }
export interface ScreenResult { criteria: Record<string, unknown>; matched: number; shown: number; stocks: ScreenStock[]; trade_date: string; report_date: string; note: string }
export interface ValuationBand { current: number | null; percentile: number | null; min?: number; median?: number; max?: number; note?: string }
export interface ValuationHistory { name: string; as_of: string; window_start: string; trading_days: number; pe: ValuationBand; pb: ValuationBand; ps: ValuationBand }
export interface Indicator { report_date: string; report_name: string; revenue_yi: number | null; revenue_yoy_pct: number | null; net_profit_yi: number | null; net_profit_yoy_pct: number | null
  deducted_net_profit_yi: number | null; roe_pct: number | null; gross_margin_pct: number | null; net_margin_pct: number | null; debt_ratio_pct: number | null; eps: number | null; operating_cashflow_per_share: number | null }
export interface Peer { code: string; name: string; pe_ttm: number | null; pb: number | null; total_mv_yi: number | null; change_pct: number | null }
export interface Peers { industry: string; as_of: string; peer_count: number; mv_rank: number | null; target: Peer | null; peers: Peer[] }
export interface PeerValuation { industry: string; as_of: string; peer_count: number; industry_median_pe: number | null; pe_rank_low_to_high: number | null; positive_pe_peer_count: number }
export interface Technicals { as_of: string; ma5: number | null; ma20: number | null; ma60: number | null; vs_ma20_pct: number | null; vs_ma60_pct: number | null; ma_alignment: string; volatility_20d_annualized_pct: number | null }
export interface Announcement { date: string; title: string; url: string; art_code: string; category: string }
export interface Dividend { report_date: string; plan: string; dividend_yield_pct: number | null; ex_dividend_date: string }
export interface Sector { industry: string; stock_count: number; median_change_pct: number; up_ratio_pct: number; leader: { code: string; name: string; change_pct: number } }
export interface SectorRanking { trade_date: string; top: Sector[]; bottom: Sector[] }
export interface MarketOverview { indices: IndexQuote[]; breadth: { trade_date: string; up: number; down: number; flat: number; median_change_pct: number; limit_up_like: number; limit_down_like: number } }
export interface ResearchRecord { id: number; created_at: string; question: string; status: string; playbook: string; intent: string; securities: Security[]; evidence_count: number }
export interface ResearchDetail { id: number; created_at: string; question: string; answer: string
  checkpoints?: Checkpoint[]; proposals?: Proposal[]
  meta: { status?: string; evidence?: { id: string; tool: string; input: unknown; output: unknown; status: string }[]; tasks?: { agent: string; goal: string }[] } }
export interface Checkpoint { id: number; message_id: number | null; question: string; playbook: string; code: string; name: string
  metric: string; metric_label: string; group: 'financial' | 'valuation' | 'market'; op: '>=' | '<='; threshold: number; statement: string
  baseline_value: number | null; baseline_as_of: string; due: string; due_date: string; status: 'pending' | 'held' | 'broken' | 'unverifiable'
  actual_value: number | null; actual_as_of: string; checked_at: string | null; created_at: string }
export interface Proposal { id: number; message_id: number | null; code: string; name: string; asset_type: string; action: string; action_label: string
  shares: number | null; price_ref: number | null; reason: string; invalidation: string; status: 'proposed' | 'executed' | 'rejected'
  exec_shares: number | null; exec_price: number | null; decided_at: string | null; created_at: string }
export interface ScoreRow { total: number; held: number; broken: number; pending: number }
export interface Scorecard extends ScoreRow { unverifiable: number; hold_rate_pct: number | null; note: string; advice_mode: boolean
  by_group: (ScoreRow & { group: string; label: string; hold_rate_pct: number | null })[]
  by_stock: (ScoreRow & { code: string; name: string })[]; recent_verified: Checkpoint[] }
export interface BrokerPosition { code: string; name: string; asset_type: string; shares: number; cost_price: number; price: number | null; market_value: number; pnl: number | null; pnl_pct: number | null }
export interface BrokerOverview { mode: 'none' | 'paper'; cash: number; initial_cash: number; market_value: number; total_assets: number; total_pnl: number; total_pnl_pct: number; positions: BrokerPosition[]; rules: string }
export interface BrokerOrder { id: number; code: string; name: string; side: 'buy' | 'sell'; shares: number; price: number | null; amount: number; fee: number; status: 'filled' | 'rejected'; reason: string; proposal_id: number | null; created_at: string }
export interface DigestEvent { kind: string; code: string; name: string; held: boolean; text: string; url?: string }
export interface Digest { id: number; day: string; summary: string; events: DigestEvent[]; created_at: string }
export interface FilingText { art_code: string; title: string; date: string; total_chars: number; page?: number; pages?: number; text: string }
export interface ReportExcerpts { title: string; date: string; category: string; art_code: string; url: string; total_chars: number; note: string; sections: { topic: string; heading: string; excerpt: string }[] }
export interface ScreenBacktest { start: string; end: string; top_n: number; total_return_pct: number; benchmark_return_pct: number; excess_return_pct: number; annualized_pct: number
  max_drawdown_pct: number; periods_beating_benchmark: number; period_count: number; benchmark: string; limitations: string[]
  periods: { start: string; end: string; picked: number; held?: number; return_pct: number | null; benchmark_pct: number | null; equity?: number; benchmark_equity?: number; top: { code: string; name: string; return_pct: number }[] }[] }
export interface DeskStock { code: string; name: string; asset_type: string; held: boolean; price: number | null; change_pct: number | null; market_value: number | null; return_pct: number | null
  pe_percentile: number | null; checkpoints: { pending: number; held: number; broken: number }; last_research: { id: number; date: string; status: string } | null; open_proposals: number }
export interface Desk { stocks: DeskStock[]; todo: { proposals: number; broken: number; pending: number; unresearched: number }; verified_recent: Checkpoint[]; digest: Digest | null }
export interface Thesis { code: string; latest: { id: number; date: string; status: string; playbook: string; conclusion: string; stance: string } | null; research_dates: string[]
  checkpoints: { total: number; pending: number; held: number; broken: number }; broken: Checkpoint[] }
export interface Mover { code: string; name: string; industry: string; price: number | null; change_pct: number; total_mv_yi: number | null }
export interface MemoryItem { id: number; kind: 'preference' | 'decision' | 'note'; code: string; content: string; source: string; created_at: string }
export interface AuditEntry { id: number; at: string; kind: string; actor: string; summary: string; payload: Record<string, unknown>; hash: string }
export interface SkillInfo { name: string; label: string; description: string; when_to_use: string; triggers: string[]; needs: string; agents: string[]; sections: string[]; criteria: string[]; path: string; content?: string }
export interface Usage { calls: number; input_tokens: number; cached_tokens: number; output_tokens: number; cache_hit_pct: number }
export interface ConnectorInfo { name: string; label: string; kind: string; transport: string; endpoint: string; enabled: boolean; description: string; auth: string }
export interface ConnectorTest { ok: boolean; error?: string; allowed_count?: number; blocked_count?: number
  tools: { name: string; description: string; allowed: boolean; reason: string }[] }

/** 取数 hook：加载中 / 出错 / 数据三态，页面不用各写一遍。 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const load = useCallback(() => {
    let alive = true
    setLoading(true)
    setError('')
    fetcher()
      .then(d => { if (alive) setData(d) })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, deps)
  useEffect(() => load(), [load])
  return { data, error, loading, reload: load }
}

// ── 对话流 ──────────────────────────────────────────────

export interface StreamEvent {
  type: string; content?: string; agent?: string; tool?: string; input?: unknown
  id?: string; goal?: string; status?: string; tools?: string[]
  playbook?: string; securities?: Security[]; items?: Checkpoint[]; proposals?: Proposal[]
  intent?: string; source?: string; success_criteria?: string[]
  tasks?: { id: string; agent: string; goal: string }[]
  evidence?: { id: string; tool: string; status: string; input: unknown; output: unknown; provenance?: { as_of?: Record<string, string | null>; sources?: { url?: string }[] } }
  gate?: string; passed?: boolean; issues?: string[]; attempt?: number
  agents?: string[]; ungrounded?: string[]; follow_ups?: string[]
  meta?: { status?: string; grounding_rate?: number; missing_evidence?: string[]; playbook?: string; usage?: Usage }
}

export async function* streamChat(
  message: string, history: { role: string; content: string }[], signal: AbortSignal, conversationId = '',
): AsyncGenerator<StreamEvent> {
  if (DEMO) {
    const { demoChat } = await import('../demo')
    yield* demoChat(message, signal)
    return
  }
  const resp = await fetch(`${API_BASE}/api/chat`, { ...json('POST', { message, history, conversation_id: conversationId || undefined }), headers: { 'Content-Type': 'application/json', ...authHeaders() }, signal })
  if (!resp.ok || !resp.body) throw new ApiError(`对话请求失败（${resp.status}）`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let cut: number
    while ((cut = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      if (chunk.startsWith('data: ')) yield JSON.parse(chunk.slice(6))
    }
  }
}
