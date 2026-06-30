import { clsx } from 'clsx'
import type { LucideIcon } from 'lucide-react'
import type { KPITrend } from '@/types/insights'
import { Skeleton } from '@/components/shared/Skeleton'
import { formatKPIValue } from '@/utils/formatters'
import { TREND_COLORS } from '@/utils/colorPalette'

interface KPICardProps {
  name: string
  value: number
  unit: string
  trend?: KPITrend
  trendPct?: number | null
  icon?: LucideIcon
  accentColor?: string
  loading?: boolean
  description?: string
}

export function KPICard({
  name, value, unit, trend, trendPct, icon: Icon,
  accentColor = '#5B4FE8', loading, description,
}: KPICardProps) {
  if (loading) {
    return (
      <div className="dp-card p-4 flex flex-col gap-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-8 w-16" />
        <Skeleton className="h-3 w-32" />
      </div>
    )
  }

  return (
    <div className="dp-card p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-2xs font-semibold uppercase tracking-widest text-dp-muted">
          {name}
        </span>
        {Icon && (
          <div className="w-7 h-7 rounded-md flex items-center justify-center"
            style={{ backgroundColor: accentColor + '18' }}>
            <Icon size={14} style={{ color: accentColor }} />
          </div>
        )}
      </div>

      <div className="text-3xl font-bold text-dp-text leading-none mb-1">
        {formatKPIValue(value, unit)}
      </div>

      {(trend || description) && (
        <p className="text-xs text-dp-muted mt-1">
          {trendPct != null && (
            <span className={clsx('font-semibold mr-1')} style={{ color: TREND_COLORS[trend ?? 'unknown'] }}>
              {trendPct > 0 ? '+' : ''}{trendPct.toFixed(1)}%
            </span>
          )}
          {description}
        </p>
      )}

      {/* Accent bar */}
      <div className="mt-3 h-0.5 w-8 rounded-full" style={{ backgroundColor: accentColor }} />
    </div>
  )
}