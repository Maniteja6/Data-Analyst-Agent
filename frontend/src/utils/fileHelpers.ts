export const ACCEPTED_TYPES: Record<string, string[]> = {
  'text/csv':                     ['.csv'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel':     ['.xls'],
  'application/octet-stream':     ['.parquet'],
  'application/json':             ['.json'],
}

export const MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024 // 200 MB (UI limit)

export function isAcceptedType(file: File): boolean {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase()
  return Object.values(ACCEPTED_TYPES).flat().includes(ext)
}

export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toUpperCase() ?? 'FILE'
}