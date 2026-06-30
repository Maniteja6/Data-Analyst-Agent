import { clsx } from 'clsx'
import { Badge } from '@/components/shared/Badge'
import type { Insight } from '@/types/insights'

interface InsightCardProps {
  insight: Insight
  rank?: number
}

const impactVariant = {
  high:   'rose' as const,
  medium: 'amber' as const,
  low:    'neutral' as const,
}

export function InsightCard({ insight, rank }: InsightCardProps) {
  return (
    <div className="dp-card p-4 animate-slide-up hover:shadow-dp-elevated transition-shadow duration-200">
      <div className="flex items-start gap-3">
        {rank != null && (
          <span className="text-xl font-bold text-dp-border flex-shrink-0 w-7 text-center leading-none mt-0.5">
            {rank}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Badge variant={impactVariant[insight.businessImpact]}>
              {insight.businessImpact} impact
            </Badge>
            {insight.hasAnomalyReference && (
              <Badge variant="amber">anomaly</Badge>
            )}
          </div>
          <h3 className="text-sm font-semibold text-dp-text mb-1">{insight.headline}</h3>
          <p className="text-xs text-dp-text-secondary leading-relaxed">{insight.explanation}</p>
          {insight.sourceColumns.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {insight.sourceColumns.map((col) => (
                <span key={col}
                  className="text-2xs font-mono bg-dp-canvas text-dp-muted px-1.5 py-0.5 rounded">
                  {col}
                </span>
              ))}
            </div>
          )}
          <div className="mt-2 flex items-center gap-1">
            <div className="h-1 flex-1 bg-dp-border rounded-full overflow-hidden">
              <div
                className="h-full bg-dp-violet rounded-full"
                style={{ width: `${insight.confidence * 100}%` }}
              />
            </div>
            <span className="text-2xs text-dp-muted w-12 text-right">
              {(insight.confidence * 100).toFixed(0)}% conf.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}