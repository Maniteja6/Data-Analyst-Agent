import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { DataInsightsPage } from '@/pages/DataInsightsPage'
import { PredictiveAnalysisPage } from '@/pages/PredictiveAnalysisPage'
import { DataQualityPage } from '@/pages/DataQualityPage'
import { AIInsightsPage } from '@/pages/AIInsightsPage'
import { ExportResultsPage } from '@/pages/ExportResultsPage'
import { useUIStore } from '@/store/UiStore'
import { useDatasetStore } from '@/store/datasetStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAnalysisStore } from '@/store/analysisStore'
import { useChatStore } from '@/store/chatStore'
import type { WSEvent } from '@/types/websocket'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, staleTime: 30_000 },
  },
})

function ActivePage() {
  const { activePage } = useUIStore()
  switch (activePage) {
    case 'dashboard':           return <DashboardPage />
    case 'data-insights':       return <DataInsightsPage />
    case 'predictive-analysis': return <PredictiveAnalysisPage />
    case 'data-quality':        return <DataQualityPage />
    case 'ai-insights':         return <AIInsightsPage />
    case 'export-results':      return <ExportResultsPage />
    default:                    return <DashboardPage />
  }
}

function AppInner() {
  const { setUploadProgress } = useDatasetStore()
  const { setAnomalies } = useAnalysisStore()
  const { updateStreamingContent, finaliseStreamingMessage } = useChatStore()

  useWebSocket((event: WSEvent) => {
    switch (event.type) {
      case 'job.progress':
        setUploadProgress(Math.round(event.progress * 100), event.message)
        break
      case 'anomaly.detected':
        // append to anomaly list — full list re-fetched via React Query
        break
      case 'chat.token':
        updateStreamingContent(event.token)
        break
      case 'chat.complete':
        finaliseStreamingMessage(event.messageId, '')
        queryClient.invalidateQueries({ queryKey: ['conversation'] })
        break
      case 'analysis.complete':
        queryClient.invalidateQueries({ queryKey: ['insights'] })
        queryClient.invalidateQueries({ queryKey: ['dataset'] })
        queryClient.invalidateQueries({ queryKey: ['profile'] })
        queryClient.invalidateQueries({ queryKey: ['anomalies'] })
        break
    }
  })

  return (
    <AppShell>
      <ActivePage />
    </AppShell>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  )
}