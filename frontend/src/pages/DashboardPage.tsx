import { useState } from 'react'
import { KPIGrid } from '@/components/workspace/KPIGrid'
import { UploadDropzone } from '@/components/upload/UploadDropzone'
import { UploadProgress } from '@/components/upload/UploadProgress'
import { FileValidation } from '@/components/upload/FileValidation'
import { ForecastPanel } from '@/components/forecast/ForecastPanel'
import { AnomalyAlertPanel } from '@/components/anomalies/AnomalyAlertPanel'
import { InsightList } from '@/components/insights/InsightList'
import { ExecutiveSummary } from '@/components/insights/ExecutiveSummary'
import { Card } from '@/components/shared/Card'
import { useFileUpload } from '@/hooks/useFileUpload'
import { useInsights } from '@/hooks/useInsights'
import { useAnalysis } from '@/hooks/useAnalysis'
import { useDatasetStore } from '@/store/datasetStore'
import { useJobStatus } from '@/hooks/useJobStatus'

export function DashboardPage() {
  const { currentDataset, uploadProgress, uploadStep, jobId } = useDatasetStore()
  const { upload, isUploading, error, clearError } = useFileUpload()
  const { data: jobStatus } = useJobStatus(jobId)

  const datasetId = currentDataset?.id ?? null
  const { data: report, isLoading: insightsLoading } = useInsights(datasetId)
  const { anomaliesQuery } = useAnalysis(datasetId)

  const showProgress = isUploading || (jobStatus && jobStatus.status === 'running')
  const isReady = currentDataset?.status === 'ready'

  return (
    <div className="space-y-5 animate-fade-in">
      {/* KPI overview row */}
      <KPIGrid
        kpis={report?.kpis ?? []}
        datasetsProcessed={isReady ? 1 : 0}
        anomalyCount={anomaliesQuery.data?.length ?? 0}
        modelsBuilt={report?.forecasts?.length ?? 0}
        filename={currentDataset?.originalName}
        status={currentDataset?.status}
        loading={insightsLoading}
      />

      {/* Upload area */}
      <div className="space-y-2">
        <p className="dp-section-title">Upload dataset</p>
        <p className="text-xs text-dp-muted -mt-2 mb-2">
          Drag &amp; drop a CSV/XLSX to start analysis.
        </p>
        <UploadDropzone onFile={upload} isUploading={isUploading} />
        <FileValidation error={error} />
      </div>

      {/* Progress */}
      {showProgress && (
        <UploadProgress
          progress={jobStatus?.progress ?? uploadProgress}
          step={jobStatus?.step ?? uploadStep}
          status={jobStatus?.status === 'failed' ? 'failed' : 'running'}
          filename={currentDataset?.originalName}
        />
      )}

      {/* Main content — shown after upload */}
      {isReady && (
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">
          {/* Left: insights */}
          <div className="xl:col-span-3 space-y-5">
            <Card padding="md">
              <p className="dp-section-title">Executive summary</p>
              <ExecutiveSummary
                summary={report?.executiveSummary ?? ''}
                loading={insightsLoading}
              />
            </Card>
            <Card padding="md">
              <p className="dp-section-title">Top insights</p>
              <InsightList
                insights={report?.insights?.slice(0, 5) ?? []}
                loading={insightsLoading}
              />
            </Card>
          </div>

          {/* Right: forecast + anomalies */}
          <div className="xl:col-span-2 space-y-5">
            <Card padding="md">
              <p className="dp-section-title">Forecast / predictions</p>
              <p className="text-xs text-dp-muted -mt-2 mb-3">
                Model outcomes for the selected target.
              </p>
              <ForecastPanel
                forecasts={report?.forecasts ?? []}
                loading={insightsLoading}
              />
            </Card>
            <Card padding="md">
              <p className="dp-section-title">Anomaly alerts</p>
              <p className="text-xs text-dp-muted -mt-2 mb-3">
                Data quality signals from the cleaning pipeline.
              </p>
              <AnomalyAlertPanel
                anomalies={anomaliesQuery.data ?? []}
                loading={anomaliesQuery.isLoading}
              />
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}