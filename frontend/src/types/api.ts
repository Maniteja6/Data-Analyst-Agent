export interface ApiError {
  error: string
  code: string
  field?: string
}

export interface JobStatus {
  jobId: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  step: string
  progress: number
  eta: number | null
  error?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}