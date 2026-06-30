import { clsx } from 'clsx'

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <svg
      className={clsx('animate-spin text-dp-violet', className ?? 'w-5 h-5')}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"
        strokeDasharray="32" strokeLinecap="round" opacity="0.25" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3"
        strokeLinecap="round" />
    </svg>
  )
}