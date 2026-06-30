import { clsx } from 'clsx'
import { ArrowRight } from 'lucide-react'
import type { Recommendation } from '@/types/insights'

const priorityConfig = {
  high:   { dot: 'bg-dp-rose',    label: 'High priority'   },
  medium: { dot: 'bg-dp-amber',   label: 'Medium priority' },
  low:    { dot: 'bg-dp-emerald', label: 'Low priority'    },
}

interface RecommendationCardProps {
  recommendation: Recommendation
}

export function RecommendationCard({ recommendation: rec }: RecommendationCardProps) {
  const cfg = priorityConfig[rec.priority]

  return (
    <div className="dp-card p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0', cfg.dot)} />
        <span className="text-2xs font-semibold uppercase tracking-widest text-dp-muted">
          {cfg.label}
        </span>
      </div>
      <h4 className="text-sm font-semibold text-dp-text mb-1">{rec.title}</h4>
      <p className="text-xs text-dp-text-secondary mb-2 leading-relaxed">{rec.situation}</p>
      <div className="flex items-start gap-2 bg-dp-canvas rounded-md p-2.5">
        <ArrowRight size={12} className="text-dp-violet mt-0.5 flex-shrink-0" />
        <p className="text-xs text-dp-text">{rec.action}</p>
      </div>
      {rec.estimatedImpact && (
        <p className="text-2xs text-dp-muted mt-2">
          Estimated impact: <span className="text-dp-teal font-medium">{rec.estimatedImpact}</span>
        </p>
      )}
    </div>
  )
}