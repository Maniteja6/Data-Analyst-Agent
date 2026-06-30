import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { CHART_COLORS } from '@/utils/colorPalette'

interface HistogramChartProps {
  data: Array<{ bin: string; count: number }>
  title?: string
  height?: number
}

export function HistogramChart({ data, title, height = 140 }: HistogramChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-dp-muted text-xs" style={{ height }}>
        No distribution data
      </div>
    )
  }

  const max = Math.max(...data.map((d) => d.count))

  return (
    <div>
      {title && <p className="text-2xs text-dp-muted mb-1 font-semibold uppercase tracking-widest">{title}</p>}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 4, right: 0, left: -28, bottom: 0 }} barSize={8}>
          <XAxis
            dataKey="bin"
            tick={{ fontSize: 9, fill: '#888780' }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 9, fill: '#888780' }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: '#1A1A3E', border: 'none', borderRadius: 6,
              fontSize: 11, color: '#fff', padding: '4px 8px',
            }}
            cursor={{ fill: '#EEEDfe' }}
          />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={entry.count === max ? CHART_COLORS[0] : CHART_COLORS[0] + '60'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}