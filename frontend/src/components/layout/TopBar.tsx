import { MessageSquare } from 'lucide-react'
import { useUIStore } from '@/store/UiStore'
import { useDatasetStore } from '@/store/datasetStore'
import { StatusDot } from '@/components/shared/StatusDot'

export function TopBar() {
  const { toggleChat } = useUIStore()
  const { currentDataset } = useDatasetStore()

  return (
    <div className="h-12 border-b border-dp-border bg-dp-surface flex items-center
      justify-between px-5 flex-shrink-0">
      <div className="flex items-center gap-3">
        {currentDataset && (
          <>
            <span className="text-sm font-medium text-dp-text truncate max-w-xs">
              {currentDataset.originalName}
            </span>
            <StatusDot status={currentDataset.status} showLabel />
          </>
        )}
      </div>
      <button
        onClick={toggleChat}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm
          text-dp-text-secondary hover:text-dp-text hover:bg-dp-canvas transition-colors"
      >
        <MessageSquare size={15} />
        <span>Chat with data</span>
      </button>
    </div>
  )
}