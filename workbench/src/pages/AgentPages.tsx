/** Agent 的三个"可调教、可追责"的页面：研究方法（技能）、AI 记住的事（记忆）、审计日志。 */
import type React from 'react'
import { useState } from 'react'
import { DEMO, api, useApi, type MemoryItem, type SkillInfo, type SkillPreview } from '../api'
import { AskAi } from '../components/AskAi'
import { Button, Callout, ConfirmDialog, Drawer, Input, Tag, type Tone } from '../components/kit'
import { DataState, Page, Section, Table, Td } from '../components/ui'

const AGENT_LABEL: Record<string, string> = { fundamental: '基本面', valuation: '估值', price: '走势', industry: '行业与市场', capital: '资金与筹码', expectation: '预期与消息', screener: '选股', portfolio: '组合与风险', fund: '基金' }
const NEEDS: Record<string, string> = { stock: '一只股票', stocks: '多只股票', holdings: '我的持仓', none: '不需要标的' }

export const SkillsPage: React.FC = () => {
  const list = useApi(api.skills)
  const [editing, setEditing] = useState<{ name: string; content: string; isNew: boolean; origin?: string } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState<SkillInfo | null>(null)
  const data = list.data

  const gallery = useApi(api.skillGallery)
  const [url, setUrl] = useState('')
  const [want, setWant] = useState('')
  const [working, setWorking] = useState('')
  const [notice, setNotice] = useState('')
  // 外面来的方法（链接、AI 起草）都是写给 Agent 的指示：先放进编辑器让用户看过，他点保存才落盘
  const review = (preview: SkillPreview, origin: string) => {
    setError(preview.problems.length ? `这份文件还有问题，改好才能保存：${preview.problems.join('；')}` : '')
    setEditing({ name: preview.skill?.name ?? 'my-method', content: preview.content, isNew: true, origin })
  }
  const fetchLink = async () => {
    setWorking('link'); setError('')
    try { review(await api.importSkill(url.trim()), `来自 ${url.trim()}`); setUrl('') } catch (e) { setError(e instanceof Error ? e.message : '导入失败') } finally { setWorking('') }
  }
  const draft = async () => {
    setWorking('draft'); setError('')
    try { review(await api.draftSkill(want.trim()), 'AI 起草'); setWant('') } catch (e) { setError(e instanceof Error ? e.message : '起草失败') } finally { setWorking('') }
  }
  const install = async (name: string, label: string) => {
    setWorking(name); setError(''); setNotice('')
    try { await api.installGallerySkill(name); list.reload(); gallery.reload(); setNotice(`已装上「${label}」。在提问时说出它的触发词就会用上，也可以点「编辑」改成你自己的做法。`) }
    catch (e) { setError(e instanceof Error ? e.message : '安装失败') } finally { setWorking('') }
  }
  const available = (gallery.data ?? []).filter((g) => !g.installed)

  const open = async (name: string) => {
    setError('')
    try { const s = await api.skill(name); setEditing({ name, content: s.content ?? '', isNew: false }) } catch (e) { setError(e instanceof Error ? e.message : '读取失败') }
  }
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editing) return
    const name = editing.content.match(/^name:\s*([a-z0-9-]+)\s*$/m)?.[1] ?? editing.name
    setBusy(true); setError('')
    try { await api.saveSkill(name, editing.content); setEditing(null); list.reload() } catch (err) { setError(err instanceof Error ? err.message : '保存失败') } finally { setBusy(false) }
  }

  return (
    <Page title="研究方法" description="把你自己的方法写成一个文件教给 AI：什么时候用、派谁去查、各自查什么、报告分哪几节"
      actions={DEMO || !data ? undefined : <Button size="sm" onClick={() => { setError(''); setEditing({ name: 'my-method', content: data.template, isNew: true }) }}>新建方法</Button>}>
      {error && !editing ? <Callout tone="danger">{error}</Callout> : null}
      {notice ? <Callout tone="success">{notice}</Callout> : null}
      <Section title="已有的方法" hint="话里出现触发词或方法名时，AI 会按它来研究，而不是自己另行规划">
        <DataState loading={list.loading} error={list.error} onRetry={list.reload}
          empty={data && data.skills.length === 0 ? '还没有方法。点右上角「新建方法」，或把 .md 文件放进技能目录。' : undefined}>
          <div className="flex flex-col gap-3">
            {(data?.skills ?? []).map((s) => (
              <div key={s.name} className="rounded-lg border border-hairline p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold text-ink">{s.label}</span>
                  <code className="font-mono text-xs text-stone">{s.name}</code>
                  <Tag>{NEEDS[s.needs] ?? s.needs}</Tag>
                  {s.agents.map((a) => <Tag key={a} tone="purple" className="!py-0">{AGENT_LABEL[a] ?? a}</Tag>)}
                  <span className="ml-auto flex gap-2">
                    {s.needs === 'stock' || s.needs === 'stocks' ? <AskAi label="试一下" question={`用「${s.label}」的方法看看贵州茅台`} /> : null}
                    {DEMO ? null : <Button size="sm" variant="ghost" onClick={() => void open(s.name)}>编辑</Button>}
                    {DEMO ? null : <Button size="sm" variant="danger" onClick={() => setRemoving(s)}>删除</Button>}
                  </span>
                </div>
                <p className="mt-2 text-sm text-charcoal">{s.description}</p>
                <p className="mt-2 text-[13px] text-steel">触发词：{s.triggers.join('、') || '（无，靠方法名触发）'}</p>
                <p className="mt-0.5 text-[13px] text-steel">报告章节：{s.sections.join(' / ')}</p>
              </div>
            ))}
          </div>
        </DataState>
        {data?.invalid.length ? (
          <Callout tone="warning" title="这些文件没有被加载" className="mt-4">
            <ul className="list-disc space-y-1 pl-4">{data.invalid.map((x) => <li key={x.path}><code className="font-mono text-xs">{x.path.split('/').slice(-1)[0]}</code>：{x.problems.join('；')}</li>)}</ul>
          </Callout>
        ) : null}
        {data ? <p className="mt-3 text-[13px] text-steel">文件放在 <code className="font-mono text-xs">{data.dirs[0]}</code>。格式与 DeepSeek Harness 的 skill 相同（YAML frontmatter + Markdown 正文），编排信息写在 <code className="font-mono text-xs">metadata.wealthpilot</code> 下。</p> : null}
      </Section>

      {DEMO ? null : (
        <Section title="添加方法" hint="不用从空白文件写起">
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-hairline p-4">
              <p className="text-sm font-medium text-ink">说一句，让 AI 起草</p>
              <p className="mt-0.5 text-[13px] text-steel">描述你买一只股票前固定要看什么。起草出来的文件会先给你看，改完再保存。</p>
              <textarea value={want} onChange={(e) => setWant(e.target.value)} rows={3} aria-label="描述你的方法"
                placeholder="比如：我买消费股之前固定看三件事——毛利率稳不稳、渠道有没有压货、估值是不是在历史低位"
                className="mt-3 w-full resize-y rounded-md border border-hairline-strong bg-canvas px-3 py-2 text-sm text-ink outline-none placeholder:text-stone focus:border-primary focus:ring-1 focus:ring-primary" />
              <Button size="sm" className="mt-2" loading={working === 'draft'} disabled={want.trim().length < 6} onClick={() => void draft()}>起草</Button>
            </div>
            <div className="rounded-lg border border-hairline p-4">
              <p className="text-sm font-medium text-ink">从链接导入</p>
              <p className="mt-0.5 text-[13px] text-steel">别人分享的方法文件（.md）。支持 GitHub 上的文件地址；格式和 DeepSeek Harness 的 skill 相同。</p>
              <div className="mt-3"><Input id="skill-url" aria-label="方法文件的链接" placeholder="https://github.com/…/blob/main/skills/xxx.md" value={url} onChange={(e) => setUrl(e.target.value)} /></div>
              <Button size="sm" variant="secondary" className="mt-2" loading={working === 'link'} disabled={!/^https:\/\//.test(url.trim())} onClick={() => void fetchLink()}>取回并查看</Button>
              <p className="mt-2 text-xs text-stone">方法文件是写给 AI 的指示。取回后先给你看内容，你点保存才会生效。</p>
            </div>
          </div>
          {available.length > 0 ? (
            <div className="mt-4">
              <p className="mb-2 text-[13px] font-medium text-steel">现成的方法 · 点一下就装上，之后可以随便改</p>
              <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
                {available.map((g) => (
                  <li key={g.name} className="flex items-center gap-3 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-ink"><span className="font-medium">{g.label}</span><Tag className="ml-2 !py-0">{NEEDS[g.needs] ?? g.needs}</Tag></p>
                      <p className="mt-0.5 truncate text-[13px] text-steel">{g.description.startsWith(g.label) ? g.description.slice(g.label.length).replace(/^[\s—–\-:：]+/, '') : g.description}</p>
                    </div>
                    <Button size="xs" variant="secondary" loading={working === g.name} disabled={working !== ''} onClick={() => void install(g.name, g.label)}>装上</Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Section>
      )}

      <Drawer open={editing != null} onClose={() => setEditing(null)} title={editing?.isNew ? (editing.origin ? `查看并保存 · ${editing.origin.startsWith('来自') ? '导入的方法' : editing.origin}` : '新建方法') : `编辑 ${editing?.name ?? ''}`} width="max-w-3xl">
        {editing ? (
          <form className="flex h-full flex-col gap-3" onSubmit={save}>
            {editing.origin ? <Callout tone="warning">{editing.origin.startsWith('来自') ? `${editing.origin}。` : '这是 AI 按你的描述起草的。'}它会决定 AI 以后怎么研究：读一遍，确认是你想要的做法再保存。</Callout> : null}
            <p className="text-[13px] text-steel">上半部分（两条 --- 之间）是配置，下半部分是写给 AI 的做法。正文里 <code className="font-mono text-xs">- fundamental: ……</code> 这样的行是给对应 Agent 的具体指示。</p>
            <textarea value={editing.content} onChange={(e) => setEditing({ ...editing, content: e.target.value })} spellCheck={false} aria-label="方法文件内容"
              className="min-h-[420px] flex-1 resize-y rounded-md border border-hairline bg-surface-soft p-3 font-mono text-[13px] leading-relaxed text-ink outline-none focus:border-primary" />
            {error ? <Callout tone="danger">{error}</Callout> : null}
            <div className="flex gap-2"><Button type="submit" loading={busy}>保存</Button><Button variant="ghost" onClick={() => setEditing(null)}>取消</Button></div>
          </form>
        ) : null}
      </Drawer>
      <ConfirmDialog open={removing != null} title="删除方法" confirmText="删除" message={removing ? `删除「${removing.label}」？文件会从技能目录移除。` : ''}
        onCancel={() => setRemoving(null)}
        onConfirm={() => { const t = removing; setRemoving(null); if (t) api.removeSkill(t.name).then(list.reload).catch((e) => setError(e instanceof Error ? e.message : '删除失败')) }} />
    </Page>
  )
}

const KIND: Record<string, { label: string; tone: Tone }> = { preference: { label: '偏好', tone: 'purple' }, decision: { label: '决定', tone: 'blue' }, note: { label: '备注', tone: 'gray' } }

export const MemoryPage: React.FC = () => {
  const list = useApi(api.memory)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const run = (work: Promise<unknown>) => work.then(() => { setDraft(''); setError(''); list.reload() }).catch((e) => setError(e instanceof Error ? e.message : '操作失败'))
  const rows = list.data ?? []
  return (
    <Page title="AI 记住的事" description="你说过的偏好和纪律、你对建议做过的决定。每次研究都会带上；不想让它记的可以删掉">
      {DEMO ? null : (
        <form className="flex max-w-2xl items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) void run(api.addMemory(draft.trim())) }}>
          <div className="flex-1"><Input id="mem-new" label="告诉它一件要记住的事" placeholder="比如：我只做长线，单只股票不超过两成仓位" value={draft} onChange={(e) => setDraft(e.target.value)} /></div>
          <Button type="submit" className="h-10" disabled={!draft.trim()}>记住</Button>
        </form>
      )}
      {error ? <Callout tone="danger">{error}</Callout> : null}
      <Section title="记忆" hint={rows.length ? `${rows.length} 条` : undefined}>
        <DataState loading={list.loading} error={list.error} onRetry={list.reload}
          empty={rows.length === 0 ? '还没有。在提问时说「记住，……」或「我不碰……」这样的话会被记下来；采纳或不采纳一条建议也会记一笔。' : undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {rows.map((m: MemoryItem) => (
              <li key={m.id} className="flex items-baseline gap-3 px-4 py-2.5 text-sm">
                <Tag tone={KIND[m.kind]?.tone}>{KIND[m.kind]?.label ?? m.kind}</Tag>
                <span className="min-w-0 flex-1 text-charcoal">{m.content}{m.code ? <span className="ml-2 font-mono text-xs text-stone">{m.code}</span> : null}</span>
                <span className="shrink-0 font-mono text-xs text-stone">{m.created_at.slice(0, 10)}</span>
                {DEMO ? null : <Button size="xs" variant="ghost" onClick={() => void run(api.removeMemory(m.id))}>忘掉</Button>}
              </li>
            ))}
          </ul>
        </DataState>
        <p className="mt-3 text-[13px] text-steel">只记你的原话，不让模型替你总结偏好。针对某只股票的决定只在研究那只股票时带上。</p>
      </Section>
    </Page>
  )
}

const AUDIT: Record<string, { label: string; tone: Tone }> = {
  research: { label: '研究', tone: 'purple' }, checkpoint: { label: '验证点', tone: 'blue' }, approval: { label: '审批', tone: 'pink' }, order: { label: '委托', tone: 'orange' },
  holdings: { label: '持仓', tone: 'green' }, settings: { label: '配置', tone: 'yellow' }, memory: { label: '记忆', tone: 'gray' },
}
const ACTOR: Record<string, string> = { user: '你', agent: 'AI', system: '系统' }

export const AuditPage: React.FC = () => {
  const log = useApi(api.audit)
  const d = log.data
  return (
    <Page title="审计日志" description="AI 提过什么建议、你怎么决定的、下过哪些单、改过哪些配置。只追加，不能修改或删除">
      <DataState loading={log.loading} error={log.error} onRetry={log.reload}>
        {d ? (
          <>
            <Callout tone={d.integrity.ok ? 'success' : 'danger'}>
              {d.integrity.ok ? `共 ${d.integrity.count} 条记录，哈希链校验通过：没有被改动或删除过。` : `校验失败：第 ${d.integrity.broken_at} 条记录与前后对不上，日志被改动过。`}
            </Callout>
            <Section title="记录" hint="新的在前">
              <DataState empty={d.events.length === 0 ? '还没有记录。' : undefined}>
                <Table minWidth={760} head={[{ label: '时间' }, { label: '类型' }, { label: '谁' }, { label: '内容' }, { label: '指纹', right: true }]}>
                  {d.events.map((e) => {
                    const domain = e.kind.split('/')[0]
                    return (
                      <tr key={e.id}>
                        <Td className="whitespace-nowrap font-mono text-xs text-stone">{e.at.slice(0, 19).replace('T', ' ')}</Td>
                        <Td className="whitespace-nowrap"><Tag tone={AUDIT[domain]?.tone}>{AUDIT[domain]?.label ?? domain}</Tag><code className="ml-2 font-mono text-xs text-steel">{e.kind}</code></Td>
                        <Td>{ACTOR[e.actor] ?? e.actor}</Td>
                        <Td className="text-charcoal">{e.summary}</Td>
                        <Td right className="font-mono text-xs text-stone">{e.hash}</Td>
                      </tr>
                    )
                  })}
                </Table>
              </DataState>
            </Section>
          </>
        ) : null}
      </DataState>
    </Page>
  )
}
