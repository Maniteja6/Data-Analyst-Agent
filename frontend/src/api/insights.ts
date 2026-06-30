import { apiClient } from './client'
import type { InsightReport } from '@/types/insights'
import type { DataProfile, AnomalyAlert } from '@/types/analytics'

export const insightsApi = {
  getReport: async (datasetId: string): Promise<InsightReport> => {
    const { data } = await apiClient.get<InsightReport>(`/insights/${datasetId}`)
    return data
  },

  getProfile: async (datasetId: string): Promise<DataProfile> => {
    const { data } = await apiClient.get<DataProfile>(`/datasets/${datasetId}/profile`)
    return data
  },

  getAnomalies: async (datasetId: string): Promise<AnomalyAlert[]> => {
    const { data } = await apiClient.get<AnomalyAlert[]>(`/datasets/${datasetId}/anomalies`)
    return data
  },
}