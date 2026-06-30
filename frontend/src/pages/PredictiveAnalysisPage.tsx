import { Card } from '@/components/shared/Card'
import { ForecastPanel } from '@/components/forecast/ForecastPanel'
import { KPICard } from '@/components/workspace/KPICard'
import { useInsights } from '@/hooks/useInsights'
import { useDatasetStore } from '@/store/datasetStore'
import { TrendingUp, Activity, Target } from 'lucide-react'

export function PredictiveAnalysisPage() {
  const { currentDataset } = useDatasetStore()
  const datasetId = currentDataset?.id ?? null
  const { data: report, isLoading } = useInsights(datasetId)

  if (!currentDataset) {
    return (
      <div className="flex items-center justify-center h-64 text-dp-muted text-sm">
        Upload a dataset to run predictive analysis.
      </div>
    )
  }

  const forecasts = report?.forecasts ?? []
  const bestForecast = forecasts[0]

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Summary KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KPICard
          name="Models trained"
          value={forecasts.length}
          unit=""
          icon={Activity}
          accentColor="#5B4FE8"
          loading={isLoading}
          description="Forecasting models evaluated"
        />
        <KPICard
          name="Best MAPE"
          value={bestForecast?.mape ?? 0}
          unit="%"
          icon={Target}
          accentColor="#0F9B8E"
          loading={isLoading}
          description={bestForecast?.modelName ?? '—'}
        />
        <KPICard
          name="Time series cols"
          value={forecasts.length}
          unit=""
          icon={TrendingUp}
          accentColor="#F59E0B"
          loading={isLoading}
          description="Datetime columns detected"
        />
      </div>

      {/* Forecast charts */}
      <Card padding="md">
        <p className="dp-section-title">Forecasts &amp; predictions</p>
        <ForecastPanel forecasts={forecasts} loading={isLoading} />
      </Card>
    </div>
  )
}