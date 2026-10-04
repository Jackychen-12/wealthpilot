import type { ReactNode } from 'react'

/** 回答正文的轻量 Markdown 渲染：标题、列表、表格、引用、分隔线、粗体、行内代码、证据引用。 */

function inline(text: string, onCite?: (id: string) => void): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[E-[a-f0-9]+\])/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className="md-code">{p.slice(1, -1)}</code>
    const cite = p.match(/^\[(E-[a-f0-9]+)\]$/)
    if (cite) {
      return (
        <button key={i} type="button" className="cite-chip" title={`证据 ${cite[1]}`} onClick={() => onCite?.(cite[1])}>
          {cite[1].slice(2, 6)}
        </button>
      )
    }
    return p
  })
}

const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l)
const isListItem = (l: string) => /^\s*([-*]|\d+[.)])\s+/.test(l)

export function Markdown({ text, onCite }: { text: string; onCite?: (id: string) => void }) {
  const lines = text.split('\n')
  const out: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (isTableRow(line)) {
      const rows: string[] = []
      while (i < lines.length && isTableRow(lines[i])) rows.push(lines[i++])
      const body = rows.filter(r => !/^\s*\|[\s:|-]+\|\s*$/.test(r)).map(r => r.trim().slice(1, -1).split('|').map(c => c.trim()))
      out.push(
        <div key={out.length} className="md-table-wrap">
          <table className="md-table">
            <tbody>
              {body.map((cells, r) => (
                <tr key={r}>
                  {cells.map((c, k) => (r === 0 ? <th key={k}>{inline(c, onCite)}</th> : <td key={k}>{inline(c, onCite)}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    if (isListItem(line)) {
      const items: string[] = []
      while (i < lines.length && isListItem(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+[.)])\s+/, ''))
      out.push(<ul key={out.length} className="md-list">{items.map((t, k) => <li key={k}>{inline(t, onCite)}</li>)}</ul>)
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.*)/)
    if (heading) out.push(<div key={out.length} className={heading[1].length <= 2 ? 'md-h1' : 'md-h2'}>{inline(heading[2], onCite)}</div>)
    else if (/^\s*---+\s*$/.test(line)) out.push(<div key={out.length} className="md-hr" />)
    else if (/^\s*>/.test(line)) out.push(<div key={out.length} className="md-quote">{inline(line.replace(/^\s*>\s?/, ''), onCite)}</div>)
    else if (line.trim()) out.push(<p key={out.length} className="md-p">{inline(line, onCite)}</p>)
    i++
  }
  return <div className="md">{out}</div>
}
