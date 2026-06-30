import {
  LayoutDashboard, BarChart2, TrendingUp, ShieldCheck,
  Sparkles, Download, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { clsx } from 'clsx'
import { useUIStore } from '@/store/UiStore'
import { SidebarNavItem } from './SidebarNavItem'

const NAV_ITEMS = [
  { id: 'dashboard',           label: 'Dashboard',           icon: LayoutDashboard },
  { id: 'data-insights',       label: 'Data Insights',       icon: BarChart2 },
  { id: 'predictive-analysis', label: 'Predictive Analysis', icon: TrendingUp },
  { id: 'data-quality',        label: 'Data Quality',        icon: ShieldCheck },
  { id: 'ai-insights',         label: 'AI Insights',         icon: Sparkles },
  { id: 'export-results',      label: 'Export Results',      icon: Download },
] as const

export function Sidebar() {
  const { sidebarCollapsed, activePage, setActivePage, toggleSidebar } = useUIStore()

  return (
    <aside
      className={clsx(
        'flex flex-col bg-gradient-to-b from-dp-navy to-dp-navy-light h-screen',
        'transition-all duration-300 ease-in-out flex-shrink-0',
        sidebarCollapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-4 pt-6 pb-5 select-none">
        <div className="w-8 h-8 rounded-lg bg-dp-violet flex items-center justify-center flex-shrink-0">
          <span className="text-white font-bold text-sm">DP</span>
        </div>
        {!sidebarCollapsed && (
          <div className="animate-fade-in">
            <div className="text-white font-semibold text-base leading-tight">DataPilot</div>
            <div className="text-white/40 text-2xs leading-tight">Premium analytics workspace</div>
          </div>
        )}
      </div>

      {/* New Project button */}
      {!sidebarCollapsed && (
        <div className="px-3 mb-5">
          <button className="w-full flex items-center justify-center gap-2 py-2 rounded-md
            bg-dp-violet hover:bg-dp-violet-light text-white text-sm font-medium
            transition-colors duration-150">
            + New Project
          </button>
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <SidebarNavItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            active={activePage === item.id}
            collapsed={sidebarCollapsed}
            onClick={() => setActivePage(item.id)}
          />
        ))}
      </nav>

      {/* Bottom status */}
      {!sidebarCollapsed && (
        <div className="px-4 pb-4">
          <p className="text-white/30 text-2xs">Upload a dataset to begin.</p>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className="mx-2 mb-4 p-2 rounded-md text-white/40 hover:text-white
          hover:bg-white/10 transition-colors flex items-center justify-center"
        aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </aside>
  )
}