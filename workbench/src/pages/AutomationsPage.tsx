/** 自动任务：到点自己跑的研究，和越过条件就提醒的盯价。 */
import type React from 'react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BellPlus, CalendarPlus } from 'lucide-react'
import { DEMO, api, useApi, type Automation, type Security } from '../api'
import { SecuritySearch } from '../components/SecuritySearch'
import { Button, Callout, ConfirmDialog, Drawer, Input, Select, Tag, type Tone } from '../components/kit'
import { DataState, Page, Section } from '../components/ui'

// 不知道从哪开始的时候，点一个就能用；之后可以改
const PRESETS = [
  { schedule: '工作日 08:30', prompt: '帮我诊断一下我的持仓，有什么需要注意的', depth: 'auto' },
  { schedule: '每周五 16:00', prompt: '复盘一下之前的研究：验证点成立了多少，哪些判断被证伪了', depth: 'auto' },
  { schedule: '每周一 09:00', prompt: '帮我筛选市盈率低于15、ROE高于15%的大市值股票', depth: 'auto' },
]
const DEPTH = [{ value: 'auto', label: '自动' }, { value: 'quick', label: '快速（十几秒，简短）' }, { value: 'deep', label: '深入（完整研究）' }]
const STATUS: Record<string, { label: string; tone: Tone }> = {
  ok: { label: '已完成', tone: 'green' }, failed: { label: '没跑成', tone: 'pink' }, skipped: { label: '跳过', tone: 'yellow' }, fired: { label: '已触发', tone: 'pink' },
}
const when = (iso?: string | null) => (iso ? iso.slice(5, 16).replace('T', ' ') : '')

type TaskForm = { id?: number; prompt: string; schedule: string; depth: string }
type AlertForm = { code: string; name: string; metric: string; op: string; threshold: string; repeat: boolean }

const AutomationsPage: React.FC = () => {
  const list = useApi(api.automations)
  const [task, setTask] = useState<TaskForm | null>(null)
  const [alert, setAlert] = useState<AlertForm | null>(null)
  const [read, setRead] = useState<{ text: string; ok: boolean } | null>(null)
  const [busy, setBusy] = useState<number | 'form' | null>(null)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger' | 'info'; text: string } | null>(null)
  const [error, setError] = useState('')
  const [removing, setRemoving] = useState<Automation | null>(null)
  const data = list.data
  const tasks = (data?.items ?? []).filter((a) => a.kind === 'task')
  const alerts = (data?.items ?? []).filter((a) => a.kind === 'alert')
  const unit = (metric: string) => data?.metrics.find((m) => m.key === metric)?.unit ?? ''

  // 用户写的时间，读成了什么当场给他看 —— 读错了比不能写更糟
  const scheduleText = task?.schedule ?? ''
  useEffect(() => {
    if (!scheduleText.trim()) { setRead(null); return undefined }
    let alive = true
    const timer = setTimeout(() => {
      api.parseSchedule(scheduleText).then((r) => { if (alive) setRead({ text: r.text, ok: true }) })
        .catch((e) => { if (alive) setRead({ text: e instanceof Error ? e.message : '没看懂时间', ok: false }) })
    }, 300)
    return () => { alive = false; clearTimeout(timer) }
  }, [scheduleText])

  const act = async (key: number | 'form', work: () => Promise<string | void>) => {
    setBusy(key); setError(''); setMessage(null)
    try {
      const text = await work()
      if (text) setMessage({ tone: 'success', text })
      list.reload()
    } catch (e) {
      const text = e instanceof Error ? e.message : '操作失败'
      if (key === 'form') setError(text); else setMessage({ tone: 'danger', text })
    } finally { setBusy(null) }
  }
  const saveTask = (form: TaskForm) => act('form', async () => {
    await api.saveAutomation({ kind: 'task', prompt: form.prompt, schedule: form.schedule, depth: form.depth }, form.id)
    setTask(null)
    return form.id ? '已保存' : '已建好。到点会自己跑；也可以点「现在跑一次」先看看效果'
  })
  const saveAlert = (form: AlertForm) => act('form', async () => {
    const saved = await api.saveAutomation({ kind: 'alert', code: form.code, name: form.name, metric: form.metric, op: form.op, threshold: Number(form.threshold), repeat: form.repeat })
    setAlert(null)
    if (saved.current == null) return `已建好：${saved.condition}`
    return `已建好：${saved.condition}。现在是 ${saved.current}${saved.unit ?? ''}${saved.hit ? '，已经满足条件，下次检查时就会提醒' : ''}`
  })
  const runNow = (a: Automation) => act(a.id, async () => {
    const r = await api.runAutomation(a.id)
    if (a.kind === 'task') return r.last_status === 'ok' ? `「${a.title}」跑完了，结论在下面` : `「${a.title}」没跑成：${r.last_result}`
    return r.current == null ? '现在取不到这个数' : `${a.condition}：现在是 ${r.current}${a.unit ?? ''}，${r.hit ? '已经满足条件' : '还没到'}`
  })
  const toggle = (a: Automation) => act(a.id, async () => { await api.saveAutomation({ enabled: !a.enabled }, a.id) })

  if (DEMO) {
    return <Page title="自动任务" description="到点自己研究、越过条件就提醒"><Callout tone="info">在线演示没有后端，这一页在本地运行后可用。</Callout></Page>
  }
  return (
    <Page title="自动任务" description="让它到点自己干活：定时做一次研究，或者在某只股票越过你设的条件时提醒你" terms={['自动任务', '历史分位']}>
      {data && !data.running ? (
        <Callout tone="warning" action={<Link to="/settings" className="text-[13px] font-medium underline underline-offset-2">去设置</Link>}>
          自动盯盘现在是关着的，任务和提醒都不会自己跑。
        </Callout>
      ) : (
        <Callout tone="neutral">只在 WealthPilot 开着的时候运行，不会在后台常驻。电脑合着盖错过了时间，下次打开时会把最近错过的那一次补上。结果会出现在「今日」页；绑定了手机的话同时推到手机。</Callout>
      )}
      {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

      <Section title="定时任务" hint={data ? `到点自动做一次研究（会调用模型）。每天最多自动跑 ${data.daily_runs_max} 次，手动点的不算` : undefined}
        actions={<Button size="sm" onClick={() => { setError(''); setTask({ prompt: '', schedule: '工作日 08:30', depth: 'auto' }) }}><CalendarPlus className="h-4 w-4" />新建任务</Button>}>
        <DataState loading={list.loading && !data} error={list.error} onRetry={list.reload}>
          {tasks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-hairline-strong p-4">
              <p className="text-sm text-charcoal">还没有任务。可以从这几个常用的开始，点一下就建好：</p>
              <div className="mt-3 flex flex-col gap-2">
                {PRESETS.map((p) => (
                  <button key={p.prompt} type="button" disabled={busy != null} onClick={() => void saveTask(p)}
                    className="flex items-baseline gap-3 rounded-md border border-hairline px-3 py-2 text-left text-sm transition-colors hover:bg-surface-soft disabled:opacity-60">
                    <span className="w-28 shrink-0 font-mono text-[13px] text-steel">{p.schedule}</span>
                    <span className="min-w-0 text-ink">{p.prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
              {tasks.map((a) => (
                <li key={a.id} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[13px] text-steel">{a.schedule}</span>
                    <span className="min-w-0 text-sm font-medium text-ink">{a.prompt}</span>
                    {a.depth !== 'auto' ? <Tag className="!py-0">{a.depth === 'quick' ? '快速' : '深入'}</Tag> : null}
                    {!a.enabled ? <Tag tone="yellow" className="!py-0">已暂停</Tag> : null}
                    <span className="ml-auto flex shrink-0 gap-1">
                      <Button size="xs" variant="secondary" loading={busy === a.id} disabled={busy != null} onClick={() => void runNow(a)}>现在跑一次</Button>
                      <Button size="xs" variant="ghost" disabled={busy != null} onClick={() => void toggle(a)}>{a.enabled ? '暂停' : '启用'}</Button>
                      <Button size="xs" variant="ghost" onClick={() => { setError(''); setTask({ id: a.id, prompt: a.prompt ?? '', schedule: a.schedule ?? '', depth: a.depth ?? 'auto' }) }}>编辑</Button>
                      <Button size="xs" variant="danger" onClick={() => setRemoving(a)}>删除</Button>
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-steel">
                    {busy === a.id ? '正在研究，大约一分钟…'
                      : a.last_run_at ? (
                        <>
                          <Tag tone={STATUS[a.last_status]?.tone} className="mr-2 !py-0">{STATUS[a.last_status]?.label ?? a.last_status}</Tag>
                          <span className="font-mono text-xs text-stone">{when(a.last_run_at)}</span>
                          <span className="ml-2 text-charcoal">{a.last_result}</span>
                          {a.last_status === 'ok' && a.last_message_id ? <Link to={`/history/${a.last_message_id}`} className="ml-2 text-link hover:underline">看全文</Link> : null}
                        </>
                      ) : '还没跑过。'}
                    {a.enabled && a.next_run_at && busy !== a.id ? <span className="ml-2 text-stone">下次 {when(a.next_run_at)}</span> : null}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </Section>

      <Section title="提醒" hint="某只股票的价格、涨跌幅或估值分位越过你设的条件时提醒一次。只取行情，不调用模型"
        actions={<Button size="sm" variant="secondary" onClick={() => { setError(''); setAlert({ code: '', name: '', metric: 'price', op: '<=', threshold: '', repeat: false }) }}><BellPlus className="h-4 w-4" />新建提醒</Button>}>
        <DataState loading={list.loading && !data} error={list.error}
          empty={data && alerts.length === 0 ? '还没有提醒。比如：贵州茅台跌到 1350 元以下告诉我；宁德时代的 PE 分位低于 20% 告诉我。' : undefined}>
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline">
            {alerts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
                <Link to={`/stock/${a.code}`} className="font-medium text-ink hover:underline">{a.name || a.code}</Link>
                <span className="text-charcoal">{(a.condition ?? '').replace(a.name || a.code || '', '').trim()}</span>
                {a.repeat ? <Tag className="!py-0">每天最多一次</Tag> : null}
                {a.last_status === 'fired' ? <Tag tone="pink" className="!py-0">已触发 {when(a.last_run_at)}</Tag> : null}
                {!a.enabled ? <Tag tone="yellow" className="!py-0">{a.last_status === 'fired' ? '提醒过了，已停' : '已暂停'}</Tag> : null}
                <span className="ml-auto flex shrink-0 gap-1">
                  <Button size="xs" variant="secondary" loading={busy === a.id} disabled={busy != null} onClick={() => void runNow(a)}>现在看一眼</Button>
                  <Button size="xs" variant="ghost" disabled={busy != null} onClick={() => void toggle(a)}>{a.enabled ? '暂停' : '重新打开'}</Button>
                  <Button size="xs" variant="danger" onClick={() => setRemoving(a)}>删除</Button>
                </span>
                {a.last_status === 'fired' && a.last_result ? <p className="w-full text-[13px] text-steel">{a.last_result}</p> : null}
              </li>
            ))}
          </ul>
        </DataState>
        <p className="mt-2 text-[13px] text-steel">开盘时间每 5 分钟看一次。价格和涨跌幅用实时行情；估值分位每天更新一次。</p>
      </Section>

      <Drawer open={task != null} onClose={() => setTask(null)} title={task?.id ? '编辑任务' : '新建任务'}>
        {task ? (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void saveTask(task) }}>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="auto-prompt" className="text-[13px] font-medium text-slate">到点要问它什么</label>
              <textarea id="auto-prompt" rows={3} value={task.prompt} onChange={(e) => setTask({ ...task, prompt: e.target.value })}
                placeholder="复盘一下我的持仓，今天有什么需要注意的"
                className="w-full resize-y rounded-md border border-hairline-strong bg-canvas px-3 py-2 text-sm text-ink outline-none placeholder:text-stone focus:border-primary focus:ring-1 focus:ring-primary" />
              <p className="text-xs text-steel">和在「AI 研究」里提问一样写。它会用当时最新的数据重新查一遍。</p>
            </div>
            <div>
              <Input id="auto-when" label="什么时候" value={task.schedule} onChange={(e) => setTask({ ...task, schedule: e.target.value })} placeholder="工作日 08:30" />
              <p className={`mt-1.5 text-xs ${read && !read.ok ? 'text-on-rose' : 'text-steel'}`}>
                {read ? (read.ok ? `读作：${read.text}` : read.text) : '可以写：每天 08:30、工作日 15:40、每周一 09:00、每周一三五 9点半'}
              </p>
            </div>
            <Select id="auto-depth" label="查多深" value={task.depth} onChange={(v) => setTask({ ...task, depth: v })} options={DEPTH} />
            {error ? <Callout tone="danger">{error}</Callout> : null}
            <div className="flex gap-2">
              <Button type="submit" loading={busy === 'form'} disabled={!task.prompt.trim() || (read != null && !read.ok)}>保存</Button>
              <Button variant="ghost" onClick={() => setTask(null)}>取消</Button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <Drawer open={alert != null} onClose={() => setAlert(null)} title="新建提醒">
        {alert ? (
          <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); void saveAlert(alert) }}>
            <div className="flex flex-col gap-1.5">
              <span className="text-[13px] font-medium text-slate">盯哪只</span>
              {alert.code
                ? <p className="flex items-center gap-2 text-sm text-ink">{alert.name}<span className="font-mono text-xs text-stone">{alert.code}</span>
                  <Button size="xs" variant="ghost" onClick={() => setAlert({ ...alert, code: '', name: '' })}>换一只</Button></p>
                : <SecuritySearch placeholder="搜索股票或 ETF" onPick={(s: Security) => setAlert({ ...alert, code: s.code, name: s.name })} />}
            </div>
            <div className="grid grid-cols-[1fr_auto] gap-3">
              <Select id="al-metric" label="看什么" value={alert.metric} onChange={(v) => setAlert({ ...alert, metric: v })}
                options={(data?.metrics ?? []).map((m) => ({ value: m.key, label: m.label }))} />
              <Select id="al-op" label="条件" value={alert.op} onChange={(v) => setAlert({ ...alert, op: v })}
                options={[{ value: '<=', label: '低于或等于' }, { value: '>=', label: '高于或等于' }]} />
            </div>
            <Input id="al-value" label={`多少${unit(alert.metric) ? `（${unit(alert.metric)}）` : ''}`} type="number" step="any" value={alert.threshold}
              onChange={(e) => setAlert({ ...alert, threshold: e.target.value })}
              hint={alert.metric.endsWith('_percentile') ? '0% 是它自己历史上最便宜的时候，100% 是最贵的时候' : alert.metric === 'change_pct' ? '当日涨跌幅，跌用负数，比如 -5' : undefined} />
            <label className="flex cursor-pointer items-start gap-2 text-sm text-charcoal">
              <input type="checkbox" checked={alert.repeat} onChange={(e) => setAlert({ ...alert, repeat: e.target.checked })} className="mt-0.5 h-4 w-4 accent-[var(--primary)]" />
              <span>触发后继续盯<span className="block text-xs text-steel">不勾：提醒一次就停，免得在这个价位附近来回提醒。勾上：每天最多提醒一次。</span></span>
            </label>
            {error ? <Callout tone="danger">{error}</Callout> : null}
            <div className="flex gap-2">
              <Button type="submit" loading={busy === 'form'} disabled={!alert.code || alert.threshold === ''}>保存</Button>
              <Button variant="ghost" onClick={() => setAlert(null)}>取消</Button>
            </div>
          </form>
        ) : null}
      </Drawer>

      <ConfirmDialog open={removing != null} title="删除" confirmText="删除" message={removing ? `删除「${removing.title}」？` : ''}
        onCancel={() => setRemoving(null)}
        onConfirm={() => { const t = removing; setRemoving(null); if (t) void act(t.id, async () => { await api.removeAutomation(t.id) }) }} />
    </Page>
  )
}

export default AutomationsPage
