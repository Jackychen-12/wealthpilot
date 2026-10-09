import type React from 'react'
import { useState } from 'react'
import { DEMO, api, type TradesReport } from '../api'
import { Button, Callout, Tag } from '../components/kit'
import { Terms } from '../components/Terms'
import { Metric, Metrics, Page, Section } from '../components/ui'
import { DecisionsSection } from './DecisionsSection'

const SAMPLE = '成交日期,证券代码,证券名称,操作,成交均价,成交数量\n20260112,600519,贵州茅台,证券买入,1500,100\n20260305,600519,贵州茅台,证券卖出,1420,100'

/** 交易行为诊断：贴成交记录进来，找反复出现的行为偏差。不调用模型，记录不保存。 */
const TradesPage: React.FC = () => {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<TradesReport | null>(null)
  const [error, setError] = useState('')
  const run = async () => {
    setBusy(true); setError('')
    try { setReport(await api.checkTrades(text)) } catch (e) { setError(e instanceof Error ? e.message : '没有算出来') } finally { setBusy(false) }
  }
  const load = (file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result as ArrayBuffer)
      let decoded = new TextDecoder('utf-8', { fatal: false }).decode(bytes)
      if (decoded.includes('\ufffd')) decoded = new TextDecoder('gb18030').decode(bytes)     // 券商导出的表多半是 GBK
      setText(decoded)
    }
    reader.readAsArrayBuffer(file)
  }
  if (DEMO) {
    return <Page title="交易行为诊断" description="从你自己的成交记录里，找反复出现的行为偏差"><Callout tone="info">在线演示没有后端，这一页在本地运行后可用。</Callout></Page>
  }
  return (
    <Page title="交易行为诊断" description="两件事：记下每次为什么买、过后按来源对账；从成交记录里找反复出现的行为偏差。都不调用模型">
      <DecisionsSection />
      <Section title="成交记录诊断" hint="券商 App 里导出交割单（CSV），或者自己写：每行“日期 代码 买/卖 价格 数量”。只在这次计算里用，不保存">
        <div className="grid max-w-3xl gap-3">
          <textarea aria-label="成交记录" value={text} onChange={(e) => setText(e.target.value)} rows={8} placeholder={SAMPLE}
            className="w-full rounded-md border border-hairline-strong bg-canvas px-3 py-2 font-mono text-[13px] leading-relaxed text-ink outline-none placeholder:text-stone focus:border-primary focus:ring-1 focus:ring-primary" />
          <div className="flex flex-wrap items-center gap-3">
            <Button loading={busy} disabled={!text.trim()} onClick={() => void run()}>开始诊断</Button>
            <label className="cursor-pointer text-[13px] text-slate underline underline-offset-2 hover:text-ink">
              选一个文件<input type="file" accept=".csv,.txt,.tsv" className="hidden" onChange={(e) => load(e.target.files?.[0])} />
            </label>
            <span className="text-[13px] text-steel">不调用模型。要用到行情，第一次会慢几秒。</span>
          </div>
          {error ? <Callout tone="danger">{error}</Callout> : null}
        </div>
      </Section>
      {report && !report.ok ? <Callout tone="warning">{report.reason}{report.problems.length ? <ul className="mt-1 list-disc pl-5">{report.problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}</Callout> : null}
      {report?.ok ? (
        <>
          <Section title="结果" hint={`${report.period!.from} 到 ${report.period!.to}`}>
            <Metrics>
              <Metric label="成交" value={report.trades} hint={`${report.stocks} 只股票`} />
              <Metric label="了结" value={report.closed} hint="先进先出配成的来回" />
              <Metric label="需要留意" value={report.flagged!.length} hint={report.flagged!.join('、') || '没有发现反复出现的行为偏差'} />
            </Metrics>
            <ul className="mt-4 divide-y divide-hairline-soft rounded-lg border border-hairline">
              {report.findings!.map((f) => (
                <li key={f.key} className="px-4 py-3">
                  <p className="flex items-center gap-2 text-sm font-medium text-ink">{f.label}{f.flag ? <Tag tone="orange">留意</Tag> : null}</p>
                  <p className="mt-1 text-sm text-charcoal">{f.text}</p>
                  {f.examples.length ? <ul className="mt-1 list-disc pl-5 text-[13px] text-steel">{f.examples.map((e) => <li key={e}>{e}</li>)}</ul> : null}
                </li>
              ))}
            </ul>
            {report.worst_stocks!.length ? <p className="mt-3 text-[13px] text-slate">亏得最多的：{report.worst_stocks!.map((w) => `${w.name} ${Math.round(w.pnl).toLocaleString()} 元`).join('，')}。</p> : null}
            {report.missing_prices!.length ? <p className="mt-1 text-[13px] text-steel">这些代码没取到行情，追高和卖出之后两项没算上它们：{report.missing_prices!.join('、')}</p> : null}
            {report.problems.length ? <p className="mt-1 text-[13px] text-steel">有 {report.problems.length} 行没认出来：{report.problems.slice(0, 3).join('；')}</p> : null}
            <p className="mt-2 text-[13px] text-steel">{report.note}</p>
            <Terms className="mt-2" words={['追涨', '亏损加仓', '处置效应', '盈亏比', '胜率', '先进先出']} />
          </Section>
        </>
      ) : null}
    </Page>
  )
}

export default TradesPage
