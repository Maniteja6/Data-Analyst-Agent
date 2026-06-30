import { clsx } from 'clsx'
import type { LucideIcon } from 'lucide-react'
import { Tooltip } from '@/components/shared/Tooltip'

interface SidebarNavItemProps {
  icon: LucideIcon
  label: string
  active: boolean
  collapsed: boolean
  onClick: () => void
}

export function SidebarNavItem({ icon: Icon, label, active, collapsed, onClick }: SidebarNavItemProps) {
  const button = (
    <button
      onClick={onClick}
      className={clsx(
        'w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors duration-150',
        active
          ? 'bg-dp-violet text-white'
          : 'text-white/60 hover:text-white hover:bg-white/10',
        collapsed && 'justify-center',
      )}
    >
      <Icon size={16} className="flex-shrink-0" />
      {!collapsed && <span>{label}</span>}
    </button>
  )

  if (collapsed) {
    return <Tooltip content={label}>{button}</Tooltip>
  }
  return button
}