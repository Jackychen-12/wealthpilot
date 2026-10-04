import type React from 'react'
import { useState } from 'react'
import { Download, Sparkles } from 'lucide-react'
import { API_BASE, api, type WeeklyReport } from '../api'
import { Button } from '../components/kit'
import { DataState, Page } from '../components/ui'

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section>
    <h2 className="text-lg font-semibold text-ink">{title}</h2>
    <div className="mt-2 text-[15px] leading-relaxed text-charcoal">{children}</div>
  </section>
)

const ReportPage: React.FC = () => {
  const [report, setReport] = useState<WeeklyReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // 每次生成都会调用一次大模型，所以不自动加载，由用户点击触发
  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      setReport(await api.weekly())
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Page title="周报" description="基于当前持仓和本周行情，按需生成复盘"
      actions={(
        <>
          <Button size="sm" onClick={() => void generate()} loading={loading}>{loading ? null : <Sparkles className="h-4 w-4" />}{loading ? '生成中…' : report ? '重新生成' : '生成周报'}</Button>
          <a className="inline-flex h-8 items-center gap-1.5 rounded-md border border-hairline-strong px-3 text-sm font-medium text-ink hover:bg-surface" href={`${API_BASE}/api/report/pdf`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" />导出 PDF</a>
        </>
      )}>
      <div>
        {report?.week_start ? <p className="mb-4 font-mono text-[13px] text-steel">{report.week_start} 至 {report.week_end}</p> : null}
        <DataState loading={loading} error={error} onRetry={() => void generate()}
          empty={!report ? '点击右上角"生成周报"开始。生成一次会调用一次大模型，约需十几秒。' : undefined}>
          {report ? (
            <div className="max-w-[720px] space-y-7">
              {report.summary ? <p className="rounded-md bg-surface px-4 py-3 text-base leading-relaxed text-ink">{report.summary}</p> : null}
              {report.key_points?.length ? (
                <Section title="本周要点">
                  <ul className="space-y-2">{report.key_points.map((k, i) => <li key={i}><span className="font-semibold text-ink">{k.title}</span>：{k.desc}</li>)}</ul>
                </Section>
              ) : null}
              {report.next_week_focus?.length ? (
                <Section title="下周关注"><ul className="list-disc space-y-1.5 pl-5">{report.next_week_focus.map((k, i) => <li key={i}>{k}</li>)}</ul></Section>
              ) : null}
              {report.risk_alert ? <Section title="风险提示">{report.risk_alert}</Section> : null}
              {report.ai_insight ? <Section title="AI 洞察">{report.ai_insight}</Section> : null}
            </div>
          ) : null}
        </DataState>
      </div>
      <p className="text-[13px] text-steel">周报由大模型根据分析数据撰写，没有经过"AI 研究"里的证据校验流程，数字请以总览和风险体检页为准。</p>
    </Page>
  )
}

export default ReportPage
