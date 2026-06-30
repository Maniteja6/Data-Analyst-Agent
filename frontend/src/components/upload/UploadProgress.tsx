import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { ProgressBar } from '@/components/shared/ProgressBar'

const STEPS = ['Uploading', 'Schema inference', 'Profiling', 'Cleaning', 'AI analysis', 'Ready']

interface UploadProgressProps {
  progress: number   // 0-100
  step: string
  status: 'running' | 'complete' | 'failed'
  filename?: string
}

export function UploadProgress({ progress, step, status, filename }: UploadProgressProps) {
  const stepIndex = STEPS.findIndex((s) => step.toLowerCase().includes(s.toLowerCase()))
  const activeStep = stepIndex >= 0 ? stepIndex : 0

  return (
    <div className="dp-card p-4 animate-slide-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        {status === 'running' && <Loader2 size={16} className="text-dp-violet animate-spin" />}
        {status === 'complete' && <CheckCircle2 size={16} className="text-dp-emerald" />}
        {status === 'failed'   && <XCircle size={16} className="text-dp-rose" />}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-dp-text truncate">
            {filename ?? 'Processing dataset…'}
          </p>
          <p className="text-xs text-dp-muted">{step}</p>
        </div>
        <span className="text-sm font-semibold text-dp-violet">{progress}%</span>
      </div>

      <ProgressBar
        value={progress}
        color={status === 'failed' ? 'amber' : status === 'complete' ? 'emerald' : 'violet'}
      />

      {/* Step indicators */}
      <div className="flex items-center justify-between mt-4">
        {STEPS.map((s, i) => (
          <div key={s} className="flex flex-col items-center gap-1">
            <div className={clsx(
              'w-2 h-2 rounded-full transition-colors duration-300',
              i < activeStep  && 'bg-dp-emerald',
              i === activeStep && status !== 'failed' && 'bg-dp-violet animate-pulse',
              i === activeStep && status === 'failed'  && 'bg-dp-rose',
              i > activeStep  && 'bg-dp-border',
            )} />
            <span className="text-2xs text-dp-muted hidden sm:block">{s}</span>
          </div>
        ))}
      </div>
    </div>
  )
}