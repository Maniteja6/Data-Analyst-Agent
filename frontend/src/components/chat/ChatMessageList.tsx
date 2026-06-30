import { useEffect, useRef } from 'react'
import { ChatMessage } from './ChatMessage'
import { TypingIndicator } from './TypingIndicator'
import type { Message } from '@/types/conversation'

interface ChatMessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  isLoading: boolean
}

export function ChatMessageList({
  messages, streamingContent, isStreaming, isLoading,
}: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, streamingContent])

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-3">
      {messages.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-full text-center py-12">
          <div className="w-10 h-10 rounded-full bg-dp-violet-dim flex items-center justify-center mb-3">
            <span className="text-dp-violet font-bold text-sm">AI</span>
          </div>
          <p className="text-sm font-medium text-dp-text mb-1">Ask anything about your data</p>
          <p className="text-xs text-dp-muted max-w-[200px]">
            Try "Show top 10 rows", "What columns have the most missing values?", or "Summarise the trends."
          </p>
        </div>
      )}

      {messages.map((msg) => (
        <ChatMessage
          key={msg.id}
          message={msg}
          streamingContent={msg.isStreaming ? streamingContent : undefined}
        />
      ))}

      {(isLoading && !isStreaming) && (
        <div className="flex gap-2">
          <div className="w-6 h-6 rounded-full bg-dp-canvas border border-dp-border
            flex items-center justify-center text-2xs font-bold text-dp-muted flex-shrink-0">
            AI
          </div>
          <TypingIndicator />
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}