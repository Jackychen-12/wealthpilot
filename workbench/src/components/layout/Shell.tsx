import type React from 'react'
import { useState } from 'react'
import { Menu } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import { Drawer } from '../kit'
import { SidebarNav, type SidebarNavProps } from './SidebarNav'

/** 应用外壳：左侧暖灰色导航栏贴边到底，右侧白色画布；窄屏时导航收进抽屉。 */
export const Shell: React.FC<Omit<SidebarNavProps, 'onNavigate'>> = (navProps) => {
  const [mobileOpen, setMobileOpen] = useState(false)
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
        <main className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
      <Drawer open={mobileOpen} onClose={() => setMobileOpen(false)} title="导航" side="left" width="max-w-[280px]">
        <div className="-mx-6 -my-5 h-full"><SidebarNav {...navProps} onNavigate={() => setMobileOpen(false)} /></div>
      </Drawer>
    </div>
  )
}
