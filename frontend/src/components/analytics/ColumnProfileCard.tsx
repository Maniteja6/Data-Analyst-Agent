import { Card } from '@/components/shared/Card'
import { formatNumber } from '@/utils/formatters'
import type { ColumnProfile } from '@/types/analytics'

interface ColumnProfileCardProps {
  profile: ColumnProfile
}

function StatRow({ label, value }: { label: string; value: string | number | null }) {
  if (value == null) return null
  return (
    <div className="flex justify-between py-1 border-b border-dp-border last:border-0">
      <span className="text-xs text-dp-muted">{label}</span>
      <span className="text-xs font-medium text-dp-text font-mono">
        {typeof value === 'number' ? formatNumber(value, 2) : value}
      </span>
    </div>
  )
}

export function ColumnProfileCard({ profile }: ColumnProfileCardProps) {
  const completeness = ((profile.totalRows - profile.nullCount) / profile.totalRows) * 100

  return (
    <Card padding="sm">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-xs font-semibold text-dp-text truncate">{profile.name}</span>
        <span className="text-2xs text-dp-muted font-mono ml-2 flex-shrink-0">{profile.dataType}</span>
      </div>

      {/* Completeness bar */}
      <div className="mb-3">
        <div className="h-1 w-full bg-dp-border rounded-full overflow-hidden">
          <div
            className="h-full bg-dp-emerald rounded-full"
            style={{ width: `${completeness}%` }}
          />
        </div>
        <div className="flex justify-between mt-0.5">
          <span className="text-2xs text-dp-muted">Completeness</span>
          <span className="text-2xs text-dp-text font-medium">{completeness.toFixed(1)}%</span>
        </div>
      </div>

      {/* Stats */}
      <div>
        <StatRow label="Unique values" value={profile.uniqueCount} />
        <StatRow label="Null count"    value={profile.nullCount} />
        {profile.mean    != null && <StatRow label="Mean"   value={profile.mean} />}
        {profile.stddev  != null && <StatRow label="Std dev" value={profile.stddev} />}
        {profile.min     != null && <StatRow label="Min"    value={profile.min} />}
        {profile.max     != null && <StatRow label="Max"    value={profile.max} />}
        {profile.p50     != null && <StatRow label="Median" value={profile.p50} />}
      </div>

      {/* Top values */}
      {profile.topValues.length > 0 && (
        <div className="mt-3">
          <p className="text-2xs text-dp-muted mb-1 font-semibold uppercase tracking-widest">
            Top values
          </p>
          {profile.topValues.slice(0, 4).map(({ value, pct }) => (
            <div key={value} className="flex items-center gap-2 mb-1">
              <div className="h-1 flex-1 bg-dp-border rounded-full overflow-hidden">
                <div className="h-full bg-dp-violet rounded-full" style={{ width: `${pct * 100}%` }} />
              </div>
              <span className="text-2xs text-dp-muted font-mono w-20 truncate text-right">{value}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}