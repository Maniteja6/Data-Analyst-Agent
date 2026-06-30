import { VegaChart } from '@/components/visualizations/VegaChart'
import type { ChatVisualizationPayload } from '@/types/conversation'

interface ChatVisualizationProps {
  viz: ChatVisualizationPayload
}

export function ChatVisualization({ viz }: ChatVisualizationProps) {
  if (viz.type !== 'vega') return null

  return (
    <div className="mt-2 rounded-dp border border-dp-border bg-dp-surface p-3">
      <VegaChart spec={viz.spec} />
      {viz.caption && (
        <p className="text-2xs text-dp-muted mt-2 text-center">{viz.caption}</p>
      )}
    </div>
  )
}