import type React from 'react'
import { useEffect, useState } from 'react'
import { DEMO, api, useApi, type AppSettings, type DoctorItem, type ModelPreset } from '../api'
import { ValueBars } from '../components/charts'
import { Button, Callout, Input, Segmented, Select, Tag } from '../components/kit'
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

type ChannelName = 'telegram' | 'feishu' | 'wecom'
const CHANNEL_TABS = [['telegram', 'Telegram'], ['feishu', '飞书'], ['wecom', '企业微信']] as const

/**
 * 手机触达：在 Telegram、飞书或企业微信里收简报和提醒、直接提问、处理建议单。
 * 应用的凭证和其他设置一起保存；认谁做主人靠配对码 —— 在这里生成，在那个应用里发给机器人，谁发对了谁就是主人。
 */
const Reach: React.FC<{
  data: AppSettings; form: Values; set: (k: string, v: string) => void; keys: Record<string, string>; setKey: (k: string, v: string) => void
}> = ({ data, form, set, keys, setKey }) => {
  const channel = useApi(api.channel)
  const [tab, setTab] = useState<ChannelName>('telegram')
  const [code, setCode] = useState('')
  const [note, setNote] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [busy, setBusy] = useState('')
  const info = channel.data?.channels.find((c) => c.channel === tab)
  const paired = info?.paired
  const reload = channel.reload
  // 配对码亮着的时候每 3 秒看一眼：用户在手机上发完，这里自己变成“已绑定”
  useEffect(() => {
    if (!code || paired) return undefined
    const timer = setInterval(reload, 3000)
    return () => clearInterval(timer)
  }, [code, paired, reload])
  useEffect(() => { setCode(''); setNote(null) }, [tab, paired])
  const act = async (key: string, work: () => Promise<void>) => {
    setBusy(key); setNote(null)
    try { await work() } catch (e) { setNote({ tone: 'danger', text: e instanceof Error ? e.message : '操作失败' }) } finally { setBusy('') }
  }
  const secret = (id: string, field: string, label: string, hint?: string) => (
    <Input id={id} label={label} type="password" autoComplete="off" hint={hint}
      placeholder={data.secrets[field]?.set ? `已配置（${data.secrets[field].hint}），留空表示不改` : '粘贴后点页面底部的「保存」'}
      value={keys[field] ?? ''} onChange={(e) => setKey(field, e.target.value)} />
  )
  const text = (id: string, field: string, label: string, hint?: string, placeholder?: string) => (
    <Input id={id} label={label} hint={hint} placeholder={placeholder} value={String(form[field] ?? '')} onChange={(e) => set(field, e.target.value)} />
  )
  const callback = `${window.location.origin}/api/channel/wecom/callback`
  return (
    <Section title="手机触达" hint="在手机上收每日简报和提醒、直接提问、处理建议单。三个里接一个就行">
      <div className="mb-4 flex items-center gap-4 border-b border-hairline">
        <Segmented value={tab} onChange={(v) => setTab(v as ChannelName)} options={CHANNEL_TABS} />
        <span className="mb-1.5 ml-auto text-[13px] text-steel">
          {(channel.data?.channels ?? []).filter((c) => c.paired).map((c) => c.label).join('、') || '还没有绑定任何一个'}{channel.data?.channels.some((c) => c.paired) ? ' 已绑定' : ''}
        </span>
      </div>
      <div className="grid max-w-2xl gap-3">
        {tab === 'telegram' ? (
          <>
            {secret('s-tg', 'telegram_bot_token', '机器人令牌', '在 Telegram 里找 @BotFather，发 /newbot，按提示起个名字，它会回你一串令牌。这个机器人只属于你。')}
            <details className="text-[13px] text-steel">
              <summary className="cursor-pointer select-none hover:text-ink">本机连不上 Telegram？</summary>
              <div className="mt-2">{text('s-tgbase', 'telegram_api_base', '接口地址', '默认 https://api.telegram.org。需要走中转时改成你的中转地址，保存后生效。')}</div>
            </details>
          </>
        ) : tab === 'feishu' ? (
          <>
            <Callout tone="neutral">
              不需要公网地址：由这台电脑主动连到飞书。在<a className="mx-0.5 underline underline-offset-2" href="https://open.feishu.cn/app" target="_blank" rel="noreferrer">飞书开放平台</a>建一个「企业自建应用」，然后：
              <ol className="mt-1.5 list-decimal space-y-0.5 pl-5">
                <li>添加应用能力里加上「机器人」；</li>
                <li>权限管理里开通「读取用户发给机器人的单聊消息」和「以应用的身份发消息」；</li>
                <li>事件与回调里，订阅方式选「使用长连接接收事件」，添加事件「接收消息」；</li>
                <li>发布应用，把下面两项填好保存，然后<b>重启 WealthPilot</b>（长连接在启动时建立）；</li>
                <li>在飞书里搜到这个机器人，把配对码发给它。</li>
              </ol>
            </Callout>
            {text('s-fsid', 'feishu_app_id', 'App ID', undefined, 'cli_…')}
            {secret('s-fssecret', 'feishu_app_secret', 'App Secret')}
            <details className="text-[13px] text-steel">
              <summary className="cursor-pointer select-none hover:text-ink">用的是海外版 Lark？</summary>
              <div className="mt-2">{text('s-fsbase', 'feishu_api_base', '接口地址', '飞书是 https://open.feishu.cn，Lark 是 https://open.larksuite.com')}</div>
            </details>
            {info?.error ? <Callout tone="danger">{info.error}</Callout> : null}
          </>
        ) : (
          <>
            <Callout tone="warning">
              企业微信只支持“回调”收消息：它要能从公网访问到 WealthPilot。只在自己电脑上跑、没有公网地址的话用不了这个，请用飞书或 Telegram。
              部署在服务器上时：在企业微信管理后台建一个自建应用，「接收消息」里把 URL 填成
              <code className="mx-1 select-all break-all rounded-xs bg-canvas/60 px-1 font-mono text-xs">{callback}</code>
              （换成你的公网地址），Token 和 EncodingAESKey 用它随机生成的；先在这里保存，再回后台点保存，它会来验证一次。还要把服务器的 IP 加进应用的「企业可信 IP」，否则发不出消息。
            </Callout>
            <div className="grid gap-3 sm:grid-cols-2">
              {text('s-wxcorp', 'wecom_corp_id', '企业 ID', '「我的企业」页面最下面')}
              {text('s-wxagent', 'wecom_agent_id', 'AgentId', '应用详情页里')}
            </div>
            {secret('s-wxsecret', 'wecom_secret', '应用的 Secret')}
            <div className="grid gap-3 sm:grid-cols-2">
              {secret('s-wxtoken', 'wecom_token', 'Token')}
              {secret('s-wxaes', 'wecom_aes_key', 'EncodingAESKey', '43 位')}
            </div>
          </>
        )}

        {!info?.configured ? (
          <p className="text-[13px] text-steel">填好上面的内容并点页面底部的「保存」，这里会出现绑定的步骤。</p>
        ) : paired ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-hairline p-4 text-sm">
            <Tag tone="green">已绑定</Tag>
            <span className="text-charcoal">简报、定时任务的结论和提醒会发到这里。在里面发 /help 看它能做什么。</span>
            <span className="ml-auto flex gap-2">
              <Button size="xs" variant="secondary" loading={busy === 'test'} onClick={() => void act('test', async () => {
                const r = await api.testChannel(tab)
                setNote(r.ok ? { tone: 'success', text: '测试消息已发出，看一下手机' } : { tone: 'danger', text: r.error })
              })}>发一条测试消息</Button>
              <Button size="xs" variant="ghost" loading={busy === 'unpair'} onClick={() => void act('unpair', async () => { await api.unpairChannel(tab); reload() })}>解除绑定</Button>
            </span>
          </div>
        ) : code ? (
          <div className="rounded-lg border border-hairline p-4 text-sm">
            <p className="text-charcoal">在{info.label}里打开你的机器人（应用），给它发这条消息（10 分钟内有效）：</p>
            <p className="mt-2 select-all font-mono text-xl font-semibold tracking-wider text-ink">/pair {code}</p>
            <p className="mt-2 text-[13px] text-steel">发完这里会自动变成“已绑定”。之后只有这个聊天能指挥它，别人发消息不会有回应。</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline p-4 text-sm">
            <span className="text-charcoal">应用信息已保存，还差一步：告诉它谁是主人。</span>
            <Button size="sm" variant="secondary" loading={busy === 'pair'} onClick={() => void act('pair', async () => setCode((await api.pairChannel(tab)).code))}>生成配对码</Button>
          </div>
        )}
        {note ? <Callout tone={note.tone}>{note.text}</Callout> : null}
        <p className="text-xs text-stone">飞书和企业微信的文字消息没有按钮，授权建议单时按提示回复命令（如 /ok 3）。这两个渠道是照官方文档写的，还没有用真实的应用跑过，接不上的话告诉我们卡在哪一步。</p>
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

// 模型有三个位置，各自存一套 Key 和模型名；主模型和备用模型各占一个
const SLOTS = [{ value: 'anthropic', label: 'Claude（Anthropic）' }, { value: 'deepseek', label: 'DeepSeek' }, { value: 'openai', label: '其他兼容 OpenAI 接口的服务（含本机模型）' }]
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
  // 能接哪些服务由后端给（和终端里 wealthpilot setup 用的是同一份），页面不自己再维护一份
  const presets = data?.presets ?? []
  const picked = presets.find((p) => p.base_url === form.openai_base_url)
  const pick = (p: ModelPreset) => setForm((f) => {
    const model = String(f.openai_model ?? '')
    const untouched = !model || presets.some((x) => x.model === model)   // 没填过，或还是别家的默认名：跟着换；自己写的不动
    return { ...f, openai_base_url: p.base_url, openai_model: untouched ? p.model : model }
  })

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
                <Select id="s-provider" label="提供商" value={provider} onChange={(v) => set('ai_provider', v)} options={SLOTS} />
                <Input id="s-model" label="模型" value={String(form[modelField] ?? '')} onChange={(e) => set(modelField, e.target.value)}
                  placeholder={provider === 'openai' ? '照服务商文档里的模型名写' : undefined} />
                {provider === 'openai' ? (
                  <div className="grid gap-3 sm:col-span-2">
                    <Input id="s-base" label="接口地址" placeholder="https://…/v1" value={String(form.openai_base_url ?? '')} onChange={(e) => set('openai_base_url', e.target.value)}
                      hint="任何兼容 OpenAI 接口的服务都行。点下面的名字可以填好常见服务的地址。" />
                    <div className="flex flex-wrap gap-1.5">
                      {presets.map((p) => (
                        <button key={p.key} type="button" onClick={() => pick(p)}
                          className={`rounded-full border px-2.5 py-0.5 text-[13px] transition-colors ${form.openai_base_url === p.base_url ? 'border-primary text-ink' : 'border-hairline text-slate hover:bg-hover hover:text-ink'}`}>{p.label}</button>
                      ))}
                    </div>
                    {picked && (picked.note || picked.key_page) ? (
                      <p className="text-[13px] text-steel">
                        {picked.note}{picked.note && picked.key_page ? ' · ' : ''}
                        {picked.key_page ? <>Key 在这里申请：<a href={picked.key_page} target="_blank" rel="noreferrer" className="text-ink underline decoration-hairline underline-offset-2 hover:decoration-ink">{picked.key_page.replace(/^https?:\/\//, '')}</a></> : null}
                      </p>
                    ) : null}
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
                    hint={`${provider === 'openai' ? '本机模型可以留空。' : ''}只保存在你这台机器上（${data.env_file}）；保存后页面不会再显示它`}
                    value={keys[keyField] ?? ''} onChange={(e) => setKeys((k) => ({ ...k, [keyField]: e.target.value }))} />
                </div>
              </div>
              <div className="mt-4 max-w-2xl">
                <Select id="s-fallback" label="备用模型" value={String(form.ai_fallback ?? '')} onChange={(v) => set('ai_fallback', v)}
                  options={[{ value: '', label: '不用' }, ...SLOTS.filter((o) => o.value !== provider)]} />
                <p className="mt-1 text-[13px] text-steel">
                  主模型余额不足、Key 失效、被限流或连不上时，这一轮研究自动换到备用模型接着跑，回答上会注明。
                  {form.ai_fallback && form.ai_fallback === data.values.ai_fallback && !data.fallback_active
                    ? <span className="text-ink"> 现在还没生效：先把提供商切到那一家，把它的 Key 和模型名填好保存，再切回来。</span>
                    : ' 备用的那一家要先配好自己的 Key 和模型名。'}
                </p>
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

            <Reach data={data} form={form} set={set} keys={keys} setKey={(k, v) => setKeys((prev) => ({ ...prev, [k]: v }))} />

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
