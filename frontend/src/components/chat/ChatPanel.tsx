import { useEffect } from 'react'
import { X } from 'lucide-react'
import { ChatMessageList } from './ChatMessageList'
import { ChatInput } from './ChatInput'
import { useConversation } from '@/hooks/useConversation'
import { useChatStore } from '@/store/chatStore'
import { useDatasetStore } from '@/store/datasetStore'
import { useUIStore } from '@/store/UiStore'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'

export function ChatPanel() {
  const { currentDataset } = useDatasetStore()
  const { setChatOpen } = useUIStore()
  const { messages, streamingContent, isStreaming, isLoading } = useChatStore()
  const { conversation, startConversation, sendMessage } = useConversation()

  // Auto-start conversation when dataset is ready
  useEffect(() => {
    if (currentDataset?.status === 'ready' && !conversation) {
      startConversation(currentDataset.id)
    }
  }, [currentDataset, conversation, startConversation])

  const datasetReady = currentDataset?.status === 'ready'

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dp-border flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-dp-text">Chat with data</h2>
          <p className="text-2xs text-dp-muted">
            {currentDataset?.originalName ?? 'No dataset loaded'}
          </p>
        </div>
        <button
          onClick={() => setChatOpen(false)}
          className="w-7 h-7 rounded-md flex items-center justify-center
            text-dp-muted hover:text-dp-text hover:bg-dp-canvas transition-colors"
          aria-label="Close chat"
        >
          <X size={14} />
        </button>
      </div>

      {/* Not ready state */}
      {!datasetReady && (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-6">
          {currentDataset ? (
            <>
              <LoadingSpinner className="w-6 h-6 mb-3" />
              <p className="text-sm text-dp-text-secondary">Analysing dataset…</p>
              <p className="text-xs text-dp-muted mt-1">Chat will be available when ready.</p>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-dp-text mb-1">No dataset loaded</p>
              <p className="text-xs text-dp-muted">Upload a dataset to start chatting.</p>
            </>
          )}
        </div>
      )}

      {/* Messages */}
      {datasetReady && (
        <>
          <ChatMessageList
            messages={messages}
            streamingContent={streamingContent}
            isStreaming={isStreaming}
            isLoading={isLoading}
          />
          <ChatInput
            onSend={sendMessage}
            disabled={isLoading || isStreaming}
          />
        </>
      )}
    </div>
  )
}