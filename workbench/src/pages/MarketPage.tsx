import type React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, runTool, useApi, type MarketOverview, type Mover, type SectorRanking } from '../api'
import { Heatmap } from '../components/charts'
import { DataState, Metric, Metrics, Page, Section, signClass, signed } from '../components/ui'
import { cn } from '../utils/cn'
import { MacroSection, RecapSection } from './DepthSections'

const toolData = <T,>(res: { data: T | string } | null): T | null => (res && typeof res.data !== 'string' ? res.data : null)

const MoverList: React.FC<{ title: string; rows: Mover[] }> = ({ title, rows }) => (
  <div className="min-w-0 flex-1 rounded-lg border border-hairline">
    <p className="border-b border-hairline-soft px-4 py-2 text-[13px] font-medium text-steel">{title}</p>
    <ul className="divide-y divide-hairline-soft">
      {rows.map((m) => (
        <li key={m.code}>
          <Link to={`/stock/${m.code}`} className="flex items-center gap-3 px-4 py-1.5 text-sm hover:bg-surface-soft">
            <span className="min-w-0 flex-1 truncate text-ink">{m.name}<span className="ml-2 text-xs text-stone">{m.industry}</span></span>
            <span className={cn('w-16 shrink-0 text-right tabular-nums', signClass(m.change_pct))}>{signed(m.change_pct, 2, '%')}</span>
          </Link>
        </li>
      ))}
    </ul>
  </div>
)

/** 大盘：今天市场本身怎么样。指数和涨跌家数、涨停与题材、行业强弱、涨跌幅榜。都不调用模型。 */
const MarketPage: React.FC = () => {
  const navigate = useNavigate()
  const market = useApi(() => runTool<MarketOverview | string>('get_market_overview'))
  const sectors = useApi(() => runTool<SectorRanking | string>('get_sector_ranking', { top: 20 }))
  const movers = useApi(api.movers)
  const m = toolData(market.data)
  const s = toolData(sectors.data)
  return (
    <Page title="大盘" description="今天市场本身怎么样：指数、涨停与题材、行业强弱。收盘后看最完整">
      <Section title="指数与涨跌家数" hint={m ? `截至 ${m.breadth.trade_date} 收盘` : undefined}>
        <DataState loading={market.loading} error={market.error} onRetry={market.reload} empty={!market.loading && !m ? String(market.data?.data ?? '没有取到大盘数据') : undefined}>
          {m ? (
            <Metrics>
              {m.indices.map((i) => <Metric key={i.name} label={i.name} value={i.value} tone={i.up ? 'text-up' : 'text-down'} hint={i.change} />)}
              <Metric label="上涨 / 下跌（家）" value={<><span className="text-up">{m.breadth.up}</span><span className="mx-1.5 text-stone">/</span><span className="text-down">{m.breadth.down}</span></>}
                hint={`涨跌中位数 ${signed(m.breadth.median_change_pct, 2, '%')}`} />
            </Metrics>
          ) : null}
        </DataState>
      </Section>

      <RecapSection />

      {s || movers.data?.gainers.length ? (
        <Section title="行业与个股" hint="哪些行业在涨、哪些在跌，谁涨得最多">
          {s ? (
            <>
              <Heatmap items={[...s.top, ...s.bottom].map((x) => ({ name: x.industry, size: x.stock_count, change: x.median_change_pct, sub: x.leader.name, code: x.leader.code }))}
                onPick={(i) => i.code && navigate(`/stock/${i.code}`)} />
              <p className="mt-2 text-[13px] text-steel">块越大公司越多，颜色越深涨跌越大（红涨绿跌）；只画涨跌幅最靠前和最靠后的行业，点一块看它的领涨股。</p>
            </>
          ) : null}
          {movers.data?.gainers.length ? (
            <div className="mt-3 flex flex-col gap-3 md:flex-row">
              <MoverList title={`涨幅榜（市值 ${movers.data.min_mv_yi} 亿以上）`} rows={movers.data.gainers} />
              <MoverList title="跌幅榜" rows={movers.data.losers} />
            </div>
          ) : null}
        </Section>
      ) : null}
    </Page>
  )
}

/** 宏观：个股研究之外的那层背景。月度数据，不用天天看。 */
export const MacroPage: React.FC = () => (
  <Page title="宏观" description="景气、物价、货币信贷、利率。月度数据次月公布，不用天天看">
    <MacroSection />
  </Page>
)

export default MarketPage
