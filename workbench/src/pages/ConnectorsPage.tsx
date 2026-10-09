import type React from 'react'
import { useState } from 'react'
import { PlugZap } from 'lucide-react'
import { api, useApi, type ConnectorTest } from '../api'
import { Button, Callout, Card, Tag, type Tone } from '../components/kit'
import { DataState, Page, Section, Table, Td } from '../components/ui'

const KIND: Record<string, { label: string; tone: Tone }> = {
  broker: { label: '券商账户', tone: 'orange' },
  data: { label: '行情 / 财务数据', tone: 'blue' },
  research: { label: '研报资讯', tone: 'purple' },
  custom: { label: '自定义', tone: 'gray' },
}

const STATUS_TONE: Record<string, Tone> = { ready: 'green', needs_url: 'blue', unsupported: 'gray' }
const code = 'rounded-xs bg-surface px-1 font-mono text-[13px]'

const ConnectorsPage: React.FC = () => {
  const list = useApi(api.connectors)
  const presets = useApi(api.connectorPresets)
  const [tests, setTests] = useState<Record<string, { loading: boolean; result?: ConnectorTest; error?: string }>>({})

  const test = async (name: string) => {
    setTests((t) => ({ ...t, [name]: { loading: true } }))
    try {
      const result = await api.testConnector(name)
      setTests((t) => ({ ...t, [name]: { loading: false, result } }))
    } catch (e) {
      setTests((t) => ({ ...t, [name]: { loading: false, error: e instanceof Error ? e.message : '测试失败' } }))
    }
  }

  const connectors = list.data?.connectors ?? []

  return (
    <Page title="数据连接" description="把妙想、iFinD 这类第三方数据服务（MCP）接进来，让 AI 研究能用上它们的数据。不接也能用：A 股、港股、美股的基础数据已经内置">
      <Callout tone="info" title="只读接入">
        外部服务里凡是下单、撤单、转账这类会动账户的工具，都会被强制屏蔽，不会交给 AI，也无法通过本系统调用。WealthPilot 只做研究与分析，不代你交易。
      </Callout>

      <Section title="已配置的连接" hint={list.data ? `配置文件：${list.data.config_file}` : undefined}>
        <DataState loading={list.loading} error={list.error} onRetry={list.reload}
          empty={connectors.length === 0 ? '还没有接任何外部服务。下面是现成的几家，挑一家按说明在终端里接。' : undefined}>
          <div className="flex flex-col gap-3">
            {connectors.map((c) => {
              const kind = KIND[c.kind] ?? KIND.custom
              const t = tests[c.name]
              return (
                <Card key={c.name} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-base font-semibold text-ink">{c.label}</span>
                        <Tag tone={kind.tone}>{kind.label}</Tag>
                        <Tag tone={c.enabled ? 'green' : 'gray'}>{c.enabled ? '已启用' : '未启用'}</Tag>
                        {c.auth !== '不需要' ? <Tag tone={c.auth === '已配置' ? 'green' : 'yellow'}>凭据：{c.auth}</Tag> : null}
                      </div>
                      {c.description ? <p className="mt-1.5 text-sm text-slate">{c.description}</p> : null}
                      <p className="mt-1 font-mono text-xs text-stone">{c.name} · {c.transport === 'http' ? c.endpoint : '本机进程（stdio）'}</p>
                    </div>
                    <Button size="sm" variant="secondary" loading={t?.loading} onClick={() => void test(c.name)}><PlugZap className="h-3.5 w-3.5" />测试连接</Button>
                  </div>
                  {t?.error ? <Callout tone="danger" className="mt-3">{t.error}</Callout> : null}
                  {t?.result && !t.result.ok ? <Callout tone="danger" className="mt-3">{t.result.error}</Callout> : null}
                  {t?.result?.ok ? (
                    <div className="mt-3">
                      <p className="mb-2 text-[13px] text-steel">连接成功：{t.result.allowed_count} 个工具可供 AI 使用，{t.result.blocked_count} 个被屏蔽{c.enabled ? '' : '。该连接未启用，启用后 AI 才会用到'}</p>
                      <Table head={[{ label: '工具' }, { label: '状态' }, { label: '说明' }]}>
                        {t.result.tools.map((tool) => (
                          <tr key={tool.name}>
                            <Td className="font-mono text-[13px]">{tool.name}</Td>
                            <Td><Tag tone={tool.allowed ? 'green' : 'pink'}>{tool.allowed ? '可用' : '已屏蔽'}</Tag> <span className="text-xs text-steel">{tool.reason}</span></Td>
                            <Td className="max-w-[360px] text-[13px] text-slate"><span className="line-clamp-2">{tool.description}</span></Td>
                          </tr>
                        ))}
                      </Table>
                    </div>
                  ) : null}
                </Card>
              )
            })}
          </div>
        </DataState>
      </Section>

      <Section title="现成的服务" hint="查公开资料整理的清单：是官方的还是社区的、要什么、现在接不接得上。都要账号或 Key，所以这里没有一家实际连过">
        <DataState loading={presets.loading} error={presets.error} onRetry={presets.reload}>
          <div className="grid gap-3 lg:grid-cols-2">
            {(presets.data ?? []).map((p) => (
              <Card key={p.key} className="flex flex-col gap-1.5 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-ink">{p.label}</span>
                  <Tag tone={p.official ? 'purple' : 'gray'}>{p.official ? '官方' : '社区'}</Tag>
                  <Tag tone={STATUS_TONE[p.status] ?? 'gray'}>{p.status_label}</Tag>
                </div>
                <p className="text-[13px] leading-relaxed text-charcoal"><span className="text-steel">有什么　</span>{p.provides}</p>
                <p className="text-[13px] leading-relaxed text-charcoal"><span className="text-steel">要什么　</span>{p.needs}</p>
                <p className="text-[13px] leading-relaxed text-slate"><span className="text-steel">注意　　</span>{p.caveat}</p>
                {p.links.length ? <p className="flex flex-wrap gap-x-3 text-[13px]">{p.links.map((l) => <a key={l} href={l} target="_blank" rel="noreferrer" className="truncate text-slate underline underline-offset-2 hover:text-ink">{new URL(l).hostname}</a>)}</p> : null}
                {p.status !== 'unsupported' ? <p className="mt-auto pt-1.5"><code className={code}>wealthpilot connectors add {p.key}{p.status === 'needs_url' ? ' --url <服务地址>' : ''}</code></p> : null}
              </Card>
            ))}
          </div>
        </DataState>
      </Section>

      <Section title="怎么接入" hint="在自己电脑的终端里做，不通过网页添加：它相当于让这台机器替你访问外部服务，令牌也只该留在这台机器上">
        <ol className="max-w-[760px] list-decimal space-y-2 pl-5 text-sm leading-relaxed text-charcoal">
          <li>按上面「要什么」把对方的账号、Key 准备好。</li>
          <li>终端里运行 <code className={code}>wealthpilot connectors add 名字 --url 服务地址 --token 令牌</code>。地址和令牌该不该填，看那一条的说明；令牌存进你自己的 <code className={code}>.env</code>，不会写进配置文件。</li>
          <li><code className={code}>wealthpilot connectors test 名字</code>，或者回到这一页点「测试连接」：看连不连得上、哪些工具可用、哪些被屏蔽。</li>
          <li>之后在「研究」里问到相关内容时，Agent 会连同这些外部工具一起用，取回来的数据同样进证据链、接受校验。不想用了：<code className={code}>wealthpilot connectors remove 名字</code>。</li>
        </ol>
      </Section>
    </Page>
  )
}

export default ConnectorsPage
