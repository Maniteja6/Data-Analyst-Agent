import { create } from 'zustand'
import type { InsightReport } from '@/types/insights'

interface InsightState {
  report: InsightReport | null
  isLoading: boolean
  error: string | null
  setReport: (report: InsightReport | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  reset: () => void
}

export const useInsightStore = create<InsightState>((set) => ({
  report: null,
  isLoading: false,
  error: null,
  setReport: (report) => set({ report }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  reset: () => set({ report: null, isLoading: false, error: null }),
}))