export type KPITrend = 'up' | 'down' | 'stable' | 'unknown'

export interface KPI {
  id: string
  name: string
  value: number
  unit: string
  trend: KPITrend
  trendPct: number | null
  significance: 'high' | 'medium' | 'low'
  description: string
}

export interface Recommendation {
  id: string
  title: string
  situation: string
  action: string
  estimatedImpact: string
  priority: 'high' | 'medium' | 'low'
}

export interface ForecastDataPoint {
  timestamp: string
  value: number
  lowerBound: number
  upperBound: number
}

export interface ForecastResult {
  id: string
  targetColumn: string
  modelName: string
  horizonLabel: string
  frequency: string
  predictions: ForecastDataPoint[]
  mape: number | null
  rmse: number | null
  narration: string
  trendDirection: 'up' | 'down' | 'flat' | 'unknown'
}

export interface Insight {
  id: string
  headline: string
  explanation: string
  businessImpact: 'high' | 'medium' | 'low'
  confidence: number
  hasAnomalyReference: boolean
  sourceColumns: string[]
}

export interface InsightReport {
  reportId: string
  sessionId: string
  executiveSummary: string
  kpis: KPI[]
  insights: Insight[]
  recommendations: Recommendation[]
  forecasts: ForecastResult[]
  createdAt: string
}