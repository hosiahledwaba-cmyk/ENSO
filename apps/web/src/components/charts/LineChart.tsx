import { ChartContainer, type LegendItem } from './ChartContainer'

export interface LineDataPoint {
  x: string | number
  [seriesKey: string]: string | number | null | undefined
}

export interface LineSeriesConfig {
  key: string
  label: string
  color: string
  dashed?: boolean
  showArea?: boolean
  strokeWidth?: number
}

interface LineChartProps {
  title: string
  subtitle?: string
  data: LineDataPoint[]
  series: LineSeriesConfig[]
  unit?: string
  height?: number
  thresholdLines?: Array<{ value: number; label: string; color?: string; dashed?: boolean }>
  interpretation?: string
  emptyMessage?: string
  yDomain?: [number, number]
  xAxisLabel?: string
  yAxisLabel?: string
}

export function LineChart({
  title,
  subtitle,
  data,
  series,
  unit = '',
  height = 240,
  thresholdLines,
  interpretation,
  emptyMessage,
  yDomain,
  xAxisLabel,
  yAxisLabel,
}: LineChartProps) {
  const legend: LegendItem[] = series.map((s) => ({ label: s.label, color: s.color }))
  if (thresholdLines) {
    thresholdLines.forEach((t) => {
      legend.push({ label: t.label, color: t.color ?? 'var(--accent-terracotta)' })
    })
  }

  if (!data || data.length === 0) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        empty
        emptyMessage={emptyMessage ?? 'No time series records available.'}
        ariaLabel={title}
      >
        {() => null}
      </ChartContainer>
    )
  }

  let allY: number[] = []
  data.forEach((d) => {
    series.forEach((s) => {
      const v = d[s.key]
      if (typeof v === 'number' && !isNaN(v)) {
        allY.push(v)
      }
    })
  })

  if (thresholdLines) {
    thresholdLines.forEach((t) => allY.push(t.value))
  }

  if (allY.length === 0) allY = [0, 1]

  const rawMin = Math.min(...allY)
  const rawMax = Math.max(...allY)
  const pad = (rawMax - rawMin) * 0.1 || 1

  const minVal = yDomain ? yDomain[0] : rawMin - pad
  const maxVal = yDomain ? yDomain[1] : rawMax + pad
  const valRange = maxVal - minVal || 1

  const width = 640
  const margin = { top: 20, right: 30, bottom: xAxisLabel ? 45 : 35, left: yAxisLabel ? 65 : 55 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const getX = (idx: number) =>
    data.length === 1 ? margin.left + innerWidth / 2 : margin.left + (idx / (data.length - 1)) * innerWidth
  const getY = (val: number) => margin.top + innerHeight - ((val - minVal) / valRange) * innerHeight

  return (
    <ChartContainer
      title={title}
      subtitle={subtitle}
      legend={legend}
      interpretation={interpretation}
      ariaLabel={title}
    >
      {(setTooltip) => (
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="chart-svg"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const val = minVal + pct * valRange
            const y = margin.top + innerHeight - pct * innerHeight
            return (
              <g key={pct}>
                <line
                  x1={margin.left}
                  y1={y}
                  x2={width - margin.right}
                  y2={y}
                  stroke="var(--chart-grid)"
                  strokeDasharray="2,2"
                />
                <text
                  x={margin.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="10"
                  fill="var(--chart-axis)"
                  fontFamily="var(--font-mono)"
                >
                  {val.toFixed(1)}
                </text>
              </g>
            )
          })}

          {/* Y Axis Label */}
          {yAxisLabel && (
            <text
              transform={`rotate(-90)`}
              x={-(margin.top + innerHeight / 2)}
              y={14}
              textAnchor="middle"
              fontSize="10"
              fill="var(--text-muted)"
              fontFamily="var(--font-sans)"
              fontWeight="500"
            >
              {yAxisLabel}
            </text>
          )}

          {/* Threshold Lines */}
          {thresholdLines?.map((t, idx) => {
            const y = getY(t.value)
            const color = t.color ?? 'var(--accent-terracotta)'
            return (
              <g key={idx}>
                <line
                  x1={margin.left}
                  y1={y}
                  x2={width - margin.right}
                  y2={y}
                  stroke={color}
                  strokeWidth="1.5"
                  strokeDasharray={t.dashed === false ? undefined : '4,3'}
                />
                <text
                  x={width - margin.right}
                  y={y - 4}
                  textAnchor="end"
                  fontSize="9"
                  fill={color}
                  fontFamily="var(--font-mono)"
                  fontWeight="600"
                >
                  {t.label} ({t.value.toFixed(1)}{unit})
                </text>
              </g>
            )
          })}

          {/* Series Area & Lines */}
          {series.map((s) => {
            const points = data
              .map((d, i) => {
                const val = d[s.key]
                if (typeof val !== 'number' || isNaN(val)) return null
                return { x: getX(i), y: getY(val), val, rawX: d.x }
              })
              .filter((p): p is { x: number; y: number; val: number; rawX: string | number } => p !== null)

            if (points.length === 0) return null

            const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')

            const zeroY = getY(Math.max(minVal, 0))
            const areaPath = `${linePath} L ${points[points.length - 1].x} ${zeroY} L ${points[0].x} ${zeroY} Z`

            return (
              <g key={s.key}>
                {s.showArea && (
                  <path d={areaPath} fill={s.color} fillOpacity="0.12" />
                )}
                <path
                  d={linePath}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={s.strokeWidth ?? 2}
                  strokeDasharray={s.dashed ? '4,4' : undefined}
                />
                {/* Data Points */}
                {points.map((p, i) => (
                  <circle
                    key={i}
                    cx={p.x}
                    cy={p.y}
                    r={points.length > 25 ? 2.5 : 3.5}
                    fill="#FFFFFF"
                    stroke={s.color}
                    strokeWidth="1.75"
                    style={{ cursor: 'pointer', transition: 'r 0.15s ease' }}
                    onMouseEnter={(e) => {
                      const rect = (e.target as SVGElement).getBoundingClientRect()
                      setTooltip({
                        x: rect.left + rect.width / 2,
                        y: rect.top,
                        text: `${p.rawX} · ${s.label}: ${p.val.toFixed(2)}${unit}`,
                      })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                ))}
              </g>
            )
          })}

          {/* X Axis Ticks & Labels */}
          {data.map((d, i) => {
            // Show every tick if <= 10 points, else subsample
            const step = Math.ceil(data.length / 8)
            if (i % step !== 0 && i !== data.length - 1) return null
            const x = getX(i)
            return (
              <g key={i}>
                <line
                  x1={x}
                  y1={height - margin.bottom}
                  x2={x}
                  y2={height - margin.bottom + 4}
                  stroke="var(--chart-axis)"
                />
                <text
                  x={x}
                  y={height - margin.bottom + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--text-muted)"
                  fontFamily="var(--font-mono)"
                >
                  {d.x}
                </text>
              </g>
            )
          })}

          {/* X Axis Label */}
          {xAxisLabel && (
            <text
              x={margin.left + innerWidth / 2}
              y={height - 6}
              textAnchor="middle"
              fontSize="10"
              fill="var(--text-muted)"
              fontFamily="var(--font-sans)"
              fontWeight="500"
            >
              {xAxisLabel}
            </text>
          )}
        </svg>
      )}
    </ChartContainer>
  )
}
