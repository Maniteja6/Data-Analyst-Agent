import { Skeleton } from '@/components/shared/Skeleton'
import { Sparkles } from 'lucide-react'

interface ExecutiveSummaryProps {
  summary: string
  loading?: boolean
}

export function ExecutiveSummary({ summary, loading }: ExecutiveSummaryProps) {
  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/6" />
      </div>
    )
  }

  if (!summary) {
    return (
      <p className="text-xs text-dp-muted italic">
        Executive summary will appear after analysis completes.
      </p>
    )
  }

  return (
    <div className="bg-dp-violet-dim rounded-dp p-4">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={13} className="text-dp-violet flex-shrink-0" />
        <span className="text-2xs font-semibold uppercase tracking-widest text-dp-violet">
          AI Executive Summary
        </span>
      </div>
      <p className="text-sm text-dp-text leading-relaxed">{summary}</p>
    </div>
  )
}