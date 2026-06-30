export type DatasetStatus =
  | 'uploaded'
  | 'profiling'
  | 'profiled'
  | 'cleaning'
  | 'ready'
  | 'failed'

export type SemanticType =
  | 'identifier'
  | 'currency'
  | 'percentage'
  | 'date'
  | 'datetime'
  | 'categorical'
  | 'free_text'
  | 'email'
  | 'numeric_measure'
  | 'numeric_count'
  | 'boolean'
  | 'unknown'

export interface ColumnSchema {
  name: string
  dataType: string
  semanticType: SemanticType
  nullable: boolean
  uniqueCount: number
  missingCount: number
  missingRate: number
  sampleValues: string[]
}

export interface Dataset {
  id: string
  originalName: string
  status: DatasetStatus
  sizeBytes: number
  mimeType: string
  rowCount: number | null
  columnCount: number | null
  schema: ColumnSchema[] | null
  createdAt: string
  updatedAt: string
}

export interface UploadResponse {
  datasetId: string
  jobId: string
  estimatedDurationSeconds: number
  message: string
}