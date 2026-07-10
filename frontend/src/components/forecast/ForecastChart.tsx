import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip,
  CartesianGrid, ResponsiveContainer,
} from 'recharts'
import type { ForecastDataPoint } from '@/types/insights'
import { formatDate } from '@/utils/formatters'

interface ForecastChartProps {
  predictions: ForecastDataPoint[]
  targetColumn: string
  height?: number
}

export function ForecastChart({ predictions, targetColumn, height = 220 }: ForecastChartProps) {
  if (!predictions || predictions.length === 0) {
    return (
      <div className="flex items-center justify-center text-dp-muted text-xs" style={{ height }}>
        No forecast data available
      </div>
    )
  }

  const data = predictions.map((p) => ({
    date:  formatDate(p.timestamp),
    value: p.value,
    band:  [p.lowerBound, p.upperBound],
    lower: p.lowerBound,
    upper: p.upperBound,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E0D8" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#888780' }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: '#888780' }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            background: '#1A1A3E', border: 'none', borderRadius: 6,
            fontSize: 11, color: '#fff', padding: '6px 10px',
          }}
        />
        {/* Confidence band */}
        <Area
          dataKey="upper"
          stroke="none"
          fill="#5B4FE8"
          fillOpacity={0.08}
          legendType="none"
        />
        <Area
          dataKey="lower"
          stroke="none"
          fill="#ffffff"
          fillOpacity={1}
          legendType="none"
        />
        {/* Forecast line */}
        <Line
          dataKey="value"
          name={targetColumn}
          stroke="#5B4FE8"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}