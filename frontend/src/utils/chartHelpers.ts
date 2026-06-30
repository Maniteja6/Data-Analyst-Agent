import type { VegaLiteSpec } from '@/types/conversation'

export function buildBarSpec(
  data: { label: string; value: number }[],
  xTitle = 'Category',
  yTitle = 'Value',
): VegaLiteSpec {
  return {
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    mark: 'bar',
    data: { values: data.map((d) => ({ [xTitle]: d.label, [yTitle]: d.value })) },
    encoding: {
      x: { field: xTitle, type: 'nominal', axis: { labelAngle: -30 } },
      y: { field: yTitle, type: 'quantitative' },
      color: { value: '#5B4FE8' },
    },
    width: 400,
    height: 200,
  }
}

export function buildLineSpec(
  data: { x: string; y: number }[],
  xTitle = 'Time',
  yTitle = 'Value',
): VegaLiteSpec {
  return {
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    mark: 'line',
    data: { values: data.map((d) => ({ [xTitle]: d.x, [yTitle]: d.y })) },
    encoding: {
      x: { field: xTitle, type: 'temporal' },
      y: { field: yTitle, type: 'quantitative' },
      color: { value: '#5B4FE8' },
    },
    width: 400,
    height: 200,
  }
}