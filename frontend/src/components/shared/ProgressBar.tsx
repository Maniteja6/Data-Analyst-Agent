import { clsx } from 'clsx'

interface ProgressBarProps {
  value: number      // 0-100
  label?: string
  className?: string
  color?: 'violet' | 'teal' | 'emerald' | 'amber'
}

const colorMap = {
  violet:  'bg-dp-violet',
  teal:    'bg-dp-teal',
  emerald: 'bg-dp-emerald',
  amber:   'bg-dp-amber',
}

export function ProgressBar({ value, label, className, color = 'violet' }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <div className={clsx('w-full', className)}>
      {label && (
        <div className="flex justify-between mb-1">
          <span className="text-xs text-dp-text-secondary">{label}</span>
          <span className="text-xs font-medium text-dp-text">{clamped}%</span>
        </div>
      )}
      <div className="h-1.5 w-full bg-dp-border rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full transition-all duration-500', colorMap[color])}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}