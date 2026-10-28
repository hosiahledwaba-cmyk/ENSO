import { ChartContainer } from './ChartContainer'

export interface WaterfallStep {
  name: string
  value: number
  description?: string
  isTotal?: boolean
}

interface WaterfallChartProps {
  title: string
  subtitle?: string
  steps: WaterfallStep[]
  height?: number
  finalProbability?: number
  climatologyBaseline?: number
  interpretation?: string
  emptyMessage?: string
}

export function WaterfallChart({
  title,
  subtitle,
  steps,
  height = 240,
  finalProbability,
  climatologyBaseline = 0.20,
  interpretation,
  emptyMessage,
}: WaterfallChartProps) {
  if (!steps || steps.length === 0) {
    return (
      <ChartContainer
        title={title}
        subtitle={subtitle}
        empty
        emptyMessage={emptyMessage ?? 'No factor contribution steps available.'}
        ariaLabel={title}
      >
        {() => null}
      </ChartContainer>
    )
  }

  // Calculate cumulative step bounds
  let running = 0
  const renderedSteps: Array<{
    name: string
    value: number
    start: number
    end: number
    isPositive: boolean
    isTotal: boolean
    description?: string
  }> = []

  steps.forEach((s) => {
    if (s.isTotal) {
      renderedSteps.push({
        name: s.name,
        value: running,
        start: 0,
        end: running,
        isPositive: running >= 0,
        isTotal: true,
        description: s.description,
      })
    } else {
      const start = running
      running += s.value
      renderedSteps.push({
        name: s.name,
        value: s.value,
        start,
        end: running,
        isPositive: s.value >= 0,
        isTotal: false,
        description: s.description,
      })
    }
  })

  const allVals = [0, ...renderedSteps.flatMap((r) => [r.start, r.end])]
  const minVal = Math.min(-0.5, Math.min(...allVals) * 1.2)
  const maxVal = Math.max(0.5, Math.max(...allVals) * 1.2)
  const valRange = maxVal - minVal || 1

  const width = 640
  const margin = { top: 25, right: 30, bottom: 45, left: 55 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const getY = (val: number) => margin.top + innerHeight - ((val - minVal) / valRange) * innerHeight
  const zeroY = getY(0)

  const legend = [
    { label: 'Risk Increasing (+ Logit)', color: 'var(--accent-terracotta)' },
    { label: 'Risk Suppressing (- Logit)', color: 'var(--chart-blue-cool)' },
    { label: 'Total Logit Model Score', color: 'var(--text-charcoal)' },
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
          {/* Zero Line */}
          <line
            x1={margin.left}
            y1={zeroY}
            x2={width - margin.right}
            y2={zeroY}
            stroke="var(--chart-axis)"
            strokeWidth="1.2"
          />

          {/* Grid lines */}
          {[minVal, minVal / 2, 0, maxVal / 2, maxVal].map((val, idx) => (
            <g key={idx}>
              <line
                x1={margin.left}
                y1={getY(val)}
                x2={width - margin.right}
                y2={getY(val)}
                stroke="var(--chart-grid)"
                strokeDasharray="2,2"
              />
              <text
                x={margin.left - 6}
                y={getY(val) + 4}
                textAnchor="end"
                fontSize="9"
                fill="var(--chart-axis)"
                fontFamily="var(--font-mono)"
              >
                {val.toFixed(2)}
              </text>
            </g>
          ))}

          {/* Step Bars */}
          {renderedSteps.map((step, idx) => {
            const stepWidth = innerWidth / renderedSteps.length
            const barWidth = Math.max(14, stepWidth * 0.65)
            const x = margin.left + idx * stepWidth + (stepWidth - barWidth) / 2

            const yTop = getY(Math.max(step.start, step.end))
            const yBottom = getY(Math.min(step.start, step.end))
            const barHeight = Math.max(3, yBottom - yTop)

            const color = step.isTotal
              ? 'var(--text-charcoal)'
              : step.isPositive
              ? 'var(--accent-terracotta)'
              : 'var(--chart-blue-cool)'

            return (
              <g key={step.name}>
                {/* Connecting line to next step */}
                {idx < renderedSteps.length - 1 && !step.isTotal && (
                  <line
                    x1={x + barWidth}
                    y1={getY(step.end)}
                    x2={margin.left + (idx + 1) * stepWidth + (stepWidth - barWidth) / 2}
                    y2={getY(step.end)}
                    stroke="var(--border-sand)"
                    strokeDasharray="2,2"
                  />
                )}

                {/* Step Bar */}
                <rect
                  x={x}
                  y={yTop}
                  width={barWidth}
                  height={barHeight}
                  fill={color}
                  rx="1"
                  style={{ cursor: 'pointer', transition: 'opacity 0.15s ease' }}
                  onMouseEnter={(e) => {
                    const rect = (e.target as SVGElement).getBoundingClientRect()
                    setTooltip({
                      x: rect.left + rect.width / 2,
                      y: rect.top,
                      text: `${step.name}: ${step.value >= 0 ? `+${step.value.toFixed(3)}` : step.value.toFixed(3)} logit ${step.description ? `(${step.description})` : ''}`,
                    })
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />

                {/* Value text above bar */}
                <text
                  x={x + barWidth / 2}
                  y={step.isPositive ? yTop - 4 : yBottom + 12}
                  textAnchor="middle"
                  fontSize="9"
                  fontFamily="var(--font-mono)"
                  fill={color}
                  fontWeight="600"
                >
                  {step.value >= 0 ? `+${step.value.toFixed(2)}` : step.value.toFixed(2)}
                </text>

                {/* Step Label below */}
                <text
                  x={x + barWidth / 2}
                  y={height - margin.bottom + 14}
                  textAnchor="middle"
                  fontSize="10"
                  fontFamily="var(--font-sans)"
                  fill="var(--text-charcoal)"
                  fontWeight={step.isTotal ? '600' : '400'}
                >
                  {step.name.length > 14 ? `${step.name.slice(0, 12)}…` : step.name}
                </text>
              </g>
            )
          })}

          {/* Final Probability Callout Annotation */}
          {finalProbability !== undefined && (
            <g>
              <rect
                x={width - margin.right - 140}
                y={margin.top - 12}
                width={140}
                height={26}
                fill="var(--bg-cream)"
                stroke="var(--accent-terracotta)"
                rx="2"
              />
              <text
                x={width - margin.right - 70}
                y={margin.top + 5}
                textAnchor="middle"
                fontSize="11"
                fontFamily="var(--font-mono)"
                fontWeight="700"
                fill="var(--text-charcoal)"
              >
                P(Drought) = {(finalProbability * 100).toFixed(1)}%
              </text>
            </g>
          )}

          {/* Climatology Reference Line if present */}
          {climatologyBaseline !== undefined && (
            <text
              x={margin.left}
              y={margin.top - 8}
              fontSize="9"
              fontFamily="var(--font-mono)"
              fill="var(--text-muted)"
            >
              Climatology Baseline: {(climatologyBaseline * 100).toFixed(0)}%
            </text>
          )}
        </svg>
      )}
    </ChartContainer>
  )
}
