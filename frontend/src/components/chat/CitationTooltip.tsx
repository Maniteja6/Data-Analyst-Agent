import { useState } from 'react'
import { Info } from 'lucide-react'
import type { Citation } from '@/types/conversation'

interface CitationTooltipProps {
  citation: Citation
  index: number
}

export function CitationTooltip({ citation, index }: CitationTooltipProps) {
  const [open, setOpen] = useState(false)

  return (
    <span className="relative inline-block">
      <button
        className="inline-flex items-center text-dp-violet text-2xs font-semibold
          hover:underline ml-0.5"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
      >
        [{index}]
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-56 bg-dp-navy text-white
          text-xs rounded-lg p-3 shadow-dp-elevated z-50 animate-fade-in">
          <div className="flex items-center gap-1.5 mb-1">
            <Info size={10} />
            <span className="font-semibold">{citation.source}</span>
          </div>
          {citation.columnName && (
            <p className="text-white/60 font-mono text-2xs mb-1">{citation.columnName}</p>
          )}
          <p className="text-white/80 leading-relaxed">{citation.text}</p>
        </div>
      )}
    </span>
  )
}