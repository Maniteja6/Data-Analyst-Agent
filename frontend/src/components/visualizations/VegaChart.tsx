import { useEffect, useRef } from 'react'
import embed, { type EmbedOptions } from 'vega-embed'
import type { VegaLiteSpec } from '@/types/conversation'

interface VegaChartProps {
  spec: VegaLiteSpec
  height?: number
}

const VEGA_OPTIONS: EmbedOptions = {
  actions: false,
  theme: 'latimes',
  config: {
    background: 'transparent',
    font: 'Inter, system-ui, sans-serif',
    axis: { labelFont: 'Inter', titleFont: 'Inter', labelColor: '#888780', gridColor: '#E2E0D8' },
    legend: { labelFont: 'Inter', titleFont: 'Inter' },
    title: { font: 'Inter', color: '#1E1E1C' },
  },
}

export function VegaChart({ spec }: VegaChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    let cancelled = false
    embed(containerRef.current, spec as object, VEGA_OPTIONS).catch(() => {
      if (!cancelled) { /* silently ignore render errors */ }
    })
    return () => { cancelled = true }
  }, [spec])

  return <div ref={containerRef} className="w-full overflow-hidden" />
}