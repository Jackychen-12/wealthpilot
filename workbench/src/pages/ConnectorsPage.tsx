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

// 可以接入的服务类型。这里只说明"能接什么"，不替任何具体厂商背书 —— 对方是否提供 MCP 服务以其官方文档为准。
const CATALOG = [
  { kind: 'broker', title: '券商账户（只读）', body: '查询持仓、资金、成交记录，让 AI 研究直接基于你的真实账户，而不必手工录入。' },
  { kind: 'data', title: '行情与财务数据服务', body: '付费或自建的数据源：更全的财务指标、历史估值分位、分钟线、港美股行情。' },
  { kind: 'research', title: '研报与资讯', body: '卖方研报、公告、新闻检索，给个股研究补充定性信息。' },
  { kind: 'custom', title: '自建 MCP 服务', body: '任何遵循 MCP 协议的服务都能接：内部数据库、策略库、公司知识库。' },
]

const EXAMPLE = `{
  "connectors": [
    {
      "name": "my_broker",
      "label": "我的券商（只读）",
      "kind": "broker",
      "transport": "http",
      "url": "https://券商提供的地址/mcp",
      "auth_env": "BROKER_MCP_TOKEN",
      "enabled": true
    }
  ]
}`

const ConnectorsPage: React.FC = () => {
  const list = useApi(api.connectors)
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
    <Page title="数据连接" description="把券商、行情数据商等第三方 MCP 服务接进来，让 AI 研究能用上它们的数据">
      <Callout tone="info" title="只读接入">
        外部服务里凡是下单、撤单、转账这类会动账户的工具，都会被强制屏蔽，不会交给 AI，也无法通过本系统调用。WealthPilot 只做研究与分析，不代你交易。
      </Callout>

      <Section title="已配置的连接" hint={list.data ? `配置文件：${list.data.config_file}` : undefined}>
        <DataState loading={list.loading} error={list.error} onRetry={list.reload}
          empty={connectors.length === 0 ? '还没有配置任何连接。按下方说明创建配置文件后，这里会列出来。' : undefined}>
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

      <Section title="可以接入什么">
        <div className="grid gap-3 sm:grid-cols-2">
          {CATALOG.map((item) => (
            <Card key={item.kind} className="p-4">
              <Tag tone={KIND[item.kind].tone}>{KIND[item.kind].label}</Tag>
              <p className="mt-2 text-sm font-medium text-ink">{item.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-slate">{item.body}</p>
            </Card>
          ))}
        </div>
        <p className="mt-3 text-[13px] text-steel">具体哪家机构提供 MCP 服务、地址和鉴权方式，以对方的官方文档为准。</p>
      </Section>

      <Section title="怎么接入" hint="连接器在服务器端配置，不通过网页添加：它相当于让服务器替你访问外部服务，应当由部署的人决定">
        <ol className="max-w-[760px] list-decimal space-y-2 pl-5 text-sm leading-relaxed text-charcoal">
          <li>在 <code className="rounded-xs bg-surface px-1 font-mono text-[13px]">backend/</code> 下把 <code className="rounded-xs bg-surface px-1 font-mono text-[13px]">connectors.example.json</code> 复制为 <code className="rounded-xs bg-surface px-1 font-mono text-[13px]">connectors.json</code>，填入对方提供的地址。</li>
          <li>令牌不要写进这个文件。<code className="rounded-xs bg-surface px-1 font-mono text-[13px]">auth_env</code> 填环境变量名，令牌本身放进 <code className="rounded-xs bg-surface px-1 font-mono text-[13px]">backend/.env</code>。</li>
          <li>回到这个页面点"测试连接"，确认哪些工具可用、哪些被屏蔽。</li>
          <li>把 <code className="rounded-xs bg-surface px-1 font-mono text-[13px]">enabled</code> 设为 true。之后在 AI 研究里问到行情或个股时，Agent 会连同这些外部工具一起使用，结果同样进入证据链接受校验。</li>
        </ol>
        <pre className="mt-4 max-w-[760px] overflow-x-auto rounded-lg bg-surface p-4 font-mono text-[12.5px] leading-relaxed text-charcoal">{EXAMPLE}</pre>
      </Section>
    </Page>
  )
}

export default ConnectorsPage
