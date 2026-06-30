import { Skeleton } from '@/components/shared/Skeleton'
import { clsx } from 'clsx'

interface CorrelationMatrixProps {
  columns: string[]
  matrix: number[][]  // n×n correlation coefficients
  loading?: boolean
}

function correlationColor(v: number): string {
  if (v >= 0.8)  return 'bg-dp-violet text-white'
  if (v >= 0.5)  return 'bg-dp-violet-dim text-dp-violet'
  if (v >= 0.2)  return 'bg-blue-50 text-blue-600'
  if (v <= -0.5) return 'bg-rose-100 text-dp-rose'
  if (v <= -0.2) return 'bg-rose-50 text-rose-400'
  return 'bg-dp-canvas text-dp-muted'
}

export function CorrelationMatrix({ columns, matrix, loading }: CorrelationMatrixProps) {
  if (loading) return <Skeleton className="h-48 w-full" />

  const display = columns.slice(0, 8)

  return (
    <div className="overflow-auto">
      <table className="text-center text-xs border-collapse">
        <thead>
          <tr>
            <th className="w-20" />
            {display.map((col) => (
              <th key={col} className="px-1 py-1 font-mono text-2xs text-dp-muted max-w-[60px]">
                <span className="block truncate" title={col}>{col}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {display.map((row, i) => (
            <tr key={row}>
              <td className="pr-2 text-right font-mono text-2xs text-dp-muted max-w-[80px]">
                <span className="block truncate" title={row}>{row}</span>
              </td>
              {display.map((_, j) => {
                const v = matrix[i]?.[j] ?? 0
                return (
                  <td key={j} className="p-0.5">
                    <div className={clsx(
                      'w-10 h-8 rounded flex items-center justify-center text-2xs font-semibold',
                      correlationColor(v),
                    )}>
                      {v.toFixed(1)}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}