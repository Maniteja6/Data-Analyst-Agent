import { clsx } from 'clsx'
import type { DatasetStatus } from '@/types/dataset'

const statusConfig: Record<DatasetStatus, { color: string; label: string; pulse: boolean }> = {
  uploaded:  { color: 'bg-dp-amber',   label: 'Waiting for upload', pulse: false },
  profiling: { color: 'bg-dp-violet',  label: 'Profiling…',         pulse: true  },
  profiled:  { color: 'bg-dp-violet',  label: 'Cleaning…',          pulse: true  },
  cleaning:  { color: 'bg-dp-teal',    label: 'Cleaning…',          pulse: true  },
  ready:     { color: 'bg-dp-emerald', label: 'Ready',              pulse: false },
  failed:    { color: 'bg-dp-rose',    label: 'Failed',             pulse: false },
}

interface StatusDotProps {
  status: DatasetStatus
  showLabel?: boolean
}

export function StatusDot({ status, showLabel = false }: StatusDotProps) {
  const cfg = statusConfig[status]
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={clsx('w-2 h-2 rounded-full', cfg.color, cfg.pulse && 'animate-pulse')} />
      {showLabel && <span className="text-xs text-dp-muted">{cfg.label}</span>}
    </span>
  )
}