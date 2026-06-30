import { useState, useCallback } from 'react'
import { datasetsApi } from '@/api/datasets'
import { useDatasetStore } from '@/store/datasetStore'
import { MAX_FILE_SIZE_BYTES, isAcceptedType } from '@/utils/fileHelpers'

interface UseFileUploadReturn {
  upload: (file: File) => Promise<void>
  isUploading: boolean
  error: string | null
  clearError: () => void
}

export function useFileUpload(): UseFileUploadReturn {
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setJobId, setUploadProgress } = useDatasetStore()

  const upload = useCallback(async (file: File) => {
    setError(null)

    if (!isAcceptedType(file)) {
      setError('Unsupported file type. Upload a CSV, XLSX, Parquet, or JSON file.')
      return
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setError('File exceeds the 200 MB limit. Split it and try again.')
      return
    }

    setIsUploading(true)
    setUploadProgress(0, 'Uploading…')

    try {
      const result = await datasetsApi.upload(file)
      setJobId(result.jobId)
      setUploadProgress(10, 'Processing…')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
    }
  }, [setJobId, setUploadProgress])

  return { upload, isUploading, error, clearError: () => setError(null) }
}