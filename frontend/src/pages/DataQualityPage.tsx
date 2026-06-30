import { Card } from '@/components/shared/Card'
import { DataQualityScore } from '@/components/analytics/DataQualityScore'
import { AnomalyAlertPanel } from '@/components/anomalies/AnomalyAlertPanel'
import { useAnalysis } from '@/hooks/useAnalysis'
import { useDatasetStore } from '@/store/datasetStore'
import { Skeleton } from '@/components/shared/Skeleton'

export function DataQualityPage() {
  const { currentDataset } = useDatasetStore()
  const datasetId = currentDataset?.id ?? null
  const { profileQuery, anomaliesQuery } = useAnalysis(datasetId)
  const profile = profileQuery.data

  if (!currentDataset) {
    return (
      <div className="flex items-center justify-center h-64 text-dp-muted text-sm">
        Upload a dataset to view data quality metrics.
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Quality score */}
        <Card padding="md">
          <p className="dp-section-title">Quality assessment</p>
          {profileQuery.isLoading || !profile ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <DataQualityScore
              completenessScore={profile.completenessScore}
              consistencyScore={profile.consistencyScore}
              rowCount={profile.rowCount}
              columnCount={profile.columnCount}
              duplicateCount={profile.duplicateCount}
            />
          )}
        </Card>

        {/* Cleaning pipeline info */}
        <Card padding="md">
          <p className="dp-section-title">Cleaning pipeline</p>
          {profileQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              {[
                { label: 'Duplicate rows removed',    value: profile?.duplicateCount ?? 0 },
                { label: 'Missing values imputed',    value: profile?.columnProfiles.reduce((a, c) => a + c.nullCount, 0) ?? 0 },
                { label: 'Type coercions applied',    value: (profile?.columnProfiles.length ?? 0) },
                { label: 'Outliers flagged',          value: anomaliesQuery.data?.filter((a) => a.anomalyType === 'outlier').length ?? 0 },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between py-2
                  border-b border-dp-border last:border-0">
                  <span className="text-xs text-dp-text-secondary">{label}</span>
                  <span className="text-xs font-semibold text-dp-text font-mono">
                    {value.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Anomalies */}
      <Card padding="md">
        <p className="dp-section-title">
          Anomaly alerts
          {anomaliesQuery.data && anomaliesQuery.data.length > 0 && (
            <span className="ml-2 dp-badge bg-rose-50 text-dp-rose border border-rose-100">
              {anomaliesQuery.data.length}
            </span>
          )}
        </p>
        <AnomalyAlertPanel
          anomalies={anomaliesQuery.data ?? []}
          loading={anomaliesQuery.isLoading}
        />
      </Card>
    </div>
  )
}