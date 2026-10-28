import { ChartContainer } from './ChartContainer'

export interface CalibrationBin {
  mean_forecast: number
  observed_frequency: number
  sample_count: number
  bin_label?: string
}

export interface ModelCalibrationSeries {
  model_name: string
  color: string
  bins: CalibrationBin[]
  ece?: number
  reliability_error?: number
}

interface ReliabilityChartProps {
  title: string
  subtitle?: string
  models: ModelCalibrationSeries[]
  height?: number
  interpretation?: string
  emptyMessage?: string
}

export function ReliabilityChart({
  title,
  subtitle,
  models,
  height = 280,
  interpretation,
  emptyMessage,
}: ReliabilityChartProps) {
  const legend = models.map((m) => ({
    label: `${m.model_name}${m.ece !== undefined ? ` (ECE: ${m.ece.toFixed(3)})` : ''}`,
    color: m.color,
  }))
  legend.push({ label: 'Perfect Calibration (1:1 Reference)', color: 'var(--chart-axis)' })

  if (!models || models.length === 0 || models.every((m) => m.bins.length === 0)) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        empty
        emptyMessage={emptyMessage ?? 'No probability calibration bins available.'}
        ariaLabel={title}
      >
        {() => null}
      </ChartContainer>
    )
  }

  const width = 640
  const margin = { top: 20, right: 30, bottom: 45, left: 60 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const getX = (val: number) => margin.left + Math.max(0, Math.min(1, val)) * innerWidth
  const getY = (val: number) => margin.top + innerHeight - Math.max(0, Math.min(1, val)) * innerHeight

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
          {/* Probability Gridlines */}
          {[0, 0.2, 0.4, 0.6, 0.8, 1.0].map((tick) => {
            const x = getX(tick)
            const y = getY(tick)
            return (
              <g key={tick}>
                {/* Horizontal grid */}
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
                  {(tick * 100).toFixed(0)}%
                </text>

                {/* Vertical grid */}
                <line
                  x1={x}
                  y1={margin.top}
                  x2={x}
                  y2={height - margin.bottom}
                  stroke="var(--chart-grid)"
                  strokeDasharray="2,2"
                />
                <text
                  x={x}
                  y={height - margin.bottom + 16}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--chart-axis)"
                  fontFamily="var(--font-mono)"
                >
                  {(tick * 100).toFixed(0)}%
                </text>
              </g>
            )
          })}

          {/* Perfect Calibration 1:1 Diagonal Reference Line */}
          <line
            x1={getX(0)}
            y1={getY(0)}
            x2={getX(1)}
            y2={getY(1)}
            stroke="var(--text-muted)"
            strokeWidth="1.5"
            strokeDasharray="4,4"
          />

          {/* Under-forecasting / Over-forecasting zone annotations */}
          <text
            x={getX(0.15)}
            y={getY(0.7)}
            fontSize="9"
            fill="var(--text-dim)"
            fontStyle="italic"
            fontFamily="var(--font-sans)"
          >
            Under-Forecasting Zone
          </text>
          <text
            x={getX(0.65)}
            y={getY(0.25)}
            fontSize="9"
            fill="var(--text-dim)"
            fontStyle="italic"
            fontFamily="var(--font-sans)"
          >
            Over-Forecasting Zone
          </text>

          {/* Model Calibration Curves */}
          {models.map((m) => {
            const validBins = m.bins.filter(
              (b) => typeof b.mean_forecast === 'number' && typeof b.observed_frequency === 'number'
            )
            if (validBins.length === 0) return null

            const sorted = [...validBins].sort((a, b) => a.mean_forecast - b.mean_forecast)
            const pathD = sorted
              .map((b, i) => `${i === 0 ? 'M' : 'L'} ${getX(b.mean_forecast)} ${getY(b.observed_frequency)}`)
              .join(' ')

            return (
              <g key={m.model_name}>
                <path
                  d={pathD}
                  fill="none"
                  stroke={m.color}
                  strokeWidth="2.25"
                  strokeLinecap="round"
                />
                {/* Points with bubble radius proportional to sample size */}
                {sorted.map((b, i) => {
                  const r = Math.min(8, Math.max(3.5, 3 + Math.sqrt(b.sample_count || 1) * 2))
                  const cx = getX(b.mean_forecast)
                  const cy = getY(b.observed_frequency)

                  return (
                    <circle
                      key={i}
                      cx={cx}
                      cy={cy}
                      r={r}
                      fill={m.color}
                      stroke="#FFFFFF"
                      strokeWidth="1.5"
                      style={{ cursor: 'pointer', transition: 'r 0.15s ease' }}
                      onMouseEnter={(e) => {
                        const rect = (e.target as SVGElement).getBoundingClientRect()
                        setTooltip({
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                          text: `${m.model_name}: Forecast ${(b.mean_forecast * 100).toFixed(1)}% → Observed ${(b.observed_frequency * 100).toFixed(1)}% (N=${b.sample_count})`,
                        })
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  )
                })}
              </g>
            )
          })}

          {/* Axis Titles */}
          <text
            x={margin.left + innerWidth / 2}
            y={height - 6}
            textAnchor="middle"
            fontSize="10"
            fontWeight="500"
            fill="var(--text-charcoal)"
            fontFamily="var(--font-sans)"
          >
            Forecasted Probability P(Drought)
          </text>
          <text
            transform="rotate(-90)"
            x={-(margin.top + innerHeight / 2)}
            y={16}
            textAnchor="middle"
            fontSize="10"
            fontWeight="500"
            fill="var(--text-charcoal)"
            fontFamily="var(--font-sans)"
          >
            Observed Event Frequency
          </text>
        </svg>
      )}
    </ChartContainer>
  )
}
