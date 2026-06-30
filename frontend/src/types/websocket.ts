export type WSEventType =
  | 'job.progress'
  | 'kpi.ready'
  | 'anomaly.detected'
  | 'analysis.complete'
  | 'chat.token'
  | 'chat.complete'
  | 'error'

export interface JobProgressEvent {
  type: 'job.progress'
  jobId: string
  step: string
  progress: number
  message: string
}

export interface KPIReadyEvent {
  type: 'kpi.ready'
  datasetId: string
  kpis: unknown[]
}

export interface AnomalyDetectedEvent {
  type: 'anomaly.detected'
  datasetId: string
  anomaly: { column: string; severity: string; description: string }
}

export interface AnalysisCompleteEvent {
  type: 'analysis.complete'
  datasetId: string
  reportUrl: string
}

export interface ChatTokenEvent {
  type: 'chat.token'
  conversationId: string
  messageId: string
  token: string
}

export interface ChatCompleteEvent {
  type: 'chat.complete'
  conversationId: string
  messageId: string
  visualizations?: unknown[]
  citations?: unknown[]
}

export type WSEvent =
  | JobProgressEvent
  | KPIReadyEvent
  | AnomalyDetectedEvent
  | AnalysisCompleteEvent
  | ChatTokenEvent
  | ChatCompleteEvent