import { InsightCard } from './InsightCard'
import { Skeleton } from '@/components/shared/Skeleton'
import type { Insight } from '@/types/insights'

interface InsightListProps {
  insights: Insight[]
  loading?: boolean
}

export function InsightList({ insights, loading }: InsightListProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)}
      </div>
    )
  }

  if (insights.length === 0) {
    return (
      <div className="text-center py-10 text-dp-muted text-sm">
        No insights yet — upload a dataset to generate AI analysis.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {insights.map((insight, i) => (
        <InsightCard key={insight.id} insight={insight} rank={i + 1} />
      ))}
    </div>
  )
}