import { apiClient } from './client'

export type ExportFormat = 'pdf' | 'xlsx' | 'pptx' | 'json'

export const exportsApi = {
  requestExport: async (
    datasetId: string,
    format: ExportFormat,
  ): Promise<{ downloadUrl: string; expiresAt: string }> => {
    const { data } = await apiClient.get(`/datasets/${datasetId}/export`, {
      params: { format },
    })
    return data
  },
}