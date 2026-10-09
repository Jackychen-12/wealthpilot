import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { Menu } from 'lucide-react'
import { Outlet, useLocation } from 'react-router-dom'
import { DEMO } from '../../api'
import { Drawer } from '../kit'
import { SidebarNav, type SidebarNavProps } from './SidebarNav'
import { SectionTabs } from './sections'

/** 应用外壳：左侧暖灰色导航栏贴边到底，右侧白色画布；窄屏时导航收进抽屉。 */
export const Shell: React.FC<Omit<SidebarNavProps, 'onNavigate'>> = (navProps) => {
  const [mobileOpen, setMobileOpen] = useState(false)
  // 换页后回到顶部，否则会停在上一页滚到的位置
  const mainRef = useRef<HTMLElement>(null)
  const { pathname } = useLocation()
  useEffect(() => { mainRef.current?.scrollTo({ top: 0 }) }, [pathname])
  return (
    <div className="flex h-full bg-canvas text-ink">
      <aside className="hidden w-60 shrink-0 border-r border-hairline bg-surface-soft lg:block" aria-label="侧边导航">
        <SidebarNav {...navProps} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-2 border-b border-hairline px-3 lg:hidden">
          <button type="button" onClick={() => setMobileOpen(true)} aria-label="打开导航"
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate hover:bg-hover">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold">WealthPilot</span>
        </div>
        {DEMO ? (
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-hairline bg-tint-yellow px-4 py-2 text-[13px] text-on-yellow">
            <span><b>在线演示</b> · 一份示例组合在真实行情和真实模型上跑出的结果，录制后回放，只读、非实时</span>
            <a className="font-medium underline underline-offset-2" href="https://github.com/Jackychen-12/wealthpilot#quick-start" target="_blank" rel="noreferrer">在本地运行完整版</a>
          </div>
        ) : null}
        <SectionTabs alertCount={navProps.alertCount} />
        <main ref={mainRef} className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
      <Drawer open={mobileOpen} onClose={() => setMobileOpen(false)} title="导航" side="left" width="max-w-[280px]">
        <div className="-mx-6 -my-5 h-full"><SidebarNav {...navProps} onNavigate={() => setMobileOpen(false)} /></div>
      </Drawer>
    </div>
  )
}
