import { AlertTriangle } from 'lucide-react'
import { AnomalyAlertItem } from './AnomalyAlertItem'
import { Skeleton } from '@/components/shared/Skeleton'
import type { AnomalyAlert } from '@/types/analytics'

interface AnomalyAlertPanelProps {
  anomalies: AnomalyAlert[]
  loading?: boolean
}

export function AnomalyAlertPanel({ anomalies, loading }: AnomalyAlertPanelProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
      </div>
    )
  }

  if (anomalies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center mb-3">
          <AlertTriangle size={18} className="text-dp-emerald" />
        </div>
        <p className="text-sm font-medium text-dp-text">No anomalies detected</p>
        <p className="text-xs text-dp-muted mt-1">Your data quality looks clean.</p>
      </div>
    )
  }

  const bySeverity = ['critical', 'high', 'medium', 'low'] as const
  const sorted = [...anomalies].sort(
    (a, b) => bySeverity.indexOf(a.severity) - bySeverity.indexOf(b.severity),
  )

  return (
    <div>
      {sorted.map((a) => <AnomalyAlertItem key={a.id} anomaly={a} />)}
    </div>
  )
}