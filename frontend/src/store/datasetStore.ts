import { create } from 'zustand'
import type { Dataset } from '@/types/dataset'

interface DatasetState {
  currentDataset: Dataset | null
  uploadProgress: number
  uploadStep: string
  jobId: string | null
  setCurrentDataset: (dataset: Dataset | null) => void
  setUploadProgress: (progress: number, step: string) => void
  setJobId: (jobId: string | null) => void
  reset: () => void
}

export const useDatasetStore = create<DatasetState>((set) => ({
  currentDataset: null,
  uploadProgress: 0,
  uploadStep: '',
  jobId: null,
  setCurrentDataset: (dataset) => set({ currentDataset: dataset }),
  setUploadProgress: (uploadProgress, uploadStep) => set({ uploadProgress, uploadStep }),
  setJobId: (jobId) => set({ jobId }),
  reset: () => set({ currentDataset: null, uploadProgress: 0, uploadStep: '', jobId: null }),
}))