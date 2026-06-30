import { useQuery } from '@tanstack/react-query'
import { insightsApi } from '@/api/insights'

export function useInsights(datasetId: string | null) {
  return useQuery({
    queryKey: ['insights', datasetId],
    queryFn: () => insightsApi.getReport(datasetId!),
    enabled: !!datasetId,
  })
}