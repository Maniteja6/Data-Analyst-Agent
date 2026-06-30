import { clsx } from 'clsx'
import { CitationTooltip } from './CitationTooltip'
import { ChatVisualization } from './ChatVisualization'
import type { Message } from '@/types/conversation'

interface ChatMessageProps {
  message: Message
  streamingContent?: string
}

export function ChatMessage({ message, streamingContent }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const content = message.isStreaming ? streamingContent ?? '' : message.content

  return (
    <div className={clsx('flex gap-2 animate-slide-up', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div className={clsx(
        'w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center text-2xs font-bold mt-0.5',
        isUser ? 'bg-dp-violet text-white' : 'bg-dp-canvas border border-dp-border text-dp-muted',
      )}>
        {isUser ? 'U' : 'AI'}
      </div>

      <div className={clsx('flex-1 max-w-[85%]', isUser && 'flex flex-col items-end')}>
        <div className={clsx(
          'rounded-xl px-3 py-2.5 text-xs leading-relaxed',
          isUser
            ? 'bg-dp-violet text-white rounded-tr-sm'
            : 'bg-dp-canvas border border-dp-border text-dp-text rounded-tl-sm',
          message.isStreaming && 'after:content-["▋"] after:animate-pulse after:ml-0.5',
        )}>
          {content}
          {/* Citations inline */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <span className="ml-1">
              {message.citations.map((c, i) => (
                <CitationTooltip key={i} citation={c} index={i + 1} />
              ))}
            </span>
          )}
        </div>

        {/* Visualizations */}
        {!isUser && message.visualizations && message.visualizations.map((v, i) => (
          <div key={i} className="w-full">
            <ChatVisualization viz={v} />
          </div>
        ))}
      </div>
    </div>
  )
}