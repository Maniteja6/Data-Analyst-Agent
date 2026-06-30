import { AnomalyBadge } from './AnomalyBadge'
import type { AnomalyAlert } from '@/types/analytics'

interface AnomalyAlertItemProps {
  anomaly: AnomalyAlert
}

export function AnomalyAlertItem({ anomaly }: AnomalyAlertItemProps) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-dp-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <span className="font-mono text-xs font-semibold text-dp-text">{anomaly.columnName}</span>
          <AnomalyBadge severity={anomaly.severity} />
          <span className="text-2xs text-dp-muted capitalize">
            {anomaly.anomalyType.replace('_', ' ')}
          </span>
        </div>
        <p className="text-xs text-dp-text-secondary line-clamp-2">{anomaly.description}</p>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-2xs text-dp-muted">
            {anomaly.affectedRows.toLocaleString()} rows affected
          </span>
          <span className="text-2xs text-dp-muted">
            {anomaly.detectionMethod}
          </span>
          <span className="text-2xs text-dp-muted">
            {(anomaly.confidence * 100).toFixed(0)}% confidence
          </span>
        </div>
      </div>
    </div>
  )
}