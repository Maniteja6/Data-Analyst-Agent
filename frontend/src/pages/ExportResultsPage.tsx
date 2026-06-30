import { useState } from 'react'
import { Download, FileText, Table2, Presentation, FileJson } from 'lucide-react'
import { Card } from '@/components/shared/Card'
import { Button } from '@/components/shared/Button'
import { Badge } from '@/components/shared/Badge'
import { exportsApi, type ExportFormat } from '@/api/exports'
import { useDatasetStore } from '@/store/datasetStore'

interface ExportOption {
  format: ExportFormat
  label: string
  description: string
  icon: React.ElementType
  badge?: string
}

const EXPORT_OPTIONS: ExportOption[] = [
  {
    format:      'pdf',
    label:       'PDF Report',
    description: 'Full analysis report with executive summary, charts, and recommendations.',
    icon:        FileText,
    badge:       'popular',
  },
  {
    format:      'xlsx',
    label:       'Excel Workbook',
    description: 'Column profiles, KPIs, anomalies, and forecasts in separate sheets.',
    icon:        Table2,
  },
  {
    format:      'pptx',
    label:       'PowerPoint Deck',
    description: 'Boardroom-ready slide deck with key findings and visualisations.',
    icon:        Presentation,
  },
  {
    format:      'json',
    label:       'JSON Export',
    description: 'Machine-readable full analysis output for downstream pipelines.',
    icon:        FileJson,
  },
]

export function ExportResultsPage() {
  const { currentDataset } = useDatasetStore()
  const [downloading, setDownloading] = useState<ExportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleExport = async (format: ExportFormat) => {
    if (!currentDataset) return
    setDownloading(format)
    setError(null)
    try {
      const { downloadUrl } = await exportsApi.requestExport(currentDataset.id, format)
      window.open(downloadUrl, '_blank')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.')
    } finally {
      setDownloading(null)
    }
  }

  if (!currentDataset || currentDataset.status !== 'ready') {
    return (
      <div className="flex items-center justify-center h-64 text-dp-muted text-sm">
        Complete analysis before exporting results.
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-5 animate-fade-in">
      <div>
        <h1 className="text-base font-semibold text-dp-text mb-0.5">Export results</h1>
        <p className="text-xs text-dp-muted">
          Download your analysis as a report, spreadsheet, or structured data.
        </p>
      </div>

      {error && (
        <div className="px-3 py-2 bg-rose-50 border border-rose-100 rounded-md text-xs text-dp-rose">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {EXPORT_OPTIONS.map((opt) => (
          <Card key={opt.format} padding="md">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-dp bg-dp-violet-dim flex items-center
                justify-center flex-shrink-0">
                <opt.icon size={18} className="text-dp-violet" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-dp-text">{opt.label}</span>
                  {opt.badge && (
                    <Badge variant="violet">{opt.badge}</Badge>
                  )}
                </div>
                <p className="text-xs text-dp-muted mt-0.5">{opt.description}</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                loading={downloading === opt.format}
                onClick={() => handleExport(opt.format)}
                className="flex-shrink-0"
              >
                <Download size={12} />
                Download
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}