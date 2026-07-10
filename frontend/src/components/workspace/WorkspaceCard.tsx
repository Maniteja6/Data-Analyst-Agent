import { Database } from 'lucide-react'
import { StatusDot } from '@/components/shared/StatusDot'
import type { DatasetStatus } from '@/types/dataset'

interface WorkspaceCardProps {
  datasetsProcessed: number
  filename?: string
  status?: DatasetStatus
}

export function WorkspaceCard({ datasetsProcessed, filename, status = 'uploaded' }: WorkspaceCardProps) {
  return (
    <div className="relative overflow-hidden rounded-dp p-5 bg-gradient-to-br
      from-dp-violet to-[#3A2FC0] text-white min-h-[140px]">
      {/* Background decoration */}
      <div className="absolute right-4 bottom-4 opacity-10">
        <Database size={80} />
      </div>

      {/* Status pill */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-semibold uppercase tracking-widest text-white/60 px-2 py-0.5
          bg-white/10 rounded-md">
          WORKSPACE
        </span>
        {status && (
          <span className="flex items-center gap-1.5 text-white/70 text-xs">
            <StatusDot status={status} />
            {filename ? filename : 'Waiting for upload'}
          </span>
        )}
      </div>

      {/* Main stat */}
      <div className="text-5xl font-bold leading-none mb-2">{datasetsProcessed}</div>
      <p className="text-white/60 text-sm">
        Datasets processed — your files in this session
      </p>
    </div>
  )
}