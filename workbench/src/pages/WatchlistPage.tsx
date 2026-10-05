import type React from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApi, type Security, type WatchItem } from '../api'
import { AskAi } from '../components/AskAi'
import { SecuritySearch, securityPath } from '../components/SecuritySearch'
import { Button, Callout, ConfirmDialog, Tag } from '../components/kit'
import { ASSET, DataState, Page, Section, Table, Td, signClass, signed } from '../components/ui'

const NoteCell: React.FC<{ item: WatchItem; onSaved: () => void; onError: (m: string) => void }> = ({ item, onSaved, onError }) => {
  const [note, setNote] = useState(item.note)
  const save = async () => {
    if (note === item.note) return
    try { await api.updateWatch(item.id, note); onSaved() } catch (e) { setNote(item.note); onError(e instanceof Error ? e.message : '备注保存失败') }
  }
  return (
    <input value={note} maxLength={200} placeholder="加一句备注，比如为什么关注" aria-label={`${item.name} 的备注`}
      onChange={(e) => setNote(e.target.value)} onBlur={() => void save()}
      onKeyDown={(e) => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) e.currentTarget.blur() }}
      className="w-full min-w-[160px] rounded-sm bg-transparent px-1.5 py-1 text-sm text-charcoal outline-none placeholder:text-stone hover:bg-hover focus:bg-canvas focus:ring-1 focus:ring-primary" />
  )
}

const WatchlistPage: React.FC = () => {
  const watch = useApi(api.watchlist)
  const [error, setError] = useState('')
  const [removing, setRemoving] = useState<WatchItem | null>(null)
  const rows = watch.data ?? []

  const add = async (s: Security) => {
    setError('')
    try { await api.addWatch({ code: s.code, name: s.name, asset_type: s.asset_type }); watch.reload() } catch (e) { setError(e instanceof Error ? e.message : '添加失败') }
  }
  const names = rows.filter((w) => w.asset_type !== 'fund').slice(0, 3).map((w) => w.name)

  return (
    <Page title="自选股" description="关注的股票、ETF 和基金，带一句自己的备注"
      actions={names.length >= 2 ? <AskAi label="对比前几只" question={`对比一下${names.join('、')}的基本面和估值`} /> : undefined}>
      <SecuritySearch className="max-w-sm" placeholder="搜索并加入自选" onPick={(s) => void add(s)} />
      {error ? <Callout tone="danger">{error}</Callout> : null}

      <Section title="自选列表" hint={rows.length ? `共 ${rows.length} 只 · 股票与 ETF 显示最新行情` : undefined}>
        <DataState loading={watch.loading && !watch.data} error={watch.error} onRetry={watch.reload} empty={rows.length === 0 ? '还没有自选。在上面搜索名称或代码，选中即加入。' : undefined}>
          <Table minWidth={760} head={[{ label: '名称' }, { label: '类型' }, { label: '最新价', right: true }, { label: '涨跌幅', right: true }, { label: '备注', className: 'w-[36%]' }, { label: '', right: true }]}>
            {rows.map((w) => (
              <tr key={w.id}>
                <Td><Link to={securityPath(w)} className="font-medium text-ink hover:underline">{w.name || w.code}</Link><div className="font-mono text-xs text-stone">{w.code}</div></Td>
                <Td><Tag tone={w.asset_type === 'fund' ? 'blue' : w.asset_type === 'etf' ? 'green' : 'purple'}>{ASSET[w.asset_type] ?? w.asset_type}</Tag></Td>
                <Td right num>{w.price == null ? '—' : w.price.toFixed(w.price < 10 ? 3 : 2)}</Td>
                <Td right num className={signClass(w.change_pct)}>{signed(w.change_pct, 2, '%')}</Td>
                <Td><NoteCell item={w} onSaved={watch.reload} onError={setError} /></Td>
                <Td right className="whitespace-nowrap">
                  {w.asset_type === 'fund' ? null : <AskAi label="研究" question={`帮我深度分析一下${w.name}（${w.code}）`} />}
                  <Button size="xs" variant="danger" className="ml-1" onClick={() => setRemoving(w)}>移除</Button>
                </Td>
              </tr>
            ))}
          </Table>
        </DataState>
      </Section>

      <ConfirmDialog open={removing != null} title="移出自选" confirmText="移除"
        message={removing ? `把「${removing.name}」移出自选？备注会一并删除。` : ''}
        onCancel={() => setRemoving(null)}
        onConfirm={() => {
          const target = removing
          setRemoving(null)
          if (target) api.removeWatch(target.id).then(watch.reload).catch((e) => setError(e instanceof Error ? e.message : '移除失败'))
        }} />
    </Page>
  )
}

export default WatchlistPage
