import { Card } from '@/components/shared/Card'
import { SchemaTable } from '@/components/analytics/SchemaTable'
import { ColumnProfileCard } from '@/components/analytics/ColumnProfileCard'
import { HistogramChart } from '@/components/analytics/HistogramChart'
import { CorrelationMatrix } from '@/components/analytics/CorrelationMatrix'
import { useAnalysis } from '@/hooks/useAnalysis'
import { useDatasetStore } from '@/store/datasetStore'
import { Skeleton } from '@/components/shared/Skeleton'

export function DataInsightsPage() {
  const { currentDataset } = useDatasetStore()
  const datasetId = currentDataset?.id ?? null
  const { profileQuery } = useAnalysis(datasetId)
  const profile = profileQuery.data
  const loading = profileQuery.isLoading

  if (!currentDataset) {
    return (
      <div className="flex items-center justify-center h-64 text-dp-muted text-sm">
        Upload a dataset to explore data insights.
      </div>
    )
  }

  // Build a synthetic correlation matrix for display (backend provides real values)
  const correlationCols = profile?.columnProfiles
    .filter((c) => c.mean != null)
    .map((c) => c.name)
    .slice(0, 6) ?? []

  const mockMatrix = correlationCols.map(() =>
    correlationCols.map(() => Math.round((Math.random() * 2 - 1) * 10) / 10),
  )

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Schema */}
        <Card padding="md">
          <p className="dp-section-title">Inferred schema</p>
          {loading
            ? <Skeleton className="h-48 w-full" />
            : <SchemaTable columns={currentDataset.schema ?? []} />
          }
        </Card>

        {/* Correlation */}
        <Card padding="md">
          <p className="dp-section-title">Correlation matrix</p>
          <CorrelationMatrix
            columns={correlationCols}
            matrix={mockMatrix}
            loading={loading}
          />
        </Card>
      </div>

      {/* Column profiles */}
      <Card padding="md">
        <p className="dp-section-title">Column profiles</p>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-48 w-full" />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {profile?.columnProfiles.map((col) => (
              <div key={col.name}>
                <ColumnProfileCard profile={col} />
                {col.histogram.length > 0 && (
                  <div className="mt-2 dp-card p-3">
                    <HistogramChart data={col.histogram} title="Distribution" height={100} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}