import { clsx } from 'clsx'

interface CardProps {
  children: React.ReactNode
  className?: string
  padding?: 'sm' | 'md' | 'lg' | 'none'
}

const paddingMap = { none: '', sm: 'p-3', md: 'p-4', lg: 'p-5' }

export function Card({ children, className, padding = 'md' }: CardProps) {
  return (
    <div className={clsx('dp-card', paddingMap[padding], className)}>
      {children}
    </div>
  )
}