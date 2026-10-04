import type React from 'react'
import { useState } from 'react'
import { Sparkles, Star } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { DEMO, api, useApi, type ScreenResult } from '../api'
import { research } from '../api/researchStore'
import { DEMO_DEFAULTS } from '../demo/defaults'
import { Button, Callout, Input, Select } from '../components/kit'
import { DataState, Page, Section, Table, Td, signClass, signed } from '../components/ui'

// 字段名与后端 screener.screen 的条件一致；Agent 的 screen_stocks 工具用的也是这一套
const FIELDS = [
  ['mv_min_yi', '总市值 ≥（亿元）'], ['mv_max_yi', '总市值 ≤（亿元）'], ['pe_max', 'PE（TTM）≤'], ['pb_max', 'PB ≤'],
  ['roe_min', 'ROE ≥（%）'], ['revenue_yoy_min', '营收同比 ≥（%）'], ['profit_yoy_min', '净利同比 ≥（%）'], ['change_min', '当日涨跌 ≥（%）'],
] as const
const SORTS = [['total_mv_yi', '总市值'], ['pe_ttm', 'PE'], ['pb', 'PB'], ['roe_pct', 'ROE'], ['revenue_yoy_pct', '营收同比'], ['profit_yoy_pct', '净利同比'], ['change_pct', '当日涨跌']] as const
const LABEL: Record<string, string> = { ...Object.fromEntries(FIELDS.map(([k, l]) => [k, l.replace(/（.*）/, '')])), industry: '行业', exclude_st: '剔除 ST' }
const PRESETS: { label: string; form: Record<string, string> }[] = [
  { label: '低估值高 ROE', form: { pe_max: '15', roe_min: '15', mv_min_yi: '200' } },
  { label: '大市值稳增长', form: { mv_min_yi: '1000', revenue_yoy_min: '10', profit_yoy_min: '10' } },
  { label: '高增长', form: { revenue_yoy_min: '30', profit_yoy_min: '30', mv_min_yi: '100' } },
]
const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toFixed(digits))

type Form = Record<string, string>
const toCriteria = (form: Form) => {
  const out: Record<string, unknown> = { limit: 50, sort_by: form.sort_by || 'total_mv_yi', descending: form.descending !== 'asc' }
  if (form.industry) out.industry = form.industry
  for (const [key] of FIELDS) if (form[key]?.trim() && !Number.isNaN(Number(form[key]))) out[key] = Number(form[key])
  return out
}

/** 选股器：条件由人填，结果由代码按全市场快照筛出来；AI 只负责解读选中的几只。 */
const ScreenerPage: React.FC = () => {
  const navigate = useNavigate()
  const industries = useApi(api.industries)
  const [form, setForm] = useState<Form>(DEMO ? DEMO_DEFAULTS.screen : {})
  const [state, setState] = useState<{ loading: boolean; error: string; result: ScreenResult | null }>({ loading: false, error: '', result: null })
  const [picked, setPicked] = useState<string[]>([])
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)

  const run = async (next: Form = form) => {
    setState((s) => ({ ...s, loading: true, error: '' }))
    setPicked([])
    setMessage(null)
    try {
      setState({ loading: false, error: '', result: await api.screen(toCriteria(next)) })
    } catch (e) {
      setState({ loading: false, error: e instanceof Error ? e.message : '筛选失败', result: null })
    }
  }
  const set = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }))
  const toggle = (code: string) => setPicked((p) => (p.includes(code) ? p.filter((c) => c !== code) : [...p, code]))

  const r = state.result
  const chosen = r?.stocks.filter((s) => picked.includes(s.code)) ?? []
  const askAi = () => {
    const names = chosen.slice(0, 3).map((s) => `${s.name}（${s.code}）`)
    void research.ask(names.length === 1 ? `帮我深度分析一下${names[0]}` : `对比一下${names.join('、')}的基本面和估值`)
    navigate('/research')
  }
  const addWatch = async () => {
    try {
      const done = await Promise.all(chosen.map((s) => api.addWatch({ code: s.code, name: s.name, asset_type: 'stock' })))
      const added = done.filter((d) => !d.already).length
      setMessage({ tone: 'success', text: `已加入自选 ${added} 只${done.length - added ? `，${done.length - added} 只原本就在` : ''}` })
      setPicked([])
    } catch (e) {
      setMessage({ tone: 'danger', text: e instanceof Error ? e.message : '加自选失败' })
    }
  }

  return (
    <Page title="选股器" description="按估值、盈利和增长条件筛选全部 A 股；结果是代码算出来的，不是模型挑的">
      <form onSubmit={(e) => { e.preventDefault(); void run() }} className="flex flex-col gap-4">
        {DEMO ? null : (
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-steel">
            <span>常用条件</span>
            {PRESETS.map((p) => <Button key={p.label} size="xs" variant="secondary" onClick={() => { setForm(p.form); void run(p.form) }}>{p.label}</Button>)}
            <Button size="xs" variant="ghost" onClick={() => setForm({})}>清空</Button>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Select id="sc-ind" label="行业" value={form.industry ?? ''} onChange={(v) => set('industry', v)}
            options={[{ value: '', label: '全部行业' }, ...(industries.data ?? []).map((i) => ({ value: i.industry, label: `${i.industry}（${i.count}）` }))]} />
          {FIELDS.map(([key, label]) => (
            <Input key={key} id={`sc-${key}`} label={label} type="number" step="any" placeholder="不限" value={form[key] ?? ''} onChange={(e) => set(key, e.target.value)} />
          ))}
          <Select id="sc-sort" label="排序" value={form.sort_by ?? 'total_mv_yi'} onChange={(v) => set('sort_by', v)} options={SORTS.map(([value, label]) => ({ value, label }))} />
          <Select id="sc-dir" label="方向" value={form.descending ?? 'desc'} onChange={(v) => set('descending', v)} options={[{ value: 'desc', label: '从高到低' }, { value: 'asc', label: '从低到高' }]} />
        </div>
        <div><Button type="submit" loading={state.loading}>筛选</Button></div>
      </form>

      {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

      <Section title="筛选结果"
        hint={r ? `符合 ${r.matched} 只，显示前 ${r.shown} 只 · 行情 ${r.trade_date} · 业绩 ${r.report_date}` : undefined}
        actions={chosen.length ? (
          <>
            <span className="text-[13px] text-steel">已选 {chosen.length} 只</span>
            <Button size="sm" variant="secondary" disabled={DEMO} onClick={() => void addWatch()}><Star className="h-3.5 w-3.5" />加自选</Button>
            <Button size="sm" disabled={research.busy || DEMO} onClick={askAi}><Sparkles className="h-3.5 w-3.5" />{chosen.length === 1 ? '深度研究' : chosen.length > 3 ? '对比前 3 只' : '交给 AI 对比'}</Button>
          </>
        ) : undefined}>
        <DataState loading={state.loading} error={state.error} onRetry={() => void run()}
          empty={!r ? '填好条件后点「筛选」。留空的条件不参与筛选。' : r.matched === 0 ? '没有符合条件的股票，放宽一些条件再试。' : undefined}>
          {r ? (
            <>
              <p className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-slate">
                <span className="text-steel">实际生效的条件</span>
                {Object.entries(r.criteria).map(([k, v]) => <span key={k}>{LABEL[k] ?? k}{v === true ? '' : ` ${String(v)}`}</span>)}
              </p>
              <Table minWidth={980} head={[{ label: '' }, { label: '公司' }, { label: '行业' }, { label: '总市值（亿元）', right: true }, { label: 'PE', right: true }, { label: 'PB', right: true },
                { label: 'ROE', right: true }, { label: '营收同比', right: true }, { label: '净利同比', right: true }, { label: '最新价', right: true }, { label: '涨跌', right: true }]}>
                {r.stocks.map((s) => (
                  <tr key={s.code}>
                    <Td className="w-8"><input type="checkbox" aria-label={`选择 ${s.name}`} checked={picked.includes(s.code)} onChange={() => toggle(s.code)} className="h-4 w-4 accent-[var(--primary)]" /></Td>
                    <Td><Link to={`/stock/${s.code}`} className="font-medium text-ink hover:underline">{s.name}</Link><span className="ml-2 font-mono text-xs text-stone">{s.code}</span></Td>
                    <Td className="text-steel">{s.industry || '—'}</Td>
                    <Td right num>{num(s.total_mv_yi, 0)}</Td>
                    <Td right num>{num(s.pe_ttm)}</Td>
                    <Td right num>{num(s.pb)}</Td>
                    <Td right num>{s.roe_pct == null ? '—' : `${s.roe_pct}%`}</Td>
                    <Td right num className={signClass(s.revenue_yoy_pct)}>{signed(s.revenue_yoy_pct, 2, '%')}</Td>
                    <Td right num className={signClass(s.profit_yoy_pct)}>{signed(s.profit_yoy_pct, 2, '%')}</Td>
                    <Td right num>{num(s.price)}</Td>
                    <Td right num className={signClass(s.change_pct)}>{signed(s.change_pct, 2, '%')}</Td>
                  </tr>
                ))}
              </Table>
              <p className="mt-3 text-[13px] text-steel">{r.note}。筛选只是按数字过滤，不代表推荐；默认剔除 ST 与退市整理股。</p>
            </>
          ) : null}
        </DataState>
      </Section>
    </Page>
  )
}

export default ScreenerPage
