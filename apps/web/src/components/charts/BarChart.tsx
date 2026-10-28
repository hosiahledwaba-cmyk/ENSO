import { ChartContainer, type LegendItem } from './ChartContainer'

export interface BarGroup {
  category: string
  values: Record<string, number> // seriesKey -> value
}

export interface BarSeriesConfig {
  key: string
  label: string
  color: string
}

interface BarChartProps {
  title: string
  subtitle?: string
  data: BarGroup[]
  series: BarSeriesConfig[]
  unit?: string
  height?: number
  horizontal?: boolean
  referenceLine?: { value: number; label: string; color?: string }
  interpretation?: string
  emptyMessage?: string
  yDomain?: [number, number]
}

export function BarChart({
  title,
  subtitle,
  data,
  series,
  unit = '',
  height = 240,
  horizontal = false,
  referenceLine,
  interpretation,
  emptyMessage,
  yDomain,
}: BarChartProps) {
  const legend: LegendItem[] = series.map((s) => ({ label: s.label, color: s.color }))

  if (!data || data.length === 0) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        empty
        emptyMessage={emptyMessage ?? 'No data records available for bar chart.'}
        ariaLabel={title}
      >
        {() => null}
      </ChartContainer>
    )
  }

  // Calculate min and max
  let allValues: number[] = []
  data.forEach((d) => {
    series.forEach((s) => {
      const v = d.values[s.key]
      if (typeof v === 'number' && !isNaN(v)) {
        allValues.push(v)
      }
    })
  })

  if (referenceLine) {
    allValues.push(referenceLine.value)
  }

  if (allValues.length === 0) {
    allValues = [0, 1]
  }

  const rawMin = Math.min(...allValues)
  const rawMax = Math.max(...allValues)

  const minVal = yDomain ? yDomain[0] : rawMin < 0 ? rawMin * 1.15 : 0
  const maxVal = yDomain ? yDomain[1] : rawMax > 0 ? rawMax * 1.15 : 1
  const valRange = maxVal - minVal || 1

  const width = 640
  const margin = horizontal
    ? { top: 20, right: 30, bottom: 30, left: 140 }
    : { top: 20, right: 20, bottom: 50, left: 55 }

  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const zeroPos = horizontal
    ? margin.left + ((0 - minVal) / valRange) * innerWidth
    : margin.top + innerHeight - ((0 - minVal) / valRange) * innerHeight

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
          {/* Background Gridlines */}
          {!horizontal &&
            [0, 0.25, 0.5, 0.75, 1].map((pct) => {
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
                    {val.toFixed(2)}
                  </text>
                </g>
              )
            })}

          {/* Reference Line */}
          {referenceLine && (
            <g>
              {!horizontal ? (
                <>
                  <line
                    x1={margin.left}
                    y1={margin.top + innerHeight - ((referenceLine.value - minVal) / valRange) * innerHeight}
                    x2={width - margin.right}
                    y2={margin.top + innerHeight - ((referenceLine.value - minVal) / valRange) * innerHeight}
                    stroke={referenceLine.color ?? 'var(--accent-terracotta)'}
                    strokeWidth="1.5"
                    strokeDasharray="4,3"
                  />
                  <text
                    x={width - margin.right}
                    y={margin.top + innerHeight - ((referenceLine.value - minVal) / valRange) * innerHeight - 5}
                    textAnchor="end"
                    fontSize="9"
                    fill={referenceLine.color ?? 'var(--accent-terracotta)'}
                    fontFamily="var(--font-mono)"
                    fontWeight="600"
                  >
                    {referenceLine.label} ({referenceLine.value.toFixed(3)})
                  </text>
                </>
              ) : (
                <>
                  <line
                    x1={margin.left + ((referenceLine.value - minVal) / valRange) * innerWidth}
                    y1={margin.top}
                    x2={margin.left + ((referenceLine.value - minVal) / valRange) * innerWidth}
                    y2={height - margin.bottom}
                    stroke={referenceLine.color ?? 'var(--accent-terracotta)'}
                    strokeWidth="1.5"
                    strokeDasharray="4,3"
                  />
                  <text
                    x={margin.left + ((referenceLine.value - minVal) / valRange) * innerWidth}
                    y={margin.top - 6}
                    textAnchor="middle"
                    fontSize="9"
                    fill={referenceLine.color ?? 'var(--accent-terracotta)'}
                    fontFamily="var(--font-mono)"
                    fontWeight="600"
                  >
                    {referenceLine.label}
                  </text>
                </>
              )}
            </g>
          )}

          {/* Zero baseline */}
          {minVal <= 0 && maxVal >= 0 && (
            <line
              x1={horizontal ? zeroPos : margin.left}
              y1={horizontal ? margin.top : zeroPos}
              x2={horizontal ? zeroPos : width - margin.right}
              y2={horizontal ? height - margin.bottom : zeroPos}
              stroke="var(--text-charcoal)"
              strokeWidth="1.2"
            />
          )}

          {/* Bars */}
          {!horizontal ? (
            // Vertical Bars
            data.map((group, groupIdx) => {
              const groupWidth = innerWidth / data.length
              const groupX = margin.left + groupIdx * groupWidth
              const barWidth = Math.max(8, (groupWidth * 0.75) / series.length)
              const offsetStart = groupX + (groupWidth - barWidth * series.length) / 2

              return (
                <g key={group.category}>
                  {/* Category Label */}
                  <text
                    x={groupX + groupWidth / 2}
                    y={height - margin.bottom + 18}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="500"
                    fill="var(--text-charcoal)"
                    fontFamily="var(--font-sans)"
                  >
                    {group.category}
                  </text>

                  {series.map((s, sIdx) => {
                    const val = group.values[s.key]
                    if (typeof val !== 'number' || isNaN(val)) return null

                    const barX = offsetStart + sIdx * barWidth
                    const h = (Math.abs(val) / valRange) * innerHeight
                    const barY = val >= 0 ? zeroPos - h : zeroPos

                    return (
                      <rect
                        key={s.key}
                        x={barX}
                        y={barY}
                        width={Math.max(2, barWidth - 3)}
                        height={Math.max(2, h)}
                        fill={s.color}
                        rx="1"
                        style={{ cursor: 'pointer', transition: 'opacity 0.15s ease' }}
                        onMouseEnter={(e) => {
                          const rect = (e.target as SVGElement).getBoundingClientRect()
                          setTooltip({
                            x: rect.left + rect.width / 2,
                            y: rect.top,
                            text: `${group.category} · ${s.label}: ${val >= 0 && s.key.includes('bss') ? `+${val.toFixed(4)}` : val.toFixed(4)}${unit}`,
                          })
                        }}
                        onMouseLeave={() => setTooltip(null)}
                      />
                    )
                  })}
                </g>
              )
            })
          ) : (
            // Horizontal Bars
            data.map((group, groupIdx) => {
              const groupHeight = innerHeight / data.length
              const groupY = margin.top + groupIdx * groupHeight
              const barHeight = Math.max(8, (groupHeight * 0.7) / series.length)
              const offsetStart = groupY + (groupHeight - barHeight * series.length) / 2

              return (
                <g key={group.category}>
                  {/* Category Label (Truncated nicely if long) */}
                  <text
                    x={margin.left - 10}
                    y={groupY + groupHeight / 2 + 4}
                    textAnchor="end"
                    fontSize="11"
                    fontWeight="500"
                    fill="var(--text-charcoal)"
                    fontFamily="var(--font-mono)"
                  >
                    {group.category.length > 20 ? `${group.category.slice(0, 18)}…` : group.category}
                  </text>

                  {series.map((s, sIdx) => {
                    const val = group.values[s.key]
                    if (typeof val !== 'number' || isNaN(val)) return null

                    const barY = offsetStart + sIdx * barHeight
                    const w = (Math.abs(val) / valRange) * innerWidth
                    const barX = val >= 0 ? zeroPos : zeroPos - w

                    return (
                      <g key={s.key}>
                        <rect
                          x={barX}
                          y={barY}
                          width={Math.max(2, w)}
                          height={Math.max(2, barHeight - 2)}
                          fill={s.color}
                          rx="1"
                          style={{ cursor: 'pointer', transition: 'opacity 0.15s ease' }}
                          onMouseEnter={(e) => {
                            const rect = (e.target as SVGElement).getBoundingClientRect()
                            setTooltip({
                              x: rect.left + rect.width / 2,
                              y: rect.top,
                              text: `${group.category} · ${s.label}: ${val >= 0 ? `+${val.toFixed(4)}` : val.toFixed(4)}${unit}`,
                            })
                          }}
                          onMouseLeave={() => setTooltip(null)}
                        />
                        {/* Value text beside bar */}
                        <text
                          x={val >= 0 ? barX + w + 4 : barX - 4}
                          y={barY + barHeight / 2 + 3}
                          textAnchor={val >= 0 ? 'start' : 'end'}
                          fontSize="9"
                          fontFamily="var(--font-mono)"
                          fill="var(--text-muted)"
                        >
                          {val >= 0 ? `+${val.toFixed(3)}` : val.toFixed(3)}
                        </text>
                      </g>
                    )
                  })}
                </g>
              )
            })
          )}
        </svg>
      )}
    </ChartContainer>
  )
}
