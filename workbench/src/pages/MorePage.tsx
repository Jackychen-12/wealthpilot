import type React from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { MORE_TOOLS } from '../components/layout/sections'
import { Page } from '../components/ui'

/** 更多工具：功能都在，只是不在“研究 → 留下判断 → 回头看”这条主线上，所以不占侧栏和页签的位置。 */
const MorePage: React.FC = () => (
  <Page title="更多工具" description="这些功能都还在，只是不在主线上：主线是研究一只股票、留下可核对的判断、到期回头看">
    <ul className="grid gap-3 sm:grid-cols-2">
      {MORE_TOOLS.map((t) => (
        <li key={t.to}>
          <Link to={t.to} className="group flex h-full flex-col gap-1 rounded-lg border border-hairline p-4 transition-colors hover:bg-surface-soft">
            <span className="flex items-center gap-1 text-sm font-semibold text-ink">{t.label}<ArrowRight className="h-3.5 w-3.5 text-stone transition-transform group-hover:translate-x-0.5" /></span>
            <span className="text-[13px] leading-relaxed text-slate">{t.what}</span>
          </Link>
        </li>
      ))}
    </ul>
  </Page>
)

export default MorePage
