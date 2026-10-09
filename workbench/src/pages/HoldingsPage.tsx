import type React from 'react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ClipboardPaste, ImageUp, Plus, Upload } from 'lucide-react'
import { api, runTool, useApi, type Holding, type HoldingInput, type ParsedHolding, type StockProfile } from '../api'
import { Donut, PnlBars } from '../components/charts'
import { securityPath } from '../components/SecuritySearch'
import { Button, Callout, ConfirmDialog, Drawer, Input, Segmented, Select, Tag } from '../components/kit'
import OverviewPage from './OverviewPage'
import { ASSET, CATEGORY, DataState, Metric, Metrics, Page, Section, Table, Td, signClass, signed, yuan } from '../components/ui'

const blank = (): HoldingInput => ({
  asset_type: 'stock', fund_code: '', fund_name: '', shares: 0, cost_price: 0,
  buy_date: new Date().toISOString().slice(0, 10), category: 'equity', industry: '',
})
// 股票在前，基金作为持仓的一种排在后面
const GROUP_ORDER = ['stock', 'etf', 'fund', 'crypto']
const groupSum = (rows: Holding[], key: (h: Holding) => string) => {
  const sums = new Map<string, number>()
  for (const h of rows) sums.set(key(h), (sums.get(key(h)) ?? 0) + (h.market_value ?? 0))
  return [...sums].map(([name, value]) => ({ name, value })).filter((d) => d.value > 0)
}
const options = (map: Record<string, string>) => Object.entries(map).map(([value, label]) => ({ value, label }))

const TABS = [['list', '明细'], ['analysis', '收益与归因']] as const
const SIGN: Record<string, string> = { HKD: 'HK$', USD: 'US$', CNY: '¥' }
const foreign = (h: Holding) => !!h.currency && h.currency !== 'CNY'
const overseasUnit = (code: string) => (/\.HK$|^hk\d/i.test(code) ? '港元' : /\.US$/i.test(code) ? '美元' : '')

/**
 * 粘贴导入：把券商 App 里的持仓照着敲几行（或直接复制过来），先解析成预览，
 * 每一行认成了哪只股票、多少股、成本多少都给用户看过，确认后才写入。
 */
const PasteImport: React.FC<{ open: boolean; onClose: () => void; onDone: (text: string) => void }> = ({ open, onClose, onDone }) => {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<ParsedHolding[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const good = (rows ?? []).filter((r) => r.ok)
  const act = async (work: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : '操作失败') } finally { setBusy(false) }
  }
  const parse = () => act(async () => setRows((await api.parseHoldings(text)).rows))
  const confirm = () => act(async () => {
    const res = await api.addHoldings(good)
    setText(''); setRows(null)
    onDone(`已添加 ${res.added} 条持仓${res.skipped.length ? `；跳过：${res.skipped.join('；')}` : ''}`)
  })
  return (
    <Drawer open={open} onClose={onClose} title="粘贴导入持仓" width="max-w-xl">
      <div className="flex flex-col gap-3">
        <p className="text-[13px] leading-relaxed text-steel">一行一只：名称或代码、数量、成本价，中间用空格或逗号隔开。写“2手”会按 200 股算。</p>
        <textarea value={text} onChange={(e) => { setText(e.target.value); setRows(null) }} rows={6} aria-label="持仓文本"
          placeholder={'贵州茅台 100 1500\n600036 2000 35.2\n宁德时代 2手 262'}
          className="w-full resize-y rounded-md border border-hairline bg-canvas px-3 py-2 font-mono text-[13px] leading-relaxed text-ink outline-none placeholder:text-stone focus:border-primary focus:ring-1 focus:ring-primary" />
        {error ? <Callout tone="danger">{error}</Callout> : null}
        {rows == null ? (
          <div><Button size="sm" loading={busy} disabled={!text.trim()} onClick={() => void parse()}>识别</Button></div>
        ) : (
          <>
            <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline text-sm">
              {rows.map((r, i) => (
                <li key={i} className="flex items-baseline gap-3 px-3 py-2">
                  {r.ok ? (
                    <>
                      <span className="min-w-0 flex-1 truncate text-ink">{r.name}<span className="ml-2 font-mono text-xs text-stone">{r.code}</span>
                        {r.asset_type !== 'stock' ? <Tag className="ml-2 !py-0">{ASSET[r.asset_type] ?? r.asset_type}</Tag> : null}</span>
                      <span className="shrink-0 tabular-nums text-charcoal">{r.shares?.toLocaleString()} 股</span>
                      <span className="w-24 shrink-0 text-right tabular-nums text-charcoal">成本 {r.cost}</span>
                      {r.note ? <span className="basis-full text-xs text-steel">{r.note}</span> : null}
                    </>
                  ) : (
                    <>
                      <span className="min-w-0 flex-1 truncate font-mono text-[13px] text-steel">{r.line}</span>
                      <span className="shrink-0 text-[13px] text-on-rose">{r.problem}</span>
                    </>
                  )}
                </li>
              ))}
            </ul>
            <p className="text-[13px] text-steel">
              {good.length ? `认出 ${good.length} 条` : '一条也没认出来'}{rows.length > good.length ? `，${rows.length - good.length} 条有问题（改一下上面的文字再识别，或者先导入认出来的）` : ''}。已经在持仓里的代码不会被改动。
            </p>
            <div className="flex gap-2">
              <Button size="sm" loading={busy} disabled={!good.length} onClick={() => void confirm()}>导入这 {good.length} 条</Button>
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => void parse()}>重新识别</Button>
            </div>
          </>
        )}
      </div>
    </Drawer>
  )
}

const HoldingsPage: React.FC<{ initialTab?: string }> = ({ initialTab = 'list' }) => {
  const [tab, setTab] = useState(initialTab)
  const holdings = useApi(api.holdings)
  const [editing, setEditing] = useState<{ id: number | null; form: HoldingInput } | null>(null)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<Holding | null>(null)
  const csvRef = useRef<HTMLInputElement>(null)
  const ocrRef = useRef<HTMLInputElement>(null)
  const [params, setParams] = useSearchParams()
  const [pasting, setPasting] = useState(false)
  // 从首页的引导点过来（/holdings?import=1）：直接打开粘贴导入
  useEffect(() => {
    if (params.get('import')) { setPasting(true); setParams({}, { replace: true }) }
  }, [params, setParams])

  const rows = holdings.data ?? []
  const total = rows.reduce((s, h) => s + (h.market_value ?? 0), 0)
  const cost = rows.reduce((s, h) => s + h.shares * h.cost_price, 0)
  const totalReturn = rows.reduce((s, h) => s + (h.total_return ?? 0), 0)
  const groups = [...GROUP_ORDER, ...new Set(rows.map((h) => h.asset_type).filter((t) => !GROUP_ORDER.includes(t)))]
    .map((type) => ({ type, items: rows.filter((h) => h.asset_type === type).sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0)) }))
    .filter((g) => g.items.length > 0)

  const run = async (work: () => Promise<string>) => {
    setBusy(true)
    setMessage(null)
    try {
      setMessage({ tone: 'success', text: await work() })
      holdings.reload()
    } catch (e) {
      setMessage({ tone: 'danger', text: e instanceof Error ? e.message : '操作失败' })
    } finally {
      setBusy(false)
    }
  }

  const save = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editing) return
    const { id, form } = editing
    void run(async () => {
      if (id == null) await api.addHolding(form)
      else await api.updateHolding(id, form)
      setEditing(null)
      return id == null ? `已添加 ${form.fund_name}` : `已更新 ${form.fund_name}`
    })
  }
  // 录入股票 / ETF 时，按代码带出名称和行业，省得手填
  const autofill = async () => {
    const form = editing?.form
    if (!form || form.asset_type === 'fund' || form.asset_type === 'crypto' || !form.fund_code || form.fund_name) return
    try {
      const res = await runTool<StockProfile | string>('get_stock_profile', { code: form.fund_code })
      if (typeof res.data === 'string') return
      const profile = res.data
      setEditing((ed) => (ed && !ed.form.fund_name ? { ...ed, form: { ...ed.form, fund_name: profile.name, industry: ed.form.industry || profile.industry } } : ed))
    } catch { /* 带不出来就让用户手填 */ }
  }
  const importFile = (kind: 'csv' | 'ocr', file: File | undefined) => {
    if (file) void run(async () => `已导入 ${(await api.importFile(kind, file)).imported_count} 条持仓`)
  }
  const set = <K extends keyof HoldingInput>(key: K, value: HoldingInput[K]) =>
    setEditing((ed) => (ed ? { ...ed, form: { ...ed.form, [key]: value } } : ed))

  return (
    <Page title="持仓" description="股票、ETF 和基金放在一起：明细、分布、收益与归因" terms={['收益归因', '集中度', '市值']}
      actions={(
        <>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => setPasting(true)}><ClipboardPaste className="h-4 w-4" />粘贴导入</Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => csvRef.current?.click()}><Upload className="h-4 w-4" />导入 CSV / Excel</Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => ocrRef.current?.click()}><ImageUp className="h-4 w-4" />截图识别</Button>
          <Button size="sm" onClick={() => setEditing({ id: null, form: blank() })}><Plus className="h-4 w-4" />添加持仓</Button>
          <input ref={csvRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={(e) => { importFile('csv', e.target.files?.[0]); e.target.value = '' }} />
          <input ref={ocrRef} type="file" accept="image/*" hidden onChange={(e) => { importFile('ocr', e.target.files?.[0]); e.target.value = '' }} />
        </>
      )}>
      {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}
      <PasteImport open={pasting} onClose={() => setPasting(false)}
        onDone={(text) => { setPasting(false); setMessage({ tone: 'success', text }); holdings.reload() }} />

      {rows.length > 0 ? (
        <Metrics>
          <Metric label="持仓数" value={rows.length} />
          <Metric label="总市值（元）" value={yuan(total)} />
          <Metric label="总成本（元）" value={yuan(cost)} />
          <Metric label="累计收益（元）" value={signed(totalReturn, 0)} tone={signClass(totalReturn)} hint={cost ? signed((totalReturn / cost) * 100, 2, '%') : undefined} />
        </Metrics>
      ) : null}

      {rows.length > 0 ? <div className="border-b border-hairline"><Segmented value={tab} onChange={setTab} options={TABS} /></div> : null}
      {tab === 'analysis' ? <OverviewPage embedded /> : null}

      {tab === 'list' && rows.length > 1 ? (
        <Section title="分布与盈亏" hint="按市值">
          <div className="flex flex-col gap-3 lg:flex-row">
            <Donut title="按资产类型" data={groupSum(rows, (h) => ASSET[h.asset_type] ?? h.asset_type)} />
            <Donut title="按行业" data={groupSum(rows, (h) => h.industry || (h.asset_type === 'fund' ? '基金（未分类）' : '未分类'))} />
          </div>
          <div className="mt-3"><PnlBars data={[...rows].filter((h) => h.total_return != null).sort((a, b) => (b.total_return ?? 0) - (a.total_return ?? 0)).map((h) => ({ name: h.fund_name.slice(0, 8), value: h.total_return ?? 0 }))} /></div>
        </Section>
      ) : null}

      {tab === 'list' ? (
      <Section title="持仓明细" hint={`最新价来自实时行情；取不到时按成本价计${rows.some(foreign) ? '。港股美股按人民币记账：小字是原币种的数和折算用的汇率（人民币汇率中间价）' : ''}`}>
        <DataState loading={holdings.loading} error={holdings.error} onRetry={holdings.reload}
          empty={rows.length === 0 ? '还没有持仓。点右上角「添加持仓」录入股票、ETF 或基金，或导入天天基金导出的 CSV。' : undefined}>
          <Table minWidth={980} head={[
            { label: '标的' }, { label: '类别' }, { label: '份额', right: true }, { label: '成本价', right: true }, { label: '最新价', right: true },
            { label: '市值', right: true }, { label: '占比', right: true }, { label: '持有收益', right: true }, { label: '收益率', right: true }, { label: '', right: true },
          ]}>
            {groups.map((g) => {
              const value = g.items.reduce((sum, h) => sum + (h.market_value ?? 0), 0)
              return (
              <Fragment key={g.type}>
              <tr className="bg-surface-soft">
                <Td colSpan={10} className="!py-1.5 text-[13px] text-steel">
                  <b className="font-medium text-ink">{ASSET[g.type] ?? g.type}</b> · {g.items.length} 项 · 市值 {yuan(value)} 元{total ? ` · 占 ${((value / total) * 100).toFixed(1)}%` : ''}
                </Td>
              </tr>
              {g.items.map((h) => (
              <tr key={h.id}>
                <Td><Link to={securityPath({ code: h.fund_code, asset_type: h.asset_type })} className="font-medium text-ink hover:underline">{h.fund_name}</Link><div className="font-mono text-xs text-stone">{h.fund_code} · {h.buy_date}</div></Td>
                <Td>{CATEGORY[h.category] ?? h.category}{h.industry ? <div className="text-xs text-steel">{h.industry}</div> : null}</Td>
                <Td right num>{yuan(h.shares, 2)}</Td>
                <Td right num>{h.cost_price.toFixed(4)}{foreign(h) && h.cost_native != null ? <div className="text-xs text-steel">{SIGN[h.currency!]}{h.cost_native} × {h.cost_fx}</div> : null}</Td>
                <Td right num>{h.latest_nav == null ? '—' : h.latest_nav.toFixed(4)}{foreign(h) && h.native_price != null ? <div className="text-xs text-steel">{SIGN[h.currency!]}{h.native_price} × {h.fx_rate}</div> : null}</Td>
                <Td right num>{yuan(h.market_value)}</Td>
                <Td right num>{total && h.market_value != null ? `${((h.market_value / total) * 100).toFixed(1)}%` : '—'}</Td>
                <Td right num className={signClass(h.total_return)}>{signed(h.total_return, 0)}</Td>
                <Td right num className={signClass(h.return_pct)}>{signed(h.return_pct, 2, '%')}</Td>
                <Td right className="whitespace-nowrap">
                  <Button size="xs" variant="ghost" onClick={() => setEditing({ id: h.id, form: { asset_type: h.asset_type, fund_code: h.fund_code, fund_name: h.fund_name, shares: h.shares, cost_price: foreign(h) && h.cost_native != null ? h.cost_native : h.cost_price, buy_date: h.buy_date, category: h.category, industry: h.industry } })}>修改</Button>
                  <Button size="xs" variant="danger" onClick={() => setRemoving(h)}>删除</Button>
                </Td>
              </tr>
              ))}
              </Fragment>
              )
            })}
          </Table>
        </DataState>
        <p className="mt-3 text-[13px] text-steel">截图识别使用 Claude Vision，需要后端配置 Anthropic Key；CSV 支持天天基金导出格式。</p>
      </Section>
      ) : null}

      <Drawer open={editing != null} onClose={() => setEditing(null)} title={editing?.id == null ? '添加持仓' : '修改持仓'} width="max-w-md">
        {editing ? (
          <form className="flex flex-col gap-4" onSubmit={save}>
            <Select id="h-type" label="资产类型" value={editing.form.asset_type} onChange={(v) => set('asset_type', v)} options={options(ASSET)} />
            <Input id="h-code" label="代码" placeholder={editing.form.asset_type === 'fund' ? '如 110011' : '如 600519；港股 00700.HK，美股 AAPL.US'} hint={editing.form.asset_type === 'stock' || editing.form.asset_type === 'etf' ? '填完代码后会自动带出名称和行业' : undefined}
              value={editing.form.fund_code} onChange={(e) => set('fund_code', e.target.value.trim())} onBlur={() => void autofill()} required />
            <Input id="h-name" label="名称" value={editing.form.fund_name} onChange={(e) => set('fund_name', e.target.value)} required />
            <div className="grid grid-cols-2 gap-3">
              <Input id="h-shares" label="持有份额" type="number" step="any" min="0" value={editing.form.shares || ''} onChange={(e) => set('shares', Number(e.target.value))} required />
              <Input id="h-cost" label={`成本价${overseasUnit(editing.form.fund_code) ? `（${overseasUnit(editing.form.fund_code)}）` : ''}`} type="number" step="any" min="0" value={editing.form.cost_price || ''} onChange={(e) => set('cost_price', Number(e.target.value))} required />
            </div>
            {overseasUnit(editing.form.fund_code) ? <p className="-mt-2 text-[13px] leading-relaxed text-steel">成本价照券商里看到的{overseasUnit(editing.form.fund_code)}数填。持仓的账是人民币的：成本按买入日的人民币汇率中间价折算，现价按今天的折算，所以盈亏里包含汇率的涨跌。</p> : null}
            <Input id="h-date" label="买入日期" type="date" value={editing.form.buy_date} onChange={(e) => set('buy_date', e.target.value)} required />
            <Select id="h-cat" label="类别" value={editing.form.category} onChange={(v) => set('category', v)} options={options(CATEGORY)} />
            <Input id="h-ind" label="行业标签" hint="用于按行业归因和行业排除校验，可留空" placeholder="如 科技、消费" value={editing.form.industry} onChange={(e) => set('industry', e.target.value)} />
            <div className="flex gap-2 pt-1">
              <Button type="submit" loading={busy}>保存</Button>
              <Button variant="ghost" onClick={() => setEditing(null)}>取消</Button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <ConfirmDialog open={removing != null} title="删除持仓" confirmText="删除"
        message={removing ? `确定删除「${removing.fund_name}」吗？删除后无法恢复。` : ''}
        onCancel={() => setRemoving(null)}
        onConfirm={() => {
          const target = removing
          setRemoving(null)
          if (target) void run(async () => { await api.removeHolding(target.id); return `已删除 ${target.fund_name}` })
        }} />
    </Page>
  )
}

export default HoldingsPage
