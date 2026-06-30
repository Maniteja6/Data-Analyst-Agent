import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { datasetsApi } from '@/api/datasets'
import { useDatasetStore } from '@/store/datasetStore'

export function useDataset(datasetId: string | null) {
  const { setCurrentDataset } = useDatasetStore()

  const query = useQuery({
    queryKey: ['dataset', datasetId],
    queryFn: () => datasetsApi.get(datasetId!),
    enabled: !!datasetId,
    refetchInterval: (data) => {
      const status = data?.state?.data?.status
      return status === 'ready' || status === 'failed' ? false : 3000
    },
  })

  useEffect(() => {
    if (query.data) setCurrentDataset(query.data)
  }, [query.data, setCurrentDataset])

  return query
}