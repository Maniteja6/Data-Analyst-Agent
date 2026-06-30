import { Card } from '@/components/shared/Card'
import { InsightList } from '@/components/insights/InsightList'
import { ExecutiveSummary } from '@/components/insights/ExecutiveSummary'
import { RecommendationCard } from '@/components/insights/RecommendationCard'
import { KPICard } from '@/components/workspace/KPICard'
import { useInsights } from '@/hooks/useInsights'
import { useDatasetStore } from '@/store/datasetStore'
import { Sparkles, CheckCircle2, Target } from 'lucide-react'

export function AIInsightsPage() {
  const { currentDataset } = useDatasetStore()
  const datasetId = currentDataset?.id ?? null
  const { data: report, isLoading } = useInsights(datasetId)

  if (!currentDataset) {
    return (
      <div className="flex items-center justify-center h-64 text-dp-muted text-sm">
        Upload a dataset to generate AI insights.
      </div>
    )
  }

  const insights         = report?.insights ?? []
  const recommendations  = report?.recommendations ?? []
  const highImpact       = insights.filter((i) => i.businessImpact === 'high').length
  const avgConfidence    = insights.length > 0
    ? insights.reduce((a, i) => a + i.confidence, 0) / insights.length : 0

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Summary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KPICard
          name="Total insights"
          value={insights.length}
          unit=""
          icon={Sparkles}
          accentColor="#5B4FE8"
          loading={isLoading}
        />
        <KPICard
          name="High-impact"
          value={highImpact}
          unit=""
          icon={Target}
          accentColor="#EF4444"
          loading={isLoading}
          description="Insights flagged as high business impact"
        />
        <KPICard
          name="Avg confidence"
          value={Math.round(avgConfidence * 100)}
          unit="%"
          icon={CheckCircle2}
          accentColor="#10B981"
          loading={isLoading}
          description="Critic-validated confidence score"
        />
      </div>

      {/* Executive summary */}
      <ExecutiveSummary summary={report?.executiveSummary ?? ''} loading={isLoading} />

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">
        {/* Insights */}
        <div className="xl:col-span-3">
          <Card padding="md">
            <p className="dp-section-title">AI insights — ranked by impact</p>
            <InsightList insights={insights} loading={isLoading} />
          </Card>
        </div>

        {/* Recommendations */}
        <div className="xl:col-span-2">
          <Card padding="md">
            <p className="dp-section-title">Recommendations</p>
            {isLoading ? (
              <p className="text-xs text-dp-muted">Loading…</p>
            ) : recommendations.length === 0 ? (
              <p className="text-xs text-dp-muted py-4 text-center">
                No recommendations yet.
              </p>
            ) : (
              <div className="space-y-3">
                {recommendations.map((r) => (
                  <RecommendationCard key={r.id} recommendation={r} />
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}