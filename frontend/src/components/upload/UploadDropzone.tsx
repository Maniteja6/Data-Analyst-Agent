import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { FileText } from 'lucide-react'
import { clsx } from 'clsx'
import { ACCEPTED_TYPES, MAX_FILE_SIZE_BYTES } from '@/utils/fileHelpers'
import { UploadButton } from './UploadButton'

interface UploadDropzoneProps {
  onFile: (file: File) => void
  isUploading?: boolean
  disabled?: boolean
}

export function UploadDropzone({ onFile, isUploading, disabled }: UploadDropzoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => { if (accepted[0]) onFile(accepted[0]) },
    [onFile],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_FILE_SIZE_BYTES,
    multiple: false,
    disabled: disabled || isUploading,
  })

  return (
    <div
      {...getRootProps()}
      className={clsx(
        'relative rounded-dp border-2 border-dashed transition-all duration-200 cursor-pointer',
        'flex items-center gap-4 px-5 py-4',
        isDragActive
          ? 'border-dp-violet bg-dp-violet-dim scale-[1.01]'
          : 'border-dp-border bg-dp-surface hover:border-dp-violet hover:bg-dp-violet-dim/40',
        (disabled || isUploading) && 'opacity-50 cursor-not-allowed',
      )}
    >
      <input {...getInputProps()} />

      <UploadButton loading={isUploading} />

      <div className="min-w-0">
        <p className="text-sm text-dp-text-secondary">
          {isDragActive
            ? 'Drop your file here…'
            : '200MB per file • CSV, XLSX, Parquet, JSON'}
        </p>
      </div>

      {isDragActive && (
        <div className="absolute inset-0 flex flex-col items-center justify-center
          rounded-dp bg-dp-violet-dim/80 pointer-events-none animate-fade-in">
          <FileText size={32} className="text-dp-violet mb-2" />
          <span className="text-dp-violet font-medium text-sm">Drop to upload</span>
        </div>
      )}
    </div>
  )
}