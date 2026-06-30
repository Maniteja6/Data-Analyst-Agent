import { LineChart, Line, ResponsiveContainer } from 'recharts'
import type { KPITrend } from '@/types/insights'
import { TREND_COLORS } from '@/utils/colorPalette'

interface SparklineProps {
  data: number[]
  trend?: KPITrend
  height?: number
  width?: number
}

export function Sparkline({ data, trend = 'stable', height = 28, width = 60 }: SparklineProps) {
  const chartData = data.map((v) => ({ v }))
  const color = TREND_COLORS[trend]

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={chartData}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}