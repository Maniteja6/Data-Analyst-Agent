import { clsx } from 'clsx'
import type { ForecastResult } from '@/types/insights'
import { TREND_COLORS } from '@/utils/colorPalette'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

const TrendIcon = {
  up:      TrendingUp,
  down:    TrendingDown,
  flat:    Minus,
  unknown: Minus,
}

interface ForecastSummaryProps {
  forecast: ForecastResult
}

export function ForecastSummary({ forecast }: ForecastSummaryProps) {
  const Icon = TrendIcon[forecast.trendDirection]
  const trendColor = TREND_COLORS[forecast.trendDirection === 'flat' ? 'stable' : forecast.trendDirection]

  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-dp-text">{forecast.targetColumn}</span>
          <Icon size={14} style={{ color: trendColor }} />
        </div>
        <p className="text-xs text-dp-muted mt-0.5">
          {forecast.modelName} · {forecast.horizonLabel} · {forecast.frequency}
        </p>
      </div>
      <div className="flex gap-4">
        {forecast.mape != null && (
          <div className="text-center">
            <div className="text-sm font-bold text-dp-text">{forecast.mape.toFixed(1)}%</div>
            <div className="text-2xs text-dp-muted">MAPE</div>
          </div>
        )}
        {forecast.rmse != null && (
          <div className="text-center">
            <div className="text-sm font-bold text-dp-text">{forecast.rmse.toFixed(2)}</div>
            <div className="text-2xs text-dp-muted">RMSE</div>
          </div>
        )}
      </div>
    </div>
  )
}