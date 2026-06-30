import { Upload } from 'lucide-react'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'

interface UploadButtonProps {
  loading?: boolean
  onClick?: () => void
}

export function UploadButton({ loading, onClick }: UploadButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 px-4 py-2 bg-dp-surface border border-dp-border
        rounded-md text-sm font-medium text-dp-text-secondary hover:text-dp-text
        hover:border-dp-violet transition-colors flex-shrink-0"
    >
      {loading ? <LoadingSpinner className="w-4 h-4" /> : <Upload size={14} />}
      <span>{loading ? 'Uploading…' : 'Upload'}</span>
    </button>
  )
}