import type React from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** 回答正文。证据引用 [E-xxxx] 渲染成可点击的小标签，点了定位到对应的工具返回。 */
export const AnswerMarkdown: React.FC<{ content: string; onCite?: (id: string) => void }> = ({ content, onCite }) => {
  const linked = content.replace(/\[(E-[a-f0-9]+)\]/g, (_, id: string) => `[${id.slice(2, 6)}](#cite-${id})`)
  return (
    <div className="prose-answer">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith('#cite-')) {
              const id = href.slice(6)
              return (
                <button type="button" title="查看这条证据" onClick={(e) => { e.stopPropagation(); onCite?.(id) }}
                  className="mx-0.5 inline-flex items-center rounded-xs bg-tint-lavender px-1 align-[1px] font-mono text-[11px] leading-4 text-on-lavender hover:brightness-95">
                  {children}
                </button>
              )
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>
          },
          table: ({ children }) => <div className="overflow-x-auto"><table>{children}</table></div>,
        }}
      >
        {linked}
      </Markdown>
    </div>
  )
}
