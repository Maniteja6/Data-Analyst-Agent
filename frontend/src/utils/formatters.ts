export function formatNumber(value: number, decimals = 1): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000)     return `${(value / 1_000).toFixed(1)}K`
  return value % 1 === 0 ? value.toLocaleString() : value.toFixed(decimals)
}

export function formatCurrency(value: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`
  if (bytes >= 1_048_576)     return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1_024)         return `${(bytes / 1_024).toFixed(0)} KB`
  return `${bytes} B`
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  }).format(new Date(iso))
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1)   return 'just now'
  if (mins < 60)  return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)   return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function formatKPIValue(value: number, unit: string): string {
  if (unit === 'USD')  return formatCurrency(value)
  if (unit === '%')    return formatPercent(value)
  return formatNumber(value)
}