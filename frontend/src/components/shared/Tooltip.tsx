'use client'
import { useState } from 'react'
import { clsx } from 'clsx'

interface TooltipProps {
  content: string
  children: React.ReactNode
  className?: string
}

export function Tooltip({ content, children, className }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  return (
    <span
      className={clsx('relative inline-flex', className)}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5
            bg-dp-navy text-white text-xs rounded px-2 py-1 whitespace-nowrap z-50
            pointer-events-none animate-fade-in"
        >
          {content}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4
            border-transparent border-t-dp-navy" />
        </span>
      )}
    </span>
  )
}