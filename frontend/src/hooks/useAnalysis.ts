import { useQuery } from '@tanstack/react-query'
import { insightsApi } from '@/api/insights'

export function useAnalysis(datasetId: string | null) {
  const profileQuery = useQuery({
    queryKey: ['profile', datasetId],
    queryFn: () => insightsApi.getProfile(datasetId!),
    enabled: !!datasetId,
  })

  const anomaliesQuery = useQuery({
    queryKey: ['anomalies', datasetId],
    queryFn: () => insightsApi.getAnomalies(datasetId!),
    enabled: !!datasetId,
  })

  return { profileQuery, anomaliesQuery }
}