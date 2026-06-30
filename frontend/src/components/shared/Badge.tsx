import { clsx } from 'clsx'

type Variant = 'violet' | 'teal' | 'amber' | 'rose' | 'emerald' | 'neutral'

const variantMap: Record<Variant, string> = {
  violet:  'bg-dp-violet-dim text-dp-violet',
  teal:    'bg-teal-50 text-dp-teal',
  amber:   'bg-amber-50 text-amber-700',
  rose:    'bg-rose-50 text-dp-rose',
  emerald: 'bg-emerald-50 text-dp-emerald',
  neutral: 'bg-dp-canvas text-dp-muted',
}

interface BadgeProps {
  children: React.ReactNode
  variant?: Variant
  className?: string
}

export function Badge({ children, variant = 'neutral', className }: BadgeProps) {
  return (
    <span className={clsx('dp-badge', variantMap[variant], className)}>
      {children}
    </span>
  )
}