import { Sparkles, Cpu } from 'lucide-react'
import { WorkspaceCard } from './WorkspaceCard'
import { KPICard } from './KPICard'
import { AnomalyCard } from './AnomalyCard'
import type { KPI } from '@/types/insights'
import type { DatasetStatus } from '@/types/dataset'

interface KPIGridProps {
  kpis: KPI[]
  datasetsProcessed: number
  anomalyCount: number
  modelsBuilt?: number
  filename?: string
  status?: DatasetStatus
  loading?: boolean
}

export function KPIGrid({
  kpis, datasetsProcessed, anomalyCount, modelsBuilt = 0,
  filename, status, loading,
}: KPIGridProps) {
  const insightCount = kpis.length

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
      {/* Large workspace card spans first column */}
      <WorkspaceCard
        datasetsProcessed={datasetsProcessed}
        filename={filename}
        status={status}
      />

      {/* KPI cluster */}
      <div className="flex flex-col gap-4">
        <KPICard
          name="Insights generated"
          value={insightCount}
          unit=""
          icon={Sparkles}
          accentColor="#5B4FE8"
          loading={loading}
          description="AI-ranked business insights"
        />
        <KPICard
          name="Models built"
          value={modelsBuilt}
          unit=""
          icon={Cpu}
          accentColor="#0F9B8E"
          loading={loading}
          description="Forecasting + ML models trained"
        />
      </div>

      {/* Anomaly card */}
      <AnomalyCard count={anomalyCount} loading={loading} />
    </div>
  )
}