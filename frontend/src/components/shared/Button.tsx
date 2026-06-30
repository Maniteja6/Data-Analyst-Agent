import { clsx } from 'clsx'

type Variant = 'primary' | 'ghost' | 'outline'

const variantMap: Record<Variant, string> = {
  primary: 'dp-btn-primary',
  ghost:   'dp-btn-ghost',
  outline: 'dp-btn border border-dp-border text-dp-text-secondary hover:bg-dp-canvas',
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md'
  loading?: boolean
}

export function Button({
  children, variant = 'primary', size = 'md', loading, className, disabled, ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        variantMap[variant],
        size === 'sm' && 'px-2 py-1 text-xs',
        (disabled || loading) && 'opacity-50 cursor-not-allowed',
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="32" strokeLinecap="round"/>
        </svg>
      )}
      {children}
    </button>
  )
}