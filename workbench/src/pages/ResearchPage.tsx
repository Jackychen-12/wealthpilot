import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Check, ChevronRight, ListTree, Square, SquarePen } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DEMO, api, runTool, useApi, type Depth, type ValuationHistory } from '../api'
import { askNotifyPermission, research, useResearch, type Evidence, type Turn } from '../api/researchStore'
import demoFixtures from '../demo/questions'
import { AnswerMarkdown } from '../components/AnswerMarkdown'
import { Sparkline } from '../components/charts'
import { CheckpointTable, ProposalList } from '../components/Checkpoints'
import { securityPath } from '../components/SecuritySearch'
import { Button, Callout, Dot, Drawer, Tag, type Tone } from '../components/kit'
import { cn } from '../utils/cn'

const AGENT: Record<string, { label: string; tone: Tone }> = {
  fundamental: { label: '基本面', tone: 'blue' },
  valuation: { label: '估值', tone: 'purple' },
  price: { label: '走势', tone: 'pink' },
  industry: { label: '行业与市场', tone: 'yellow' },
  screener: { label: '选股', tone: 'orange' },
  portfolio: { label: '组合与风险', tone: 'green' },
  fund: { label: '基金', tone: 'gray' },
  review: { label: '复盘', tone: 'green' },
}
export const PLAYBOOK: Record<string, string> = { stock_deep: '个股深度研究', stock_compare: '个股对比', holding_review: '持仓诊断', screen: '选股', review: '事后复盘', quick: '快速回答', rewrite: '基于已有证据改写' }
export const STATUS: Record<string, { tone: Tone; label: string }> = {
  passed: { tone: 'green', label: '已通过校验' },
  partial: { tone: 'yellow', label: '部分证据缺失' },
  rejected: { tone: 'pink', label: '未通过校验 · 未发布' },
  insufficient_data: { tone: 'pink', label: '证据不足 · 未发布' },
  failed: { tone: 'pink', label: '执行失败' },
  stopped: { tone: 'gray', label: '已停止' },
}
// 起始页只给四个最常用的问法；其余能力直接问就行，不需要先学有哪些"模板"
const EXAMPLES = [
  { label: '研究一只股票', q: '帮我深度分析一下贵州茅台' },
  { label: '对比几只股票', q: '对比一下贵州茅台和五粮液的基本面和估值' },
  { label: '看看我的持仓', q: '帮我诊断一下我的持仓' },
  { label: '按条件选股', q: '帮我筛选市盈率低于15、ROE高于15%的大市值股票' },
]
const MORE_EXAMPLES = ['复盘一下之前的研究：验证点成立了多少，哪些判断被证伪了', '今天哪些行业领涨，大盘情绪如何', '宁德时代最近一期财报里管理层怎么解释业绩变化', '低市盈率高 ROE 这个选股条件过去两年表现如何']
const PROCESS_KEY = 'wp_show_process'
const DEPTH_KEY = 'wp_depth'
const REPORT_KEY = 'wp_report_open'
const DEPTHS: { key: Depth; label: string; hint: string }[] = [
  { key: 'auto', label: '自动', hint: '按问题决定查多深' },
  { key: 'quick', label: '快速', hint: '十几秒给个简短回答，不留验证点' },
  { key: 'deep', label: '深入', hint: '完整研究：四个维度取证、逐条校验，约一分钟' },
]
// 改写不重新取数：只用这一轮已经拿到的证据换个写法，几秒钟
const REWRITES = ['更短一点', '只讲风险', '换成给新手的说法', '列成要点']
// 和个股页的判断卡同一套颜色：偏多用红、偏空用绿（A 股的习惯）
const STANCE_TONE: Record<string, Tone> = { 看多: 'pink', 中性偏多: 'pink', 看空: 'green', 中性偏空: 'green', 中性: 'gray' }
const STAGES = ['规划', '取证', '审核证据', '写结论', '核对'] as const

/** 现在进行到哪一步（对应 STAGES 的下标）。 */
function stageOf(t: Turn): number {
  if (t.playbook === 'rewrite' || t.rewriteOf != null) return 3
  if (!t.tasks.length) return 0
  if (!t.tasks.every((x) => x.state === 'done' || x.state === 'failed')) return 1
  const last = t.checks[t.checks.length - 1]
  if (!last) return 2
  if (last.tone === 'warn') return 1
  if (last.text.startsWith('回答校验') || last.text.startsWith('按校验意见')) return 4
  return 3
}

/** 等待中：告诉用户现在在干什么、大概还要多久，而不是只转一个圈。 */
const Waiting: React.FC<{ t: Turn }> = ({ t }) => {
  const stage = stageOf(t)
  const rewrite = t.rewriteOf != null
  const finished = t.tasks.filter((x) => x.state === 'done' || x.state === 'failed').length
  const running = t.tasks.filter((x) => x.state === 'running').map((x) => AGENT[x.agent]?.label ?? x.agent)
  const detail = rewrite ? '不重新取数，基于这次研究已有的证据重写'
    : ['正在理解问题、安排要查什么', `正在取证${running.length ? `：${running.join('、')}` : ''}（${finished}/${t.tasks.length}）`,
      '正在审核证据够不够', '证据齐了，正在写结论', '正在逐条核对数字和引用'][stage]
  const left = t.eta ? Math.round(t.eta - t.seconds) : null
  const pct = t.eta ? Math.min(96, (t.seconds / t.eta) * 100) : Math.min(90, stage * 20 + 8)
  return (
    <div className="rounded-lg border border-hairline p-4" role="status" aria-live="polite">
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="min-w-0 truncate font-medium text-ink">{detail}</span>
        <span className="shrink-0 tabular-nums text-steel">
          {left == null ? `已用 ${t.seconds.toFixed(0)} 秒` : left > 0 ? `大约还要 ${left} 秒` : '比平时久一点，快好了'}
        </span>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-surface">
        <div className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out" style={{ width: `${pct}%` }} />
      </div>
      {rewrite ? null : (
        <ol className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {STAGES.map((name, i) => (
            <li key={name} className={cn('inline-flex items-center gap-1', i < stage ? 'text-steel' : i === stage ? 'font-medium text-ink' : 'text-stone')}>
              {i < stage ? <Check className="h-3 w-3" /> : <Dot tone={i === stage ? 'purple' : 'gray'} pulse={i === stage} className="h-1.5 w-1.5" />}{name}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-xs text-stone">没通过核对的草稿不会显示。可以先去看别的页面，好了会提醒你。</p>
    </div>
  )
}

function phase(t: Turn) {
  if (!t.tasks.length) return '规划任务中'
  const last = t.checks[t.checks.length - 1]
  if (last?.tone === 'info') return '撰写并校验回答'
  if (last?.tone === 'warn') return '补充证据中'
  if (last?.tone === 'bad') return '校验未通过，处理中'
  return t.tasks.every((x) => x.state === 'done' || x.state === 'failed') ? '审核证据中' : '取证中'
}

const ResearchPage: React.FC = () => {
  const { turns, selected, focusEvidence } = useResearch()
  const [draft, setDraft] = useState('')
  const [processOpen, setProcessOpen] = useState(false)
  // 研究过程默认不占地方：想看的时候点「过程」，选择会记住
  const [showProcess, setShowProcess] = useState(() => { try { return localStorage.getItem(PROCESS_KEY) === '1' } catch { return false } })
  const toggleProcess = () => {
    if (!matchMedia('(min-width: 1280px)').matches) { setProcessOpen(true); return }
    setShowProcess((v) => { try { localStorage.setItem(PROCESS_KEY, v ? '0' : '1') } catch { /* 只在本次生效 */ } return !v })
  }
  const [depth, setDepthState] = useState<Depth>(() => { try { return (localStorage.getItem(DEPTH_KEY) as Depth) || 'auto' } catch { return 'auto' } })
  const setDepth = (d: Depth) => { setDepthState(d); try { localStorage.setItem(DEPTH_KEY, d) } catch { /* 只在本次生效 */ } }
  // 长报告默认先看结论卡片；想每次都直接看全文，展开一次就记住
  const [reportOpen, setReportOpen] = useState(() => { try { return localStorage.getItem(REPORT_KEY) === '1' } catch { return false } })
  const [opened, setOpened] = useState<Record<number, boolean>>({})
  const [reuse, setReuse] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const skillList = useApi(api.skills)
  const skillQuestions = (skillList.data?.skills ?? []).map((k) => `用「${k.label}」的方法看看贵州茅台`)
  const busy = turns.some((t) => t.running)
  const current = turns.find((t) => t.id === selected) ?? turns[turns.length - 1]
  const lastLength = turns[turns.length - 1]?.answer.length

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [turns.length, lastLength])

  const lastDone = [...turns].reverse().find((t) => !t.running && t.messageId != null && (t.status === 'passed' || t.status === 'partial'))
  const send = (text: string, rewriteOf?: number) => {
    askNotifyPermission()
    void research.ask(text, { depth, rewriteOf: rewriteOf ?? (reuse && lastDone ? lastDone.id : undefined) })
    setDraft('')
    setReuse(false)
  }
  const showReport = (t: Turn) => opened[t.id] ?? reportOpen
  const toggleReport = (t: Turn) => {
    const next = !showReport(t)
    setOpened((o) => ({ ...o, [t.id]: next }))
    setReportOpen(next)
    try { localStorage.setItem(REPORT_KEY, next ? '1' : '0') } catch { /* 只在本次生效 */ }
  }
  const cite = (t: Turn, id: string) => { research.focus(t.id, id); if (matchMedia('(min-width: 1280px)').matches) { setShowProcess(true) } else { setProcessOpen(true) } }

  return (
    <div className="flex h-full min-w-0">
      {/* 对话 */}
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[760px] px-6 pb-8 pt-10">
            {turns.length === 0 ? (
              <>
                <h1 className="text-[32px] font-semibold leading-tight tracking-[-0.5px] text-ink">想研究什么？</h1>
                <p className="mt-2 text-base text-steel">直接问。回答里的每个数字都能点开看它来自哪条数据。</p>
                {DEMO ? (
                  <div className="mt-8 rounded-lg border border-hairline p-4">
                    <p className="mb-2 text-[13px] text-steel">在线演示没有连接模型，可以回放下面这几次真实的研究过程：</p>
                    {demoFixtures.map((q) => (
                      <button key={q} type="button" onClick={() => send(q)}
                        className="-mx-1.5 block w-[calc(100%+0.75rem)] rounded-sm px-1.5 py-1.5 text-left text-sm text-charcoal transition-colors hover:bg-hover">
                        {q}
                      </button>
                    ))}
                  </div>
                ) : (
                  <>
                    <div className="mt-8 grid gap-2 sm:grid-cols-2">
                      {EXAMPLES.map((ex) => (
                        <button key={ex.q} type="button" onClick={() => send(ex.q)}
                          className="rounded-lg border border-hairline px-4 py-3 text-left transition-colors hover:bg-surface-soft">
                          <span className="block text-sm font-medium text-ink">{ex.label}</span>
                          <span className="mt-0.5 block truncate text-[13px] text-steel">{ex.q}</span>
                        </button>
                      ))}
                    </div>
                    <details className="mt-4 text-sm text-slate">
                      <summary className="cursor-pointer select-none text-[13px] text-steel hover:text-ink">还能问什么</summary>
                      <div className="mt-1">
                        {[...skillQuestions, ...MORE_EXAMPLES].map((q) => (
                          <button key={q} type="button" onClick={() => send(q)} className="-mx-1.5 flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-left hover:bg-hover hover:text-ink">
                            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-stone" />{q}
                          </button>
                        ))}
                      </div>
                    </details>
                  </>
                )}
              </>
            ) : (
              <div className="mb-6 flex items-center justify-between">
                <span className="text-[13px] text-steel">本次会话 · {turns.length} 个问题</span>
                {!busy ? <Button size="xs" variant="ghost" onClick={research.clear}><SquarePen className="h-3.5 w-3.5" />新会话</Button> : null}
              </div>
            )}

            <div className="flex flex-col gap-10">
              {turns.map((t) => {
                const st = STATUS[t.status]
                const isSelected = current?.id === t.id && turns.length > 1
                return (
                  <article key={t.id} onClick={() => research.select(t.id)}
                    className={cn('-mx-4 cursor-pointer rounded-lg px-4 py-3 transition-colors', isSelected && 'bg-surface-soft')}>
                    <h2 className="text-[22px] font-semibold leading-snug tracking-[-0.2px] text-ink">{t.question}</h2>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-steel">
                      {t.running
                        ? <Tag tone="purple"><Dot tone="purple" pulse className="h-1.5 w-1.5" />{phase(t)}</Tag>
                        : st ? <Tag tone={st.tone}>{st.label}</Tag> : null}
                      {t.rewriteOf != null || PLAYBOOK[t.playbook] || t.playbook.startsWith('skill:')
                        ? <Tag tone="purple">{t.rewriteOf != null ? PLAYBOOK.rewrite : PLAYBOOK[t.playbook] ?? `方法：${t.intent}`}</Tag> : null}
                      {t.securities.map((s) => (
                        <Link key={s.code} to={securityPath(s)} onClick={(e) => e.stopPropagation()} title="已解析出的证券，点击查看详情"
                          className="rounded-sm bg-tint-gray px-1.5 py-0.5 text-xs text-on-gray hover:brightness-95">{s.name} <span className="font-mono">{s.code}</span></Link>
                      ))}
                      <span className="tabular-nums">{t.seconds.toFixed(0)} 秒</span>
                      <span>·</span>
                      {t.rewriteOf == null ? <span>{t.evidence.length} 条证据</span> : <span>沿用上一轮的证据</span>}
                      {t.usage?.input_tokens ? <span title={`输入 ${t.usage.input_tokens.toLocaleString()} token，其中 ${t.usage.cached_tokens.toLocaleString()} 命中缓存；输出 ${t.usage.output_tokens.toLocaleString()}`}>· {Math.round((t.usage.input_tokens + t.usage.output_tokens) / 1000)}k token（缓存 {t.usage.cache_hit_pct}%）</span> : null}
                      <Button size="xs" variant="ghost" onClick={(e) => { e.stopPropagation(); research.select(t.id); toggleProcess() }}>
                        <ListTree className="h-3.5 w-3.5" />过程
                      </Button>
                    </div>
                    {t.rewriteOf == null && t.securities.filter((x) => x.asset_type === 'stock').slice(0, 3).length > 0 ? (
                      <div className="mt-4 grid gap-2 sm:grid-cols-3" onClick={(e) => e.stopPropagation()}>
                        {t.securities.filter((x) => x.asset_type === 'stock').slice(0, 3).map((x) => <StockSnapshot key={x.code} code={x.code} name={x.name} />)}
                      </div>
                    ) : null}
                    <div className="mt-4" onClick={(e) => e.stopPropagation()}>
                      {t.running ? <Waiting t={t} />
                        : !t.answer ? <p className="text-[15px] text-steel">{t.error || '没有生成回答。'}</p>
                        : t.summary && t.rewriteOf == null ? (
                          <>
                            {/* 长报告先给结论：几句话 + 立场。要看论证再展开全文。改写是用户点名要的写法，直接给全文 */}
                            <div className="rounded-lg border border-hairline bg-surface-soft p-4">
                              <div className="mb-1.5 flex items-center gap-2">
                                <span className="eyebrow">结论</span>
                                {t.summary.stance ? <Tag tone={STANCE_TONE[t.summary.stance] ?? 'gray'}>{t.summary.stance}</Tag> : null}
                              </div>
                              <p className="text-[15px] leading-relaxed text-ink">{t.summary.conclusion}</p>
                              <button type="button" onClick={() => toggleReport(t)} aria-expanded={showReport(t)}
                                className="mt-3 inline-flex items-center gap-1 text-[13px] text-link hover:underline">
                                <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', showReport(t) && 'rotate-90')} />
                                {showReport(t) ? '收起完整报告' : `展开完整报告（${t.answer.length.toLocaleString()} 字，每个数字都带出处）`}
                              </button>
                            </div>
                            {showReport(t) ? <div className="mt-5"><AnswerMarkdown content={t.answer} onCite={(id) => cite(t, id)} /></div> : null}
                          </>
                        ) : <AnswerMarkdown content={t.answer} onCite={(id) => cite(t, id)} />}
                    </div>
                    {!DEMO && !t.running && t.messageId != null && (t.status === 'passed' || t.status === 'partial') && t.id === turns[turns.length - 1].id ? (
                      <div className="mt-4 flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <span className="mr-1 text-xs text-stone" title="不重新取数，只用这一轮已经拿到的证据换个写法">换个写法</span>
                        {REWRITES.map((r) => (
                          <button key={r} type="button" disabled={busy} onClick={() => send(r, t.rewriteOf ?? t.id)}
                            className="rounded-full border border-hairline px-2.5 py-0.5 text-[13px] text-slate transition-colors hover:bg-hover hover:text-ink disabled:opacity-50">{r}</button>
                        ))}
                      </div>
                    ) : null}
                    {t.checkpoints.length > 0 ? (
                      <details className="mt-6" onClick={(e) => e.stopPropagation()}>
                        <summary className="cursor-pointer select-none text-[13px] text-steel hover:text-ink">{t.checkpoints.length} 个验证点 · 到期后自动核对这次的判断对不对</summary>
                        <div className="mt-2"><CheckpointTable items={t.checkpoints} showStock={new Set(t.checkpoints.map((c) => c.code)).size > 1} /></div>
                      </details>
                    ) : null}
                    {t.proposals.length > 0 ? (
                      <div className="mt-6" onClick={(e) => e.stopPropagation()}>
                        <p className="eyebrow mb-2">操作建议单 · 需要你逐条授权</p>
                        <ProposalList items={t.proposals} />
                      </div>
                    ) : null}
                    {t.missing.length > 0 ? <Callout tone="warning" className="mt-4">未能取得的证据：{t.missing.join('；')}</Callout> : null}
                    {!t.running && t.followUps.length > 0 && t.id === turns[turns.length - 1].id ? (
                      <div className="mt-5 flex flex-col items-start gap-1">
                        <span className="eyebrow mb-1">继续追问</span>
                        {t.followUps.map((f) => (
                          <button key={f} type="button" onClick={(e) => { e.stopPropagation(); send(f) }}
                            className="-mx-1.5 flex items-center gap-1.5 rounded-sm px-1.5 py-1 text-left text-sm text-slate hover:bg-hover hover:text-ink">
                            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-stone" />{f}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          </div>
        </div>

        <div className="mx-auto w-full max-w-[760px] px-6 pb-6">
          <form onSubmit={(e) => { e.preventDefault(); send(draft) }}
            className="flex items-end gap-2 rounded-xl border border-hairline-strong bg-canvas p-2 shadow-subtle transition-shadow focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
            <textarea
              id="research-input" rows={1} value={draft} disabled={busy}
              placeholder={busy ? '研究进行中…' : DEMO ? '在线演示只能回放上面的示例问题' : '输入问题，Enter 发送，Shift+Enter 换行'}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(draft) } }}
              className="max-h-36 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] text-ink outline-none placeholder:text-stone disabled:opacity-60"
            />
            {busy
              ? <Button variant="secondary" size="sm" onClick={research.stop}><Square className="h-3.5 w-3.5" />停止</Button>
              : <Button type="submit" size="sm" disabled={!draft.trim()} aria-label="发送"><ArrowUp className="h-4 w-4" />发送</Button>}
          </form>
          {DEMO ? null : (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-xs text-steel">
              <div className="inline-flex overflow-hidden rounded-md border border-hairline" role="radiogroup" aria-label="研究深度">
                {DEPTHS.map((d) => (
                  <button key={d.key} type="button" role="radio" aria-checked={depth === d.key} title={d.hint} onClick={() => setDepth(d.key)}
                    className={cn('px-2.5 py-1 transition-colors', depth === d.key ? 'bg-surface font-medium text-ink' : 'hover:bg-hover hover:text-ink')}>{d.label}</button>
                ))}
              </div>
              <span className="hidden sm:inline">{DEPTHS.find((d) => d.key === depth)?.hint}</span>
              {lastDone ? (
                <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5" title="不重新取数，几秒钟。适合追问“那风险呢”“换个说法”这类问题；要查新的数据就别勾">
                  <input type="checkbox" checked={reuse} onChange={(e) => setReuse(e.target.checked)} className="accent-[var(--color-primary)]" />
                  只用上一轮的证据回答
                </label>
              ) : null}
            </div>
          )}
          <p className="mt-2 text-center text-xs text-stone">内容由 AI 基于工具数据生成，不构成投资建议</p>
        </div>
      </div>

      <aside className={cn('hidden h-full w-[360px] shrink-0 flex-col border-l border-hairline bg-surface-soft', showProcess && 'xl:flex')}>
        <Inspector turn={current} focus={focusEvidence} />
      </aside>
      {/* 窄屏：过程面板收进抽屉 */}
      <Drawer open={processOpen} onClose={() => setProcessOpen(false)} title="研究过程" width="max-w-[400px]">
        <div className="-mx-6 -my-5 flex h-full flex-col bg-surface-soft"><Inspector turn={current} focus={focusEvidence} compact /></div>
      </Drawer>
    </div>
  )
}

/** 回答上方的一眼图：近半年走势、现价与涨跌、PE 所处的历史分位。数字和回答引用的是同一批工具。 */
const StockSnapshot: React.FC<{ code: string; name: string }> = ({ code, name }) => {
  const kline = useApi(() => api.stockKline(code, 125), [code])
  const valuation = useApi(() => runTool<ValuationHistory | string>('get_valuation_history', { code }), [code])
  const points = kline.data ? [...kline.data.data].reverse() : []
  const last = points[points.length - 1]
  const change = points.length > 1 ? (last.nav / points[0].nav - 1) * 100 : null
  const pe = valuation.data && typeof valuation.data.data !== 'string' ? valuation.data.data.pe : null
  if (kline.error && valuation.error) return null
  return (
    <Link to={securityPath({ code, asset_type: 'stock' })} className="block rounded-lg border border-hairline p-3 transition-colors hover:bg-surface-soft">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-ink">{name}</span>
        <span className="font-mono text-xs text-stone">{code}</span>
      </div>
      {points.length > 1 ? <Sparkline values={points.map((p) => p.nav)} /> : <div className="h-11" />}
      <div className="flex items-baseline justify-between text-[13px] tabular-nums">
        <span className="text-ink">{last ? last.nav.toFixed(2) : '—'}</span>
        <span className={change == null ? 'text-steel' : change >= 0 ? 'text-up' : 'text-down'}>{change == null ? '' : `近半年 ${change >= 0 ? '+' : ''}${change.toFixed(1)}%`}</span>
      </div>
      {pe?.percentile != null ? (
        <div className="mt-2">
          <div className="relative h-1.5 rounded-full bg-surface"><span className="absolute top-1/2 h-3 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" style={{ left: `${pe.percentile}%` }} /></div>
          <p className="mt-1 text-xs text-steel">PE {pe.current} · 历史分位 {pe.percentile}%</p>
        </div>
      ) : null}
    </Link>
  )
}

const EvidenceRow: React.FC<{ e: Evidence; open: boolean; focused: boolean; onToggle: () => void; innerRef?: React.Ref<HTMLDivElement> }> = ({ e, open, focused, onToggle, innerRef }) => (
  <div ref={innerRef} className={cn('rounded-sm', focused && 'bg-tint-lavender/60')}>
    <button type="button" onClick={onToggle} className="flex w-full items-center gap-1.5 rounded-sm px-1 py-1 text-left text-[13px] hover:bg-hover">
      <ChevronRight className={cn('h-3.5 w-3.5 shrink-0 text-stone transition-transform', open && 'rotate-90')} />
      <code className="truncate font-mono text-[12.5px] text-charcoal">{e.tool}</code>
      {!e.ok ? <Tag tone="yellow" className="!py-0">无数据</Tag> : null}
      <span className="ml-auto shrink-0 font-mono text-[11px] text-stone">{e.id.slice(2, 6)}</span>
    </button>
    {open ? (
      <div className="mb-1 ml-5 space-y-1 border-l border-hairline pl-3 text-xs text-slate">
        <p><span className="text-steel">入参</span> <span className="break-all font-mono">{e.input}</span></p>
        {e.asOf ? <p><span className="text-steel">数据日期</span> <span className="font-mono">{e.asOf}</span></p> : null}
        {e.source ? <p><span className="text-steel">来源</span> <a className="text-link hover:underline" href={e.source} target="_blank" rel="noreferrer">{new URL(e.source).hostname}</a></p> : null}
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-sm bg-surface p-2.5 font-mono text-[11.5px] leading-relaxed text-charcoal">{e.output}</pre>
      </div>
    ) : null}
  </div>
)

const TASK_STATE = { pending: ['gray', '等待'], running: ['purple', '进行中'], done: ['green', '完成'], failed: ['red', '失败'] } as const

const Inspector: React.FC<{ turn?: Turn; focus: string; compact?: boolean }> = ({ turn, focus, compact }) => {
  const [open, setOpen] = useState('')
  const focusRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!focus) return
    setOpen(focus)
    const timer = setTimeout(() => focusRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60)
    return () => clearTimeout(timer)
  }, [focus])

  const evidenceList = (list: Evidence[]) => list.map((e) => (
    <EvidenceRow key={e.id} e={e} open={open === e.id} focused={focus === e.id}
      innerRef={focus === e.id ? focusRef : undefined} onToggle={() => setOpen((o) => (o === e.id ? '' : e.id))} />
  ))

  return (
    <>
      <header className={cn('px-5 pb-3', compact ? 'pt-4' : 'pt-10')}>
        {compact ? null : <h2 className="text-base font-semibold text-ink">研究过程</h2>}
        <p className="mt-0.5 truncate text-[13px] text-steel">
          {turn ? (PLAYBOOK[turn.playbook] ? `${PLAYBOOK[turn.playbook]}模板 · ` : '') + (turn.intent || '等待规划') + (turn.fallbackPlan ? ' · 关键词兜底规划' : '') : '规划、证据与校验记录'}
        </p>
      </header>
      <div className="flex-1 space-y-6 overflow-y-auto px-5 pb-6">
        {!turn ? (
          <p className="text-sm text-steel">提问后，这里会实时显示任务规划、每次工具调用拿到的证据，以及校验结论。点回答里的证据标签会定位到这里。</p>
        ) : (
          <>
            <section>
              <p className="eyebrow mb-2">任务与证据</p>
              {turn.tasks.length === 0 ? <p className="text-[13px] text-steel">{turn.running ? '正在规划…' : '没有执行任务'}</p> : null}
              <div className="space-y-3">
                {turn.tasks.map((task) => {
                  const meta = AGENT[task.agent] ?? { label: task.agent, tone: 'gray' as Tone }
                  const [tone, label] = TASK_STATE[task.state]
                  return (
                    <div key={task.id} className="rounded-lg border border-hairline bg-canvas p-3">
                      <div className="flex items-center justify-between gap-2">
                        <Tag tone={meta.tone}>{meta.label}</Tag>
                        <span className="inline-flex items-center gap-1.5 text-xs text-steel"><Dot tone={tone} pulse={task.state === 'running'} className="h-1.5 w-1.5" />{label}</span>
                      </div>
                      <p className="mt-2 text-[13px] leading-relaxed text-slate">{task.goal}</p>
                      <div className="mt-2">{evidenceList(turn.evidence.filter((e) => e.taskId === task.id))}</div>
                    </div>
                  )
                })}
                {evidenceList(turn.evidence.filter((e) => !turn.tasks.some((t) => t.id === e.taskId)))}
              </div>
            </section>

            {turn.checks.length > 0 ? (
              <section>
                <p className="eyebrow mb-2">校验记录</p>
                <ul className="space-y-2">
                  {turn.checks.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-slate">
                      <Dot className="mt-[7px] h-1.5 w-1.5" tone={c.tone === 'ok' ? 'green' : c.tone === 'bad' ? 'red' : c.tone === 'warn' ? 'orange' : 'gray'} />
                      <span className="min-w-0 break-words">{c.text}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {turn.criteria.length > 0 ? (
              <section>
                <p className="eyebrow mb-2">本轮必须取得的证据</p>
                <ul className="list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-slate">
                  {turn.criteria.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </section>
            ) : null}
          </>
        )}
      </div>
    </>
  )
}

export default ResearchPage
