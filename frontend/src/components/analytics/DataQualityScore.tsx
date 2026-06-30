import { clsx } from 'clsx'

interface DataQualityScoreProps {
  completenessScore: number   // 0-1
  consistencyScore: number    // 0-1
  rowCount: number
  columnCount: number
  duplicateCount: number
}

function ScoreArc({ value, color, label }: { value: number; color: string; label: string }) {
  const pct = Math.round(value * 100)
  const r = 28
  const circumference = 2 * Math.PI * r
  const offset = circumference - (pct / 100) * circumference

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-16 h-16">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r={r} fill="none" stroke="#E2E0D8" strokeWidth="5" />
          <circle
            cx="32" cy="32" r={r} fill="none"
            stroke={color} strokeWidth="5"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs font-bold text-dp-text">{pct}%</span>
        </div>
      </div>
      <span className="text-2xs text-dp-muted">{label}</span>
    </div>
  )
}

export function DataQualityScore({
  completenessScore, consistencyScore, rowCount, columnCount, duplicateCount,
}: DataQualityScoreProps) {
  const overall = (completenessScore + consistencyScore) / 2
  const grade =
    overall >= 0.9 ? 'A' : overall >= 0.75 ? 'B' : overall >= 0.6 ? 'C' : 'D'
  const gradeColor =
    overall >= 0.9 ? 'text-dp-emerald' : overall >= 0.75 ? 'text-dp-teal' :
    overall >= 0.6 ? 'text-dp-amber'   : 'text-dp-rose'

  return (
    <div>
      <div className="flex items-center gap-6 mb-4">
        <div className="text-center">
          <span className={clsx('text-4xl font-bold', gradeColor)}>{grade}</span>
          <p className="text-2xs text-dp-muted mt-0.5">Overall grade</p>
        </div>
        <div className="flex gap-4">
          <ScoreArc value={completenessScore} color="#5B4FE8" label="Completeness" />
          <ScoreArc value={consistencyScore}  color="#0F9B8E" label="Consistency"  />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Rows',        value: rowCount.toLocaleString() },
          { label: 'Columns',     value: columnCount.toString() },
          { label: 'Duplicates',  value: duplicateCount.toLocaleString() },
        ].map(({ label, value }) => (
          <div key={label} className="bg-dp-canvas rounded-md p-2.5 text-center">
            <div className="text-base font-bold text-dp-text">{value}</div>
            <div className="text-2xs text-dp-muted">{label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}