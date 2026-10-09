import type React from 'react'
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export interface Exportable { question: string; answer: string; when?: string; evidence?: { id: string; tool?: string; output?: unknown }[] }

const short = (id: string) => id.slice(2, 6)
const flat = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v ?? '')).replace(/\s+/g, ' ').slice(0, 200)
const stamp = (when?: string) => (when ?? new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString()).slice(0, 16).replace('T', ' ')

/** 和终端里 /export 存出来的是同一种文件：问题、回答、证据清单。 */
export const researchMarkdown = (r: Exportable) => [
  `# ${r.question || '研究'}`, '', `> WealthPilot · ${stamp(r.when)} · 不构成投资建议`, '', r.answer.trim(), '',
  ...(r.evidence?.length ? ['## 证据', '', ...r.evidence.map((e) => `- \`${e.id}\` ${e.tool ?? ''}：${flat(e.output)}`), ''] : []),
].join('\n')

export const exportName = (r: Exportable) =>
  `wealthpilot-${stamp(r.when).replace(/[- :]/g, '').slice(0, 12)}-${(r.question.replace(/[^0-9A-Za-z一-龥]+/g, '-').slice(0, 24).replace(/^-+|-+$/g, '')) || '研究'}.md`

const download = (name: string, text: string) => {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url; a.download = name
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const PRINT_CSS = `
  body { font: 14px/1.75 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; color: #1a1a1a; max-width: 720px; margin: 32px auto; padding: 0 24px; }
  h1 { font-size: 22px; line-height: 1.4; margin: 0 0 6px; } h2 { font-size: 17px; margin: 26px 0 8px; } h3 { font-size: 15px; margin: 18px 0 6px; }
  .meta { color: #777; font-size: 12.5px; margin-bottom: 20px; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; } th, td { border: 1px solid #ddd; padding: 5px 8px; text-align: left; } th { background: #f6f6f4; }
  code { font: 12px ui-monospace, Menlo, monospace; background: #f3f2ef; padding: 0 3px; border-radius: 3px; }
  blockquote { margin: 10px 0; padding-left: 12px; border-left: 3px solid #ddd; color: #555; }
  .evidence li { font-size: 12px; color: #555; word-break: break-all; margin-bottom: 3px; }
  @media print { body { margin: 0 auto; } h2, h3 { break-after: avoid; } table, li { break-inside: avoid; } }
`

/** 在新窗口里排成一页干净的文档再打印：浏览器的打印对话框里选「存储为 PDF」就是 PDF。 */
const print = (r: Exportable) => {
  const w = window.open('', '_blank')
  if (!w) return false
  w.document.title = r.question || 'WealthPilot 研究'
  const style = w.document.createElement('style')
  style.textContent = PRINT_CSS
  w.document.head.appendChild(style)
  const host = w.document.createElement('div')
  w.document.body.appendChild(host)
  createRoot(host).render(
    <>
      <h1>{r.question || '研究'}</h1>
      <p className="meta">WealthPilot · {stamp(r.when)} · 不构成投资建议</p>
      <Markdown remarkPlugins={[remarkGfm]}>{r.answer.replace(/\[(E-[a-f0-9]+)\]/g, (_, id: string) => `\`${short(id)}\``)}</Markdown>
      {r.evidence?.length ? (
        <>
          <h2>证据</h2>
          <ul className="evidence">{r.evidence.map((e) => <li key={e.id}><code>{short(e.id)}</code> {e.tool}：{flat(e.output)}</li>)}</ul>
        </>
      ) : null}
    </>,
  )
  setTimeout(() => { w.focus(); w.print() }, 400)
  return true
}

/** 一次研究的两个出口：存成 Markdown 文件，或者打印 / 存成 PDF。都在浏览器里完成，不经过服务器。 */
export const ExportButtons: React.FC<{ item: Exportable; className?: string }> = ({ item, className }) => {
  const [blocked, setBlocked] = useState(false)
  const link = 'text-[13px] text-slate underline underline-offset-2 hover:text-ink'
  return (
    <span className={className} onClick={(e) => e.stopPropagation()}>
      <button type="button" className={link} onClick={() => download(exportName(item), researchMarkdown(item))}>存成 Markdown</button>
      <span className="mx-1.5 text-stone">·</span>
      <button type="button" className={link} title="在打印对话框里选「存储为 PDF」" onClick={() => setBlocked(!print(item))}>打印 / 存成 PDF</button>
      {blocked ? <span className="ml-2 text-[13px] text-on-rose">浏览器拦住了新窗口，允许弹出窗口后再点一次</span> : null}
    </span>
  )
}
