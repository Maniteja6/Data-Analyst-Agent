import { create } from 'zustand'
import type { DataProfile, AnomalyAlert } from '@/types/analytics'

interface AnalysisState {
  profile: DataProfile | null
  anomalies: AnomalyAlert[]
  isLoading: boolean
  error: string | null
  setProfile: (profile: DataProfile | null) => void
  setAnomalies: (anomalies: AnomalyAlert[]) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  reset: () => void
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  profile: null,
  anomalies: [],
  isLoading: false,
  error: null,
  setProfile: (profile) => set({ profile }),
  setAnomalies: (anomalies) => set({ anomalies }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  reset: () => set({ profile: null, anomalies: [], isLoading: false, error: null }),
}))