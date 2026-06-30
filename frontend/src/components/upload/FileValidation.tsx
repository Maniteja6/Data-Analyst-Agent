import { AlertCircle, CheckCircle2 } from 'lucide-react'

interface FileValidationProps {
  error: string | null
  success?: string | null
}

export function FileValidation({ error, success }: FileValidationProps) {
  if (!error && !success) return null

  if (error) {
    return (
      <div className="flex items-start gap-2 px-3 py-2.5 rounded-md bg-rose-50
        border border-rose-100 animate-fade-in">
        <AlertCircle size={14} className="text-dp-rose mt-0.5 flex-shrink-0" />
        <p className="text-xs text-dp-rose">{error}</p>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2.5 rounded-md bg-emerald-50
      border border-emerald-100 animate-fade-in">
      <CheckCircle2 size={14} className="text-dp-emerald flex-shrink-0" />
      <p className="text-xs text-dp-emerald">{success}</p>
    </div>
  )
}