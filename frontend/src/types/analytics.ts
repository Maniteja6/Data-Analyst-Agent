export interface ColumnProfile {
  name: string
  dataType: string
  totalRows: number
  nullCount: number
  uniqueCount: number
  mean: number | null
  stddev: number | null
  min: number | null
  max: number | null
  p25: number | null
  p50: number | null
  p75: number | null
  skewness: number | null
  topValues: Array<{ value: string; count: number; pct: number }>
  histogram: Array<{ bin: string; count: number }>
}

export interface DataProfile {
  sessionId: string
  rowCount: number
  columnCount: number
  duplicateCount: number
  completenessScore: number
  consistencyScore: number
  columnProfiles: ColumnProfile[]
}

export interface AnomalyAlert {
  id: string
  columnName: string
  anomalyType: 'outlier' | 'missing_pattern' | 'duplicate' | 'type_mismatch' | 'rule_violation'
  severity: 'critical' | 'high' | 'medium' | 'low'
  description: string
  affectedRows: number
  detectionMethod: string
  confidence: number
}

export interface CleaningAction {
  action: string
  column: string
  rowsAffected: number
  description: string
}

export interface CleaningReport {
  actionsApplied: CleaningAction[]
  rowsBefore: number
  rowsAfter: number
  columnsBefore: number
  columnsAfter: number
}