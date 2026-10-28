import { ChartContainer } from './ChartContainer'

export interface HeatmapCell {
  row: string
  col: string
  value: number
  label?: string
  sublabel?: string
}

interface HeatmapChartProps {
  title: string
  subtitle?: string
  rows: string[]
  cols: string[]
  cells: HeatmapCell[]
  height?: number
  valueFormatter?: (val: number) => string
  interpretation?: string
  emptyMessage?: string
}

export function HeatmapChart({
  title,
  subtitle,
  rows,
  cols,
  cells,
  height = 240,
  valueFormatter = (v) => v.toFixed(3),
  interpretation,
  emptyMessage,
}: HeatmapChartProps) {
  if (!cells || cells.length === 0 || rows.length === 0 || cols.length === 0) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        empty
        emptyMessage={emptyMessage ?? 'No matrix comparison data available.'}
        ariaLabel={title}
      >
        {() => null}
      </ChartContainer>
    )
  }

  const values = cells.map((c) => c.value).filter((v) => typeof v === 'number' && !isNaN(v))
  const minVal = values.length ? Math.min(...values) : 0
  const maxVal = values.length ? Math.max(...values) : 1
  const valRange = maxVal - minVal || 1

  const width = 640
  const margin = { top: 35, right: 30, bottom: 20, left: 160 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const colWidth = innerWidth / cols.length
  const rowHeight = innerHeight / rows.length

  // Interpolate color from Sand to Terracotta
  const getCellColor = (val: number) => {
    const norm = Math.max(0, Math.min(1, (val - minVal) / valRange))
    // 0 -> #F7F4EF, 0.5 -> #D6C2A7, 1.0 -> #C96A3E
    if (norm < 0.5) {
      return `rgb(${Math.round(247 - norm * 2 * (247 - 214))}, ${Math.round(244 - norm * 2 * (244 - 194))}, ${Math.round(239 - norm * 2 * (239 - 167))})`
    }
    const t = (norm - 0.5) * 2
    return `rgb(${Math.round(214 - t * (214 - 201))}, ${Math.round(194 - t * (194 - 106))}, ${Math.round(167 - t * (167 - 62))})`
  }

  const legend = [
    { label: `Min (${minVal.toFixed(2)})`, color: '#F7F4EF' },
    { label: `Mid (${((minVal + maxVal) / 2).toFixed(2)})`, color: '#D6C2A7' },
    { label: `Max (${maxVal.toFixed(2)})`, color: '#C96A3E' },
  ]

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
          {/* Column Headers */}
          {cols.map((col, colIdx) => {
            const x = margin.left + colIdx * colWidth + colWidth / 2
            return (
              <text
                key={col}
                x={x}
                y={margin.top - 12}
                textAnchor="middle"
                fontSize="11"
                fontWeight="600"
                fontFamily="var(--font-sans)"
                fill="var(--text-charcoal)"
              >
                {col}
              </text>
            )
          })}

          {/* Rows & Cells */}
          {rows.map((row, rowIdx) => {
            const y = margin.top + rowIdx * rowHeight
            return (
              <g key={row}>
                {/* Row Header */}
                <text
                  x={margin.left - 12}
                  y={y + rowHeight / 2 + 4}
                  textAnchor="end"
                  fontSize="11"
                  fontWeight="500"
                  fontFamily="var(--font-sans)"
                  fill="var(--text-charcoal)"
                >
                  {row.length > 24 ? `${row.slice(0, 22)}…` : row}
                </text>

                {cols.map((col, colIdx) => {
                  const x = margin.left + colIdx * colWidth
                  const cell = cells.find((c) => c.row === row && c.col === col)
                  const val = cell?.value ?? 0
                  const color = getCellColor(val)
                  const isDark = (val - minVal) / valRange > 0.65

                  return (
                    <g key={col}>
                      <rect
                        x={x + 2}
                        y={y + 2}
                        width={colWidth - 4}
                        height={rowHeight - 4}
                        fill={color}
                        stroke="var(--border-sand)"
                        strokeWidth="1"
                        rx="2"
                        style={{ cursor: 'pointer', transition: 'filter 0.15s ease' }}
                        onMouseEnter={(e) => {
                          const rect = (e.target as SVGElement).getBoundingClientRect()
                          setTooltip({
                            x: rect.left + rect.width / 2,
                            y: rect.top,
                            text: `${row} · ${col}: ${cell?.label ?? valueFormatter(val)} ${cell?.sublabel ? `(${cell.sublabel})` : ''}`,
                          })
                        }}
                        onMouseLeave={() => setTooltip(null)}
                      />
                      <text
                        x={x + colWidth / 2}
                        y={y + rowHeight / 2 + 4}
                        textAnchor="middle"
                        fontSize="10"
                        fontFamily="var(--font-mono)"
                        fontWeight="600"
                        fill={isDark ? '#FFFFFF' : 'var(--text-charcoal)'}
                        pointerEvents="none"
                      >
                        {cell?.label ?? valueFormatter(val)}
                      </text>
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      )}
    </ChartContainer>
  )
}
