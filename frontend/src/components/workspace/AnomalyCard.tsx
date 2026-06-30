import { AlertTriangle } from 'lucide-react'
import { Skeleton } from '@/components/shared/Skeleton'

interface AnomalyCardProps {
  count: number
  loading?: boolean
}

export function AnomalyCard({ count, loading }: AnomalyCardProps) {
  if (loading) {
    return (
      <div className="dp-card p-4 flex flex-col gap-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-10" />
      </div>
    )
  }

  return (
    <div className="dp-card p-4">
      <div className="flex items-start justify-between mb-2">
        <span className="text-2xs font-semibold uppercase tracking-widest text-dp-muted">
          Anomalies detected
        </span>
        <div className="w-7 h-7 rounded-md flex items-center justify-center bg-rose-50">
          <AlertTriangle size={14} className="text-dp-rose" />
        </div>
      </div>
      <div className="text-3xl font-bold text-dp-text leading-none">{count}</div>
      <p className="text-xs text-dp-muted mt-1">
        Cleaning pipeline: duplicates removed + missing cells flagged before training.
      </p>
      <div className="mt-3 h-0.5 w-8 rounded-full bg-dp-rose" />
    </div>
  )
}