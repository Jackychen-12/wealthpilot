import type React from 'react'
import { DEMO, api, useApi } from '../api'
import { Callout, Tag } from '../components/kit'
import { DataState, Metric, Metrics, Section, Table, Td, signClass } from '../components/ui'

const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`)
const MOOD_TONE: Record<string, string> = { 冰点: 'text-down', 偏冷: 'text-down', 一般: 'text-ink', 偏热: 'text-up', 高潮: 'text-up' }

/** 今天市场发生了什么：涨停与连板、题材热点、龙虎榜。全是取数和计数，不调用模型。 */
export const RecapSection: React.FC = () => {
  const recap = useApi(() => (DEMO ? Promise.reject(new Error('demo')) : api.recap()))
  const r = recap.data
  if (DEMO || (!recap.loading && !r)) return null     // 休市、没开盘、演示：这一块不占地方
  return (
    <Section title="今天的市场" hint={r ? `${r.day} · 情绪${r.mood.label}（按固定尺子得出的粗略刻度，不是预测）` : undefined}>
      <DataState loading={recap.loading && !r}>
        {r ? (
          <div className="grid gap-4">
            <Metrics>
              <Metric label="涨停" value={r.limits.limit_up} hint={`首板 ${r.limits.first_board} · 连板 ${r.limits.multi_board}`} />
              <Metric label="炸板" value={r.limits.broken} hint={r.limits.seal_rate_pct != null ? `封板率 ${r.limits.seal_rate_pct}%` : undefined} />
              <Metric label="跌停" value={r.limits.limit_down} />
              <Metric label="最高连板" value={r.limits.max_streak} hint={r.limits.ladder[0]?.names.slice(0, 2).join('、')} />
              <Metric label="昨日涨停今日" value={pct(r.limits.yesterday_limit_up_today_pct, 2)} tone={signClass(r.limits.yesterday_limit_up_today_pct ?? 0)} hint={`${r.limits.yesterday_limit_up_count} 只的平均`} />
              <Metric label="情绪" value={r.mood.label} tone={MOOD_TONE[r.mood.label]} hint={r.breadth ? `${r.breadth.up} 涨 / ${r.breadth.down} 跌` : undefined} />
            </Metrics>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-1.5 text-[13px] font-medium text-charcoal">连板梯队</p>
                {r.limits.ladder.length ? (
                  <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline text-sm">
                    {r.limits.ladder.slice(0, 6).map((step) => (
                      <li key={step.boards} className="flex gap-3 px-4 py-2"><span className="w-14 shrink-0 tabular-nums text-steel">{step.boards} 连板</span><span className="min-w-0 text-ink">{step.names.slice(0, 8).join('、')}</span></li>
                    ))}
                  </ul>
                ) : <p className="text-[13px] text-steel">今天没有连板股。</p>}
              </div>
              <div>
                <p className="mb-1.5 text-[13px] font-medium text-charcoal">涨停集中在{r.themes[0] ? `（按${r.themes[0].basis}）` : ''}</p>
                {r.themes.length ? (
                  <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline text-sm">
                    {r.themes.slice(0, 6).map((t) => (
                      <li key={t.theme} className="flex gap-3 px-4 py-2"><span className="w-28 shrink-0 truncate text-ink">{t.theme}</span><span className="w-10 shrink-0 tabular-nums text-steel">{t.count} 只</span><span className="min-w-0 truncate text-slate">{t.names.join('、')}</span></li>
                    ))}
                  </ul>
                ) : <p className="text-[13px] text-steel">涨停比较分散，没有明显集中的题材。</p>}
              </div>
            </div>
            {r.billboard && r.billboard.count ? (
              <p className="text-[13px] text-slate">
                龙虎榜 {r.billboard.count} 只
                {r.billboard.institution_net_yi != null ? <>，机构席位合计净买 <b className={signClass(r.billboard.institution_net_yi)}>{r.billboard.institution_net_yi.toFixed(2)} 亿</b></> : null}
                {r.billboard.northbound_net_yi != null ? <>，北向席位 <b className={signClass(r.billboard.northbound_net_yi)}>{r.billboard.northbound_net_yi.toFixed(2)} 亿</b></> : null}
                ；净买最多：{r.billboard.top_buy.slice(0, 4).map((s) => `${s.name} ${s.net_yi.toFixed(2)} 亿`).join('，')}。
              </p>
            ) : null}
            {r.concepts ? (
              <p className="text-[13px] text-slate">概念领涨：{r.concepts.top.slice(0, 5).map((c) => `${c.name} ${pct(c.change_pct, 2)}`).join('，')}；领跌：{r.concepts.bottom.slice(0, 3).map((c) => `${c.name} ${pct(c.change_pct, 2)}`).join('，')}。</p>
            ) : null}
          </div>
        ) : null}
      </DataState>
    </Section>
  )
}

/** 宏观数据：景气、物价、货币信贷、利率。 */
export const MacroSection: React.FC = () => {
  const macro = useApi(() => (DEMO ? Promise.reject(new Error('demo')) : api.macro()))
  const m = macro.data
  const rows = [...(m?.indicators ?? []), ...(m?.rates ?? [])]
  if (DEMO || (!macro.loading && !rows.length)) return null
  return (
    <Section title="宏观" hint="景气、物价、货币信贷、利率。月度数据次月公布">
      <DataState loading={macro.loading && !m}>
        {m ? (
          <>
            <Table head={[{ label: '指标' }, { label: '最新', right: true }, { label: '比上期', right: true }, { label: '数据所属' }, { label: '怎么读' }]} minWidth={640}>
              {rows.map((i) => (
                <tr key={i.key} className="border-t border-hairline-soft">
                  <Td>{i.label}</Td>
                  <Td right num>{i.value}{i.unit}</Td>
                  <Td right num className={signClass(i.change ?? 0)}>{i.change == null ? '—' : `${i.change > 0 ? '+' : ''}${i.change}`}</Td>
                  <Td className="text-steel">{i.unit === '%' && i.as_of.length >= 10 && ['cn10y', 'cn2y', 'us10y', 'us2y', 'lpr1y', 'lpr5y'].includes(i.key) ? i.as_of : i.as_of.slice(0, 7)}</Td>
                  <Td className="text-steel">{i.how_to_read ?? ''}</Td>
                </tr>
              ))}
            </Table>
            {m.spread ? <p className="mt-2 text-[13px] text-slate">{m.spread.label} <b className="text-ink">{m.spread.value > 0 ? '+' : ''}{m.spread.value} {m.spread.unit}</b>：{m.spread.how_to_read}。</p> : null}
            {m.missing?.length ? <p className="mt-1 text-[13px] text-steel">没有的：{m.missing.join('；')}</p> : null}
          </>
        ) : null}
      </DataState>
    </Section>
  )
}

/** 立场成绩单：给过立场的个股研究，之后相对沪深 300 的表现。 */
export const StanceSection: React.FC = () => {
  const card = useApi(() => (DEMO ? Promise.reject(new Error('demo')) : api.stances()))
  const c = card.data
  if (DEMO) return null
  return (
    <Section title="立场成绩单" hint="当时说看多、看空的那些，后来相对沪深 300 怎么样。看多要跑赢、看空要跑输才算对">
      <DataState loading={card.loading && !c} error={card.error} onRetry={card.reload}>
        {c && c.total ? (
          <>
            <Table head={[{ label: '之后' }, { label: '已结算', right: true }, { label: '方向对了', right: true }, { label: '看多的平均超额', right: true }, { label: '看空的平均超额', right: true }]} minWidth={560}>
              {Object.entries(c.horizons).map(([h, item]) => (
                <tr key={h} className="border-t border-hairline-soft">
                  <Td>{h} 个交易日</Td>
                  <Td right num>{item.settled}{item.pending ? <span className="text-steel">（另 {item.pending} 未到期）</span> : null}</Td>
                  <Td right num>{item.settled ? `${item.right}（${item.hit_rate_pct}%）` : '—'}</Td>
                  <Td right num className={signClass(item.看多_avg_excess_pct ?? 0)}>{pct(item.看多_avg_excess_pct)}</Td>
                  <Td right num className={signClass(item.看空_avg_excess_pct ?? 0)}>{pct(item.看空_avg_excess_pct)}</Td>
                </tr>
              ))}
            </Table>
            {c.note ? <p className="mt-2 text-[13px] text-steel">{c.note}</p> : null}
            <div className="mt-3">
              <Table head={[{ label: '日期' }, { label: '股票' }, { label: '立场' }, { label: '5 日超额', right: true }, { label: '20 日超额', right: true }, { label: '60 日超额', right: true }]} minWidth={560}>
                {c.calls.slice(0, 12).map((call) => (
                  <tr key={call.message_id} className="border-t border-hairline-soft">
                    <Td className="text-steel">{call.asked}</Td><Td>{call.name}</Td><Td><Tag>{call.stance}</Tag></Td>
                    {['5', '20', '60'].map((h) => {
                      const res = call.results[h]
                      return <Td key={h} right num className={res?.settled ? (res.right ? 'text-ink' : 'text-steel') : 'text-stone'}>{res?.settled ? `${pct(res.excess_pct)} ${res.right ? '✓' : '✗'}` : '未到期'}</Td>
                    })}
                  </tr>
                ))}
              </Table>
            </div>
          </>
        ) : c ? <p className="text-[13px] text-steel">{c.note}</p> : null}
      </DataState>
    </Section>
  )
}

/** 反向 DCF：现价隐含了多高的利润增速。不是目标价。 */
export const ReverseDcfSection: React.FC<{ code: string }> = ({ code }) => {
  const dcf = useApi(() => (DEMO ? Promise.reject(new Error('demo')) : api.reverseDcf(code)), [code])
  const d = dcf.data
  if (DEMO) return null
  return (
    <Section title="现价隐含了什么" hint="反向 DCF：按现在的市值倒推，利润要以多高的速度涨十年才配得上。不是目标价">
      <DataState loading={dcf.loading && !d} error={dcf.error} onRetry={dcf.reload}>
        {d && d.ok ? (
          <div className="grid gap-3">
            <Metrics>
              {d.implied_growth!.map((i) => (
                <Metric key={i.discount_pct} label={`折现率 ${i.discount_pct}% 时`} value={i.growth_pct == null ? '解释不了' : `${i.growth_pct}%`} hint="隐含的利润年增速" />
              ))}
              <Metric label="过去三年实际" value={d.past_profit_cagr_3y_pct == null ? '—' : `${d.past_profit_cagr_3y_pct}%`} hint="归母净利润年化增速" />
            </Metrics>
            <p className="text-[13px] text-slate">市值 {d.market_cap_yi} 亿，{d.profit_period}归母净利润 {d.profit_ttm_yi} 亿（PE {d.pe_ttm}）。假设利润按下面的速度涨十年、之后每年 2.5%，折现率 {d.scenarios!.discount_pct}%：</p>
            <Table head={[{ label: '假设每年增长' }, ...d.scenarios!.rows.map((r) => ({ label: `${r.growth_pct}%`, right: true }))]} minWidth={420}>
              <tr className="border-t border-hairline-soft">
                <Td>算出来的价值是市值的几倍</Td>
                {d.scenarios!.rows.map((r) => <Td key={r.growth_pct} right num>{r.value_vs_market_cap.toFixed(2)}</Td>)}
              </tr>
            </Table>
            <ul className="list-disc space-y-0.5 pl-5 text-[13px] text-steel">{d.notes!.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        ) : d ? <Callout tone="neutral">{d.reason}</Callout> : null}
      </DataState>
    </Section>
  )
}
