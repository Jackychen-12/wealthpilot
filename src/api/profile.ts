import { apiFetch, apiPut } from './client'

export interface InvestorProfile {
  risk_level: number
  risk_label: string
  horizon_months: number
  max_drawdown_tolerance: number
  liquidity_reserve: number
  experience_years: number
  excluded_industries: string[]
  raw_score: number
  updated_at: string
  is_stale: boolean
}

export interface ProfileUpsert {
  risk_level: number
  horizon_months: number
  max_drawdown_tolerance: number
  liquidity_reserve?: number
  experience_years?: number
  excluded_industries?: string[]
  raw_score?: number
}

export function getProfile(): Promise<InvestorProfile | null> {
  return apiFetch<InvestorProfile | null>('/api/profile', null)
}

export function saveProfile(payload: ProfileUpsert): Promise<InvestorProfile | null> {
  return apiPut<ProfileUpsert, InvestorProfile>('/api/profile', payload)
}

/**
 * 把问卷答案映射成画像字段。
 *
 * 刻意不从总分反推每个字段 —— 最大回撤容忍度、投资期限、投资经验分别对应
 * 具体的题目，直接取那道题的答案比用总分估计准确得多。
 *
 * 题目顺序：0 投资经验 / 1 下跌反应 / 2 收益目标 / 3 最大亏损 / 4 投资时长
 */
export function answersToProfile(answers: number[], totalScore: number): ProfileUpsert {
  const experience = answers[0]
  const maxLoss = answers[3]
  const horizon = answers[4]

  const experienceYears = [0.5, 2, 4, 8][experience] ?? 1
  const drawdownTolerance = [0.02, 0.05, 0.15, 0.3][maxLoss] ?? 0.15
  const horizonMonths = [1, 12, 36, 60][horizon] ?? 12

  // 5-8 保守 / 9-12 稳健 / 13-16 积极 / 17-20 激进
  const riskLevel = totalScore <= 8 ? 1 : totalScore <= 12 ? 2 : totalScore <= 16 ? 3 : 4

  return {
    risk_level: riskLevel,
    horizon_months: horizonMonths,
    max_drawdown_tolerance: drawdownTolerance,
    experience_years: experienceYears,
    raw_score: totalScore,
  }
}
