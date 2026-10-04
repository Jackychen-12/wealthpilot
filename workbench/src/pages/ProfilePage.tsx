import type React from 'react'
import { useEffect, useState } from 'react'
import { api, useApi, type ProfileInput } from '../api'
import { Button, Callout, Input, Select } from '../components/kit'
import { DataState, Page, Section } from '../components/ui'

const LEVELS = ['保守型', '稳健型', '积极型', '激进型', '极进取型']
const blank: ProfileInput = {
  risk_level: 2, horizon_months: 36, max_drawdown_tolerance: 0.15, liquidity_reserve: 0,
  experience_years: 1, available_cash: null, excluded_industries: [],
}

const ProfilePage: React.FC = () => {
  const profile = useApi(api.profile)
  const [form, setForm] = useState<ProfileInput>(blank)
  const [excluded, setExcluded] = useState('')
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const p = profile.data

  useEffect(() => {
    if (!p) return
    setForm({ risk_level: p.risk_level, horizon_months: p.horizon_months, max_drawdown_tolerance: p.max_drawdown_tolerance,
      liquidity_reserve: p.liquidity_reserve, experience_years: p.experience_years, available_cash: p.available_cash, excluded_industries: p.excluded_industries })
    setExcluded(p.excluded_industries.join('、'))
  }, [p])

  const set = <K extends keyof ProfileInput>(k: K, v: ProfileInput[K]) => setForm((f) => ({ ...f, [k]: v }))

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      await api.saveProfile({ ...form, excluded_industries: excluded.split(/[,，、\s]+/).filter(Boolean) })
      setMessage({ tone: 'success', text: '已保存。之后 AI 给出的仓位建议都会按这份画像校验。' })
      profile.reload()
    } catch (err) {
      setMessage({ tone: 'danger', text: err instanceof Error ? err.message : '保存失败' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Page title="风险画像" description="AI 给出任何仓位建议前都会逐条核对的硬约束">
      <DataState loading={profile.loading} error={profile.error} onRetry={profile.reload}>
        {p ? (
          <Callout tone={p.is_stale ? 'warning' : 'neutral'}>
            当前画像：{p.risk_label}，最大回撤容忍 {(p.max_drawdown_tolerance * 100).toFixed(0)}%，更新于 {p.updated_at.slice(0, 10)}{p.is_stale ? '。已超过 180 天，建议复评' : ''}
          </Callout>
        ) : (
          <Callout tone="warning" title="还没有风险画像">没有画像时，AI 不会给出具体的仓位比例、加减仓数量或止损价位。</Callout>
        )}
        {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

        <Section title="画像设置">
          <form onSubmit={(e) => void save(e)} className="max-w-[720px]">
            <div className="grid gap-4 sm:grid-cols-2">
              <Select id="p-level" label="风险等级" value={String(form.risk_level)} onChange={(v) => set('risk_level', Number(v))}
                options={LEVELS.map((l, i) => ({ value: String(i + 1), label: `${i + 1} · ${l}` }))} />
              <Input id="p-dd" label="最大回撤容忍度（%）" hint="组合从高点最多能接受跌多少" type="number" min="1" max="100" step="1"
                value={Math.round(form.max_drawdown_tolerance * 100)} onChange={(e) => set('max_drawdown_tolerance', Number(e.target.value) / 100)} required />
              <Input id="p-horizon" label="投资期限（月）" type="number" min="0" value={form.horizon_months} onChange={(e) => set('horizon_months', Number(e.target.value))} required />
              <Input id="p-exp" label="投资经验（年）" type="number" min="0" step="0.5" value={form.experience_years} onChange={(e) => set('experience_years', Number(e.target.value))} />
              <Input id="p-reserve" label="半年内要用的钱（元）" hint="这部分资金不会被建议占用" type="number" min="0" value={form.liquidity_reserve} onChange={(e) => set('liquidity_reserve', Number(e.target.value))} />
              <Input id="p-cash" label="可用现金（元）" hint="可留空" type="number" min="0" value={form.available_cash ?? ''} onChange={(e) => set('available_cash', e.target.value === '' ? null : Number(e.target.value))} />
              <div className="sm:col-span-2">
                <Input id="p-excluded" label="不接受的行业" hint="用顿号或逗号分隔" placeholder="如 白酒、房地产" value={excluded} onChange={(e) => setExcluded(e.target.value)} />
              </div>
            </div>
            <Button type="submit" className="mt-6" loading={busy}>保存画像</Button>
          </form>
        </Section>
      </DataState>
    </Page>
  )
}

export default ProfilePage
