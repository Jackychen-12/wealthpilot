import type React from 'react'
import { useEffect, useState } from 'react'
import { DEMO, api, useApi, type AppSettings, type DoctorItem } from '../api'
import { ValueBars } from '../components/charts'
import { Button, Callout, Input, Select, Tag } from '../components/kit'
import { DataState, Page, Section } from '../components/ui'

type Values = Record<string, string | number | boolean>

const Toggle: React.FC<{ label: string; hint: string; checked: boolean; onChange: (v: boolean) => void; locked?: boolean }> = ({ label, hint, checked, onChange, locked }) => (
  <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-hairline p-4">
    <input type="checkbox" checked={checked} disabled={locked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--primary)]" />
    <span className="min-w-0">
      <span className="block text-sm font-medium text-ink">{label}{locked ? <Tag tone="yellow" className="ml-2 !py-0">由环境变量指定</Tag> : null}</span>
      <span className="mt-0.5 block text-[13px] leading-relaxed text-steel">{hint}</span>
    </span>
  </label>
)

/**
 * 手机触达：绑定一个 Telegram 机器人。令牌和其他设置一起保存；绑定哪个聊天靠配对码 ——
 * 在这里生成，在 Telegram 里发给机器人，谁发对了谁就是主人。
 */
const Reach: React.FC<{ data: AppSettings; token: string; onToken: (v: string) => void; base: string; onBase: (v: string) => void }> = ({ data, token, onToken, base, onBase }) => {
  const channel = useApi(api.channel)
  const [code, setCode] = useState('')
  const [note, setNote] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [busy, setBusy] = useState('')
  const saved = data.secrets.telegram_bot_token?.set
  const paired = channel.data?.paired
  const reload = channel.reload
  // 配对码亮着的时候每 3 秒看一眼：用户在手机上发完，这里自己变成“已绑定”
  useEffect(() => {
    if (!code || paired) return undefined
    const timer = setInterval(reload, 3000)
    return () => clearInterval(timer)
  }, [code, paired, reload])
  useEffect(() => { if (paired) setCode('') }, [paired])
  const act = async (key: string, work: () => Promise<void>) => {
    setBusy(key); setNote(null)
    try { await work() } catch (e) { setNote({ tone: 'danger', text: e instanceof Error ? e.message : '操作失败' }) } finally { setBusy('') }
  }
  return (
    <Section title="手机触达" hint="在手机上收每日简报和提醒、直接提问、处理建议单">
      <div className="grid max-w-2xl gap-3">
        <Input id="s-tg" label="Telegram 机器人令牌" type="password" autoComplete="off"
          placeholder={saved ? `已配置（${data.secrets.telegram_bot_token.hint}），留空表示不改` : '粘贴令牌，然后点页面底部的「保存」'}
          hint="在 Telegram 里找 @BotFather，发 /newbot，按提示起个名字，它会回你一串令牌。这个机器人只属于你。"
          value={token} onChange={(e) => onToken(e.target.value)} />
        <details className="text-[13px] text-steel">
          <summary className="cursor-pointer select-none hover:text-ink">本机连不上 Telegram？</summary>
          <div className="mt-2"><Input id="s-tgbase" label="接口地址" value={base} onChange={(e) => onBase(e.target.value)} hint="默认 https://api.telegram.org。需要走中转时改成你的中转地址，保存后生效。" /></div>
        </details>
        {!saved ? null : paired ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-hairline p-4 text-sm">
            <Tag tone="green">已绑定</Tag>
            <span className="text-charcoal">每日简报、定时任务的结论和提醒会推到这个聊天。发 /help 看它能做什么。</span>
            <span className="ml-auto flex gap-2">
              <Button size="xs" variant="secondary" loading={busy === 'test'} onClick={() => void act('test', async () => {
                const r = await api.testChannel()
                setNote(r.ok ? { tone: 'success', text: '测试消息已发出，看一下手机' } : { tone: 'danger', text: r.error })
              })}>发一条测试消息</Button>
              <Button size="xs" variant="ghost" loading={busy === 'unpair'} onClick={() => void act('unpair', async () => { await api.unpairChannel(); reload() })}>解除绑定</Button>
            </span>
          </div>
        ) : code ? (
          <div className="rounded-lg border border-hairline p-4 text-sm">
            <p className="text-charcoal">在 Telegram 里打开你的机器人，给它发这条消息（10 分钟内有效）：</p>
            <p className="mt-2 select-all font-mono text-xl font-semibold tracking-wider text-ink">/pair {code}</p>
            <p className="mt-2 text-[13px] text-steel">发完这里会自动变成“已绑定”。之后只有这个聊天能指挥它，别人给机器人发消息不会有回应。</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline p-4 text-sm">
            <span className="text-charcoal">令牌已保存，还差一步：告诉机器人谁是它的主人。</span>
            <Button size="sm" variant="secondary" loading={busy === 'pair'} onClick={() => void act('pair', async () => setCode((await api.pairChannel()).code))}>生成配对码</Button>
          </div>
        )}
        {note ? <Callout tone={note.tone}>{note.text}</Callout> : null}
      </div>
    </Section>
  )
}

const DOCTOR_MARK: Record<DoctorItem['status'], { mark: string; cls: string }> = {
  ok: { mark: '✓', cls: 'text-on-mint' }, warn: { mark: '!', cls: 'text-on-yellow' }, fail: { mark: '✗', cls: 'text-on-rose' },
}

/** 版本与自检：现在是哪一版、有没有新的；哪一环不通、怎么修。 */
const VersionAndDoctor: React.FC = () => {
  const version = useApi(() => api.version())
  const [checking, setChecking] = useState(false)
  const [fresh, setFresh] = useState<Awaited<ReturnType<typeof api.version>> | null>(null)
  const [items, setItems] = useState<DoctorItem[] | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const v = fresh ?? version.data
  const check = async () => {
    setChecking(true); setError('')
    try { setFresh(await api.version(true)) } catch (e) { setError(e instanceof Error ? e.message : '检查失败') } finally { setChecking(false) }
  }
  const diagnose = async () => {
    setRunning(true); setError('')
    try { setItems((await api.doctor(true)).items) } catch (e) { setError(e instanceof Error ? e.message : '自检失败') } finally { setRunning(false) }
  }
  return (
    <Section title="版本与自检" hint={v ? `v${v.version}${v.commit ? ` · ${v.commit}` : ''}` : undefined}>
      <div className="grid max-w-2xl gap-3">
        {v?.behind ? (
          <Callout tone="info" title={`有${v.latest_version && v.latest_version !== v.version ? `新版本 ${v.latest_version}` : ` ${v.behind} 处更新`}`}>
            在终端里运行 <code className="rounded-xs bg-canvas/60 px-1 font-mono text-xs">wealthpilot update</code>。它会先备份数据库；仓库里有你自己的改动时会停下来，不会覆盖。
            {v.notes.map((n) => (
              <div key={n.version} className="mt-2">
                <p className="font-medium">v{n.version} <span className="font-normal opacity-70">{n.date}</span></p>
                <ul className="list-disc pl-4">{n.items.map((i) => <li key={i}>{i}</li>)}</ul>
              </div>
            ))}
          </Callout>
        ) : v ? <p className="text-sm text-charcoal">{v.checked ? '已经是最新。' : v.how || '还没有检查过更新。'}</p> : null}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" loading={checking} onClick={() => void check()}>检查更新</Button>
          <Button size="sm" variant="secondary" loading={running} onClick={() => void diagnose()}>自检</Button>
          {running ? <span className="self-center text-[13px] text-steel">正在逐项检查模型、数据源、数据库…</span> : null}
        </div>
        {error ? <Callout tone="danger">{error}</Callout> : null}
        {items ? (
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline text-sm">
            {items.map((i) => (
              <li key={i.name} className="flex items-baseline gap-3 px-4 py-2">
                <span className={`w-4 shrink-0 text-center font-mono font-semibold ${DOCTOR_MARK[i.status].cls}`}>{DOCTOR_MARK[i.status].mark}</span>
                <span className="w-28 shrink-0 text-ink sm:w-44">{i.name}</span>
                <span className="min-w-0 text-charcoal [overflow-wrap:anywhere]">{i.detail}{i.fix ? <span className="mt-0.5 block text-[13px] text-steel">{i.fix}</span> : null}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-[13px] text-steel">自检会实际调用一次模型、各取一次行情和财务数据，告诉你哪一环不通、怎么修。终端里对应的命令是 <code className="font-mono text-xs">wealthpilot doctor</code>。</p>}
      </div>
    </Section>
  )
}

// 常见的兼容服务。只预填接口地址；模型名各家经常变，照服务商文档里的写
const PRESETS: { label: string; url: string }[] = [
  { label: '硅基流动', url: 'https://api.siliconflow.cn/v1' },
  { label: '智谱', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'Moonshot（Kimi）', url: 'https://api.moonshot.cn/v1' },
  { label: '阿里云百炼（通义）', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: '火山方舟（豆包）', url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { label: '本机 Ollama', url: 'http://localhost:11434/v1' },
]
const KIND_LABEL: Record<string, string> = { stock_deep: '个股深度研究', stock_compare: '个股对比', holding_review: '持仓诊断', screen: '选股', review: '复盘',
  quick: '快速回答', rewrite: '改写 / 沿用证据', free: '自由问答', reuse: '原样复用' }
const wan = (tokens: number) => (tokens / 1e4).toFixed(tokens >= 1e6 ? 0 : 1)

/** 用量：花了多少 token（填了单价就折成钱），都花在哪类问题上。 */
const UsagePanel: React.FC = () => {
  const usage = useApi(api.usage)
  const u = usage.data
  if (!u) return null
  const cell = (label: string, t: { tokens: number; runs: number; cost: number | null }) => (
    <div className="min-w-0 flex-1 rounded-lg border border-hairline px-4 py-3">
      <p className="text-[13px] text-steel">{label}</p>
      <p className="mt-0.5 text-[22px] font-semibold leading-tight tabular-nums text-ink">{wan(t.tokens)} <span className="text-sm font-normal text-steel">万 token</span></p>
      <p className="mt-0.5 text-[13px] text-steel">{t.runs} 次{t.cost != null ? ` · 约 ${t.cost.toFixed(2)} 元` : ''}</p>
    </div>
  )
  return (
    <div className="grid max-w-3xl gap-3">
      <div className="flex flex-col gap-3 sm:flex-row">{cell('今天', u.today)}{cell('近 7 天', u.last_7_days)}{cell('近 30 天', u.last_30_days)}</div>
      {u.last_30_days.runs > 0 ? (
        <>
          <ValueBars title="每天的用量（万 token）" unit="万 token" height={150} data={u.by_day.map((d) => ({ label: d.day.slice(3), value: Number((d.tokens / 1e4).toFixed(1)) }))} />
          <ul className="divide-y divide-hairline-soft rounded-lg border border-hairline text-sm">
            {u.by_kind.map((k) => (
              <li key={k.kind} className="flex items-baseline gap-3 px-4 py-2">
                <span className="min-w-0 flex-1 text-ink">{KIND_LABEL[k.kind] ?? (k.kind.startsWith('skill:') ? `方法：${k.kind.slice(6)}` : k.kind)}</span>
                <span className="shrink-0 tabular-nums text-steel">{k.runs} 次</span>
                <span className="w-36 shrink-0 text-right tabular-nums text-charcoal">平均 {wan(k.avg_tokens)} 万 / 次</span>
              </li>
            ))}
          </ul>
        </>
      ) : <p className="text-[13px] text-steel">还没有用量记录。从这一版开始，每次调用模型都会记一笔。</p>}
      {u.today.tokens > 0 && u.today.cached_tokens > 0 ? <p className="text-[13px] text-steel">今天的输入里有 {Math.round((u.today.cached_tokens / Math.max(1, u.today.input_tokens)) * 100)}% 命中了服务商的缓存，这部分实际更便宜，所以折算的钱是个上限。</p> : null}
    </div>
  )
}

/** 设置：在网页上改配置，不用编辑 .env。保存后立即生效。 */
const SettingsPage: React.FC = () => {
  const settings = useApi(api.settings)
  const [form, setForm] = useState<Values>({})
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const data = settings.data
  useEffect(() => { if (data) setForm(data.values) }, [data])

  const set = (k: string, v: string | number | boolean) => setForm((f) => ({ ...f, [k]: v }))
  const locked = (k: string) => data?.overridden.includes(k) ?? false
  const provider = String(form.ai_provider ?? 'anthropic')
  const keyField = provider === 'deepseek' ? 'deepseek_api_key' : provider === 'openai' ? 'openai_api_key' : 'anthropic_api_key'
  const modelField = provider === 'deepseek' ? 'deepseek_model' : provider === 'openai' ? 'openai_model' : 'anthropic_model'

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setMessage(null)
    try {
      await api.saveSettings({ ...form, ...keys, paper_initial_cash: Number(form.paper_initial_cash), watch_move_pct: Number(form.watch_move_pct),
        auto_daily_runs_max: Number(form.auto_daily_runs_max), openai_max_tokens: Number(form.openai_max_tokens || 4096),
        daily_token_budget: Math.max(0, Math.round(Number(form.daily_token_budget || 0))), token_price_input: Number(form.token_price_input || 0),
        token_price_output: Number(form.token_price_output || 0), research_reuse_hours: Number(form.research_reuse_hours || 0) })
      setKeys({})
      settings.reload()
      setMessage({ tone: 'success', text: '已保存，立即生效' })
    } catch (err) {
      setMessage({ tone: 'danger', text: err instanceof Error ? err.message : '保存失败' })
    } finally { setBusy(false) }
  }
  const test = async () => {
    setTesting(true); setMessage(null)
    try {
      const r = await api.testModel()
      setMessage(r.ok ? { tone: 'success', text: `模型可用：${r.provider} / ${r.model}` } : { tone: 'danger', text: `模型不可用（${r.provider} / ${r.model}）：${r.error}` })
    } catch (err) {
      setMessage({ tone: 'danger', text: err instanceof Error ? err.message : '测试失败' })
    } finally { setTesting(false) }
  }

  if (DEMO) {
    return <Page title="设置" description="模型、研究方式、模拟盘和每日盯盘"><Callout tone="info">在线演示没有后端，这一页在本地运行后可用。</Callout></Page>
  }
  return (
    <Page title="设置" description="模型、研究方式、手机触达、模拟盘和每日盯盘。保存后立即生效，不用重启">
      <DataState loading={settings.loading && !data} error={settings.error} onRetry={settings.reload}>
        {data ? (
          <form onSubmit={save} className="flex flex-col gap-10">
            {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

            <Section title="模型" hint={`当前使用 ${data.active_model}`}>
              <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
                <Select id="s-provider" label="提供商" value={provider} onChange={(v) => set('ai_provider', v)} options={[{ value: 'anthropic', label: 'Claude（Anthropic）' }, { value: 'deepseek', label: 'DeepSeek' }, { value: 'openai', label: '其他兼容 OpenAI 接口的服务（含本机模型）' }]} />
                <Input id="s-model" label="模型" value={String(form[modelField] ?? '')} onChange={(e) => set(modelField, e.target.value)}
                  placeholder={provider === 'openai' ? '照服务商文档里的模型名写' : undefined} />
                {provider === 'openai' ? (
                  <div className="grid gap-3 sm:col-span-2">
                    <Input id="s-base" label="接口地址" placeholder="https://…/v1" value={String(form.openai_base_url ?? '')} onChange={(e) => set('openai_base_url', e.target.value)}
                      hint="任何兼容 OpenAI 接口的服务都行。点下面的名字可以填好常见服务的地址。" />
                    <div className="flex flex-wrap gap-1.5">
                      {PRESETS.map((p) => (
                        <button key={p.url} type="button" onClick={() => set('openai_base_url', p.url)}
                          className={`rounded-full border px-2.5 py-0.5 text-[13px] transition-colors ${form.openai_base_url === p.url ? 'border-primary text-ink' : 'border-hairline text-slate hover:bg-hover hover:text-ink'}`}>{p.label}</button>
                      ))}
                    </div>
                    <Callout tone="neutral">
                      模型要支持<b>工具调用</b>（function calling），不然 Agent 没法取数，研究会一直失败。本机模型不需要 Key，留空就行，但小模型的工具调用和中文长文质量通常明显差一截。
                      这些服务我们没有逐个实测过，填好后先点「测试当前配置」。
                    </Callout>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Input id="s-maxtok" label="单次输出上限（token）" type="number" min="256" step="1" value={String(form.openai_max_tokens ?? 4096)} onChange={(e) => set('openai_max_tokens', e.target.value)}
                        hint="超过服务商的限制会直接报错；拿不准就用 4096" />
                      <label className="flex cursor-pointer items-start gap-2 self-end pb-5 text-sm text-charcoal">
                        <input type="checkbox" checked={Boolean(form.openai_json_mode)} onChange={(e) => set('openai_json_mode', e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--primary)]" />
                        <span>服务支持 JSON 输出模式<span className="block text-xs text-steel">打开后规划更稳；不支持的服务打开会报 400</span></span>
                      </label>
                    </div>
                  </div>
                ) : null}
                <div className="sm:col-span-2">
                  <Input id="s-key" label="API Key" type="password" autoComplete="off"
                    placeholder={data.secrets[keyField]?.set ? `已配置（${data.secrets[keyField].hint}），留空表示不改` : '粘贴 Key'}
                    hint={provider === 'openai' ? '本机模型可以留空。只保存在你这台机器上；保存后页面不会再显示它' : '只保存在你这台机器的 backend/.env 里；保存后页面不会再显示它'}
                    value={keys[keyField] ?? ''} onChange={(e) => setKeys((k) => ({ ...k, [keyField]: e.target.value }))} />
                </div>
              </div>
              <Button variant="secondary" size="sm" className="mt-3" loading={testing} onClick={() => void test()}>测试当前配置</Button>
            </Section>

            <Section title="用量与预算" hint="token 是服务商计费的单位；想看折成多少钱，把你那家的单价填上">
              <UsagePanel />
              <div className="mt-4 grid max-w-3xl gap-3 sm:grid-cols-3">
                <Input id="s-budget" label="每天最多用多少（万 token）" type="number" min="0" step="1"
                  value={form.daily_token_budget ? String(Number(form.daily_token_budget) / 1e4) : ''} placeholder="不限"
                  onChange={(e) => set('daily_token_budget', Math.round(Number(e.target.value || 0) * 1e4))}
                  hint="到了就不再调用模型，第二天恢复。一次个股深度研究大约 15 到 20 万" />
                <Input id="s-pin" label="输入单价（元 / 百万 token）" type="number" min="0" step="0.01" value={String(form.token_price_input || '')} placeholder="不折算"
                  onChange={(e) => set('token_price_input', e.target.value)} />
                <Input id="s-pout" label="输出单价（元 / 百万 token）" type="number" min="0" step="0.01" value={String(form.token_price_output || '')} placeholder="不折算"
                  onChange={(e) => set('token_price_output', e.target.value)} />
              </div>
              <div className="mt-3 grid max-w-3xl gap-3">
                <div className="max-w-xs"><Input id="s-reuse" label="几小时内不重复取数" type="number" min="0" step="0.5" value={String(form.research_reuse_hours ?? 4)} onChange={(e) => set('research_reuse_hours', e.target.value)}
                  hint="这段时间内再对同一只股票做深度研究，沿用上次取到的数据。填 0 就每次都重新取" /></div>
                <Toggle label="个股深度研究先做多空辩论" locked={locked('debate_enabled')} checked={Boolean(form.debate_enabled)} onChange={(v) => set('debate_enabled', v)}
                  hint="撰写前让看多、看空两方各说一遍，报告更不容易和稀泥。每次多两次模型调用，想省就关掉。" />
              </div>
            </Section>

            <Section title="研究方式">
              <div className="grid max-w-2xl gap-3">
                <Toggle label="个人模式：给出立场与操作建议" locked={locked('advice_mode')} checked={Boolean(form.advice_mode)} onChange={(v) => set('advice_mode', v)}
                  hint="打开后个股研究会多一节「建议」（看多 / 中性 / 看空、对应操作、失效条件），并生成需要你逐条授权的操作建议单。关闭时只陈述事实与推断。" />
                <Toggle label="事后验证" locked={locked('checkpoints_enabled')} checked={Boolean(form.checkpoints_enabled)} onChange={(v) => set('checkpoints_enabled', v)}
                  hint="研究发布后把最关键的判断记成验证点，到期由代码核对。每次研究多一次小额模型调用。" />
              </div>
            </Section>

            <Reach data={data} token={keys.telegram_bot_token ?? ''} onToken={(v) => setKeys((k) => ({ ...k, telegram_bot_token: v }))}
              base={String(form.telegram_api_base ?? '')} onBase={(v) => set('telegram_api_base', v)} />

            <Section title="模拟盘">
              <div className="grid max-w-2xl gap-3">
                <Toggle label="开启模拟盘" locked={locked('broker')} checked={form.broker === 'paper'} onChange={(v) => set('broker', v ? 'paper' : 'none')}
                  hint="开启后，授权操作建议单会在模拟盘按最新价成交（不动真钱），持仓自动同步进组合。关闭时，授权只是把你填的成交记入持仓。" />
                <div className="max-w-xs"><Input id="s-cash" label="初始资金（元）" type="number" min="1" value={String(form.paper_initial_cash ?? '')} onChange={(e) => set('paper_initial_cash', e.target.value)} hint="只影响新开或重置后的账户" /></div>
              </div>
            </Section>

            <Section title="每日盯盘" hint="后端开着时，交易日到点自动检查持仓和自选">
              <div className="grid max-w-2xl gap-3">
                <Toggle label="自动盯盘" locked={locked('watch_enabled')} checked={Boolean(form.watch_enabled)} onChange={(v) => set('watch_enabled', v)}
                  hint="核对到期的验证点，检查新财报、重要公告、估值跨档和大涨大跌，生成「今日简报」。全程不调用模型。" />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Input id="s-time" label="每天几点检查" type="time" value={String(form.watch_time ?? '15:30')} onChange={(e) => set('watch_time', e.target.value)} />
                  <Input id="s-move" label="涨跌超过多少算异动（%）" type="number" min="0.1" step="0.1" value={String(form.watch_move_pct ?? '')} onChange={(e) => set('watch_move_pct', e.target.value)} />
                </div>
                <Input id="s-hook" label="推送地址（可选）" placeholder="企业微信 / 飞书 / Slack 机器人的 webhook 地址" value={String(form.alert_webhook_url ?? '')} onChange={(e) => set('alert_webhook_url', e.target.value)} hint="有事才推送；留空则只在「今日」页显示" />
                <div className="max-w-xs"><Input id="s-auto" label="定时任务每天最多自动跑几次" type="number" min="0" step="1" value={String(form.auto_daily_runs_max ?? '')} onChange={(e) => set('auto_daily_runs_max', e.target.value)} hint="每次都会调用模型。手动点「现在跑一次」不算在内" /></div>
                <Toggle label="启动时检查更新" locked={locked('update_check')} checked={Boolean(form.update_check)} onChange={(v) => set('update_check', v)}
                  hint="只读取本仓库的远端有没有新提交，不上传任何东西。关掉后仍可以手动点「检查更新」。" />
              </div>
            </Section>

            <div className="flex items-center gap-3">
              <Button type="submit" loading={busy}>保存</Button>
              <span className="text-[13px] text-steel">写入 {data.env_file}。只能在运行后端的这台机器上修改。</span>
            </div>
          </form>
        ) : null}
      </DataState>
      {data ? <VersionAndDoctor /> : null}
    </Page>
  )
}

export default SettingsPage
