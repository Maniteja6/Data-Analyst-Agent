import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import type { JobStatus } from '@/types/api'

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: async () => {
      const { data } = await apiClient.get<JobStatus>(`/jobs/${jobId}/status`)
      return data
    },
    enabled: !!jobId,
    refetchInterval: (data) => {
      const status = data?.state?.data?.status
      return status === 'complete' || status === 'failed' ? false : 2000
    },
  })
}