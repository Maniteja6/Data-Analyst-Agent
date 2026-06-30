import { clsx } from 'clsx'
import { Badge } from '@/components/shared/Badge'
import { Skeleton } from '@/components/shared/Skeleton'
import type { ColumnSchema, SemanticType } from '@/types/dataset'

const semanticVariant: Record<SemanticType, 'violet' | 'teal' | 'amber' | 'emerald' | 'neutral'> = {
  currency:        'emerald',
  percentage:      'teal',
  date:            'violet',
  datetime:        'violet',
  categorical:     'amber',
  identifier:      'neutral',
  numeric_measure: 'teal',
  numeric_count:   'teal',
  boolean:         'amber',
  free_text:       'neutral',
  email:           'amber',
  unknown:         'neutral',
}

interface SchemaTableProps {
  columns: ColumnSchema[]
  loading?: boolean
}

export function SchemaTable({ columns, loading }: SchemaTableProps) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-dp-border">
            <th className="text-left py-2 pr-4 text-2xs font-semibold uppercase tracking-widest text-dp-muted">Column</th>
            <th className="text-left py-2 pr-4 text-2xs font-semibold uppercase tracking-widest text-dp-muted">Type</th>
            <th className="text-left py-2 pr-4 text-2xs font-semibold uppercase tracking-widest text-dp-muted">Semantic</th>
            <th className="text-right py-2 text-2xs font-semibold uppercase tracking-widest text-dp-muted">Missing</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-dp-border">
          {columns.map((col) => (
            <tr key={col.name} className="hover:bg-dp-canvas transition-colors">
              <td className="py-2 pr-4">
                <span className="font-mono text-xs text-dp-text font-medium">{col.name}</span>
              </td>
              <td className="py-2 pr-4">
                <span className="font-mono text-xs text-dp-muted">{col.dataType}</span>
              </td>
              <td className="py-2 pr-4">
                <Badge variant={semanticVariant[col.semanticType]}>
                  {col.semanticType.replace('_', ' ')}
                </Badge>
              </td>
              <td className="py-2 text-right">
                <span className={clsx(
                  'text-xs font-medium',
                  col.missingRate > 0.2 ? 'text-dp-rose' :
                  col.missingRate > 0.05 ? 'text-dp-amber' : 'text-dp-muted',
                )}>
                  {(col.missingRate * 100).toFixed(1)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}