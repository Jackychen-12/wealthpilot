import type React from 'react'
import { useEffect, useState } from 'react'
import { DEMO, api, useApi } from '../api'
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
  const keyField = provider === 'deepseek' ? 'deepseek_api_key' : 'anthropic_api_key'
  const modelField = provider === 'deepseek' ? 'deepseek_model' : 'anthropic_model'

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setMessage(null)
    try {
      await api.saveSettings({ ...form, ...keys, paper_initial_cash: Number(form.paper_initial_cash), watch_move_pct: Number(form.watch_move_pct) })
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
    <Page title="设置" description="模型、研究方式、模拟盘和每日盯盘。保存后立即生效，不用重启">
      <DataState loading={settings.loading && !data} error={settings.error} onRetry={settings.reload}>
        {data ? (
          <form onSubmit={save} className="flex flex-col gap-10">
            {message ? <Callout tone={message.tone}>{message.text}</Callout> : null}

            <Section title="模型" hint={`当前使用 ${data.active_model}`}>
              <div className="grid max-w-2xl gap-3 sm:grid-cols-2">
                <Select id="s-provider" label="提供商" value={provider} onChange={(v) => set('ai_provider', v)} options={[{ value: 'anthropic', label: 'Claude（Anthropic）' }, { value: 'deepseek', label: 'DeepSeek' }]} />
                <Input id="s-model" label="模型" value={String(form[modelField] ?? '')} onChange={(e) => set(modelField, e.target.value)} />
                <div className="sm:col-span-2">
                  <Input id="s-key" label="API Key" type="password" autoComplete="off"
                    placeholder={data.secrets[keyField]?.set ? `已配置（${data.secrets[keyField].hint}），留空表示不改` : '粘贴 Key'}
                    hint="只保存在你这台机器的 backend/.env 里；保存后页面不会再显示它"
                    value={keys[keyField] ?? ''} onChange={(e) => setKeys((k) => ({ ...k, [keyField]: e.target.value }))} />
                </div>
              </div>
              <Button variant="secondary" size="sm" className="mt-3" loading={testing} onClick={() => void test()}>测试当前配置</Button>
            </Section>

            <Section title="研究方式">
              <div className="grid max-w-2xl gap-3">
                <Toggle label="个人模式：给出立场与操作建议" locked={locked('advice_mode')} checked={Boolean(form.advice_mode)} onChange={(v) => set('advice_mode', v)}
                  hint="打开后个股研究会多一节「建议」（看多 / 中性 / 看空、对应操作、失效条件），并生成需要你逐条授权的操作建议单。关闭时只陈述事实与推断。" />
                <Toggle label="事后验证" locked={locked('checkpoints_enabled')} checked={Boolean(form.checkpoints_enabled)} onChange={(v) => set('checkpoints_enabled', v)}
                  hint="研究发布后把最关键的判断记成验证点，到期由代码核对。每次研究多一次小额模型调用。" />
              </div>
            </Section>

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
              </div>
            </Section>

            <div className="flex items-center gap-3">
              <Button type="submit" loading={busy}>保存</Button>
              <span className="text-[13px] text-steel">写入 {data.env_file}。只能在运行后端的这台机器上修改。</span>
            </div>
          </form>
        ) : null}
      </DataState>
    </Page>
  )
}

export default SettingsPage
