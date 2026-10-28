import { useState, type ReactNode } from 'react'
import { ErrorBoundary } from '../ErrorBoundary'

export interface LegendItem {
  label: string
  color: string
}

interface ChartContainerProps {
  title: string
  subtitle?: string
  legend?: LegendItem[]
  interpretation?: ReactNode
  empty?: boolean
  emptyMessage?: string
  children: (tooltipSetter: (tooltip: { x: number; y: number; text: string } | null) => void) => ReactNode
  height?: number
  ariaLabel: string
}

export function ChartContainer({
  title,
  subtitle,
  legend,
  interpretation,
  empty,
  emptyMessage,
  children,
  ariaLabel,
}: ChartContainerProps) {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null)

  return (
    <ErrorBoundary fallbackTitle={`Error rendering ${title}`}>
      <div className="chart-container" role="figure" aria-label={ariaLabel}>
        <div className="chart-header">
          <div>
            <h4 className="chart-title">{title}</h4>
            {subtitle && <div className="chart-subtitle">{subtitle}</div>}
          </div>
          {legend && legend.length > 0 && (
            <div className="chart-legend">
              {legend.map((item) => (
                <div key={item.label} className="chart-legend-item">
                  <span className="chart-legend-swatch" style={{ backgroundColor: item.color }} />
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {empty ? (
          <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            {emptyMessage ?? 'No data available for this visualisation.'}
          </div>
        ) : (
          <div style={{ position: 'relative' }}>
            {children(setTooltip)}
            {tooltip && (
              <div
                className="chart-tooltip"
                style={{
                  left: `${tooltip.x}px`,
                  top: `${tooltip.y}px`,
                }}
              >
                {tooltip.text}
              </div>
            )}
          </div>
        )}

        {interpretation && (
          <div className="chart-interpretation">
            <strong>Interpretation: </strong>
            {interpretation}
          </div>
        )}
      </div>
    </ErrorBoundary>
  )
}
