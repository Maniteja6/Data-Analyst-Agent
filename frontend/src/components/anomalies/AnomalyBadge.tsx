import { clsx } from 'clsx'
import type { AnomalyAlert } from '@/types/analytics'

const severityStyles: Record<AnomalyAlert['severity'], string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high:     'bg-amber-100 text-amber-700 border-amber-200',
  medium:   'bg-sky-100 text-sky-700 border-sky-200',
  low:      'bg-emerald-100 text-emerald-700 border-emerald-200',
}

export function AnomalyBadge({ severity }: { severity: AnomalyAlert['severity'] }) {
  return (
    <span className={clsx(
      'dp-badge border capitalize',
      severityStyles[severity],
    )}>
      {severity}
    </span>
  )
}