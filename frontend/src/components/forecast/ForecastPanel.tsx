import { ForecastChart } from './ForecastChart'
import { ForecastSummary } from './ForecastSummary'
import { Skeleton } from '@/components/shared/Skeleton'
import type { ForecastResult } from '@/types/insights'

interface ForecastPanelProps {
  forecasts: ForecastResult[]
  loading?: boolean
}

export function ForecastPanel({ forecasts, loading }: ForecastPanelProps) {
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (forecasts.length === 0) {
    return (
      <div className="py-8 text-center text-dp-muted text-sm">
        <p className="font-medium text-dp-text-secondary mb-1">No time series detected</p>
        <p className="text-xs">Run Full Analysis with a target selected to populate predictions.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {forecasts.map((f) => (
        <div key={f.id} className="dp-card p-4">
          <ForecastSummary forecast={f} />
          <div className="mt-3">
            <ForecastChart predictions={f.predictions} targetColumn={f.targetColumn} />
          </div>
          {f.narration && (
            <p className="text-xs text-dp-text-secondary mt-3 pt-3 border-t border-dp-border leading-relaxed">
              {f.narration}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}