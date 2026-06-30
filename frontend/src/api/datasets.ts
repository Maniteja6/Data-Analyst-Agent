import { apiClient } from './client'
import type { Dataset, UploadResponse } from '@/types/dataset'

export const datasetsApi = {
  upload: async (file: File, projectId?: string): Promise<UploadResponse> => {
    const form = new FormData()
    form.append('file', file)
    if (projectId) form.append('project_id', projectId)
    const { data } = await apiClient.post<UploadResponse>('/datasets/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  get: async (datasetId: string): Promise<Dataset> => {
    const { data } = await apiClient.get<Dataset>(`/datasets/${datasetId}`)
    return data
  },

  list: async (): Promise<Dataset[]> => {
    const { data } = await apiClient.get<Dataset[]>('/datasets')
    return data
  },
}