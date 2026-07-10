interface ChartSkeletonProps { height?: number }

export function ChartSkeleton({ height = 180 }: ChartSkeletonProps) {
  return (
    <div className="w-full animate-pulse" style={{ height }}>
      <div className="flex items-end gap-1 h-full px-2 pb-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="flex-1 bg-dp-border rounded-sm"
            style={{ height: `${30 + Math.random() * 60}%` }}
          />
        ))}
      </div>
    </div>
  )
}