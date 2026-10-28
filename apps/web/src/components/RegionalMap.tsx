import { useState, useId } from 'react'
import type { SubregionForecastItem } from '../api/client'

interface RegionalMapProps {
  subregions: SubregionForecastItem[]
  selectedRegionId: string
  onSelectRegion: (regionId: string) => void
  colorMetric?: 'probability' | 'rainfall_anomaly'
}

export function RegionalMap({
  subregions,
  selectedRegionId,
  onSelectRegion,
  colorMetric = 'probability',
}: RegionalMapProps) {
  const mapId = useId()
  const [hoveredRegionId, setHoveredRegionId] = useState<string | null>(null)

  // Bounding box of Southern Africa focus area
  const LON_MIN = 24.0
  const LON_MAX = 33.5
  const LAT_MIN = -31.5 // bottom
  const LAT_MAX = -21.5 // top
  const WIDTH = 560
  const HEIGHT = 420

  const projectX = (lon: number) => {
    return ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * WIDTH
  }

  const projectY = (lat: number) => {
    return ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * HEIGHT
  }

  // Polygon coordinate sets for subregions
  const subregionPolygons: Record<string, [number, number][]> = {
    ZA_LIMPOPO: [
      [27.0, -22.1],
      [31.8, -22.2],
      [31.9, -24.8],
      [29.2, -25.0],
      [27.2, -24.8],
      [26.9, -23.4],
    ],
    ZA_MAIZE_WEST: [
      [24.8, -25.2],
      [27.6, -25.2],
      [27.6, -28.3],
      [24.8, -28.3],
    ],
    ZA_MAIZE_EAST: [
      [28.4, -25.2],
      [31.2, -25.2],
      [31.2, -27.4],
      [28.4, -27.4],
    ],
    ZA_SRZ: [
      [25.0, -22.0],
      [32.0, -22.0],
      [32.0, -30.0],
      [25.0, -30.0],
    ],
  }

  const getFillColor = (sub: SubregionForecastItem, isSelected: boolean, isHovered: boolean) => {
    if (colorMetric === 'probability') {
      const p = sub.forecast.probability
      if (p >= 0.40) {
        return isSelected ? '#B35327' : isHovered ? '#D7774A' : '#C96A3E' // Terracotta
      }
      if (p >= 0.25) {
        return isSelected ? '#C4AC8F' : isHovered ? '#E3D2BE' : '#D6C2A7' // Sand
      }
      return isSelected ? '#234C4A' : isHovered ? '#3D7573' : '#2D5F5D' // Slate
    }

    // Color by rainfall anomaly z-score
    const z = sub.rainfall_anomaly.october_zscore
    if (z <= -1.0) return '#C96A3E' // Severe dry
    if (z < 0) return '#D6C2A7' // Mild dry
    return '#2D5F5D' // Above normal
  }

  const handleKeyDown = (e: React.KeyboardEvent, regionId: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelectRegion(regionId)
    }
  }

  return (
    <div
      className="regional-map-container panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        padding: '1.25rem',
        background: 'var(--bg-cream)',
        borderRadius: '4px',
        border: '1px solid var(--border-sand)',
      }}
      aria-labelledby={`${mapId}-title`}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h3 id={`${mapId}-title`} className="panel-title" style={{ margin: 0, fontSize: '1rem' }}>
            Southern Africa Agro-Climatic Subregions
          </h3>
          <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Interactive regional risk map for the Limpopo River Basin and Maize Belt Summer Rainfall Zone
          </p>
        </div>

        {/* Legend */}
        <div
          role="region"
          aria-label="Map risk level legend"
          style={{
            display: 'flex',
            gap: '0.6rem',
            alignItems: 'center',
            fontSize: '0.72rem',
            fontFamily: 'var(--font-mono)',
            padding: '0.35rem 0.6rem',
            background: 'var(--bg-white)',
            borderRadius: '3px',
            border: '1px solid var(--border-sand)',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--text-charcoal)' }}>Drought Risk:</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
            <span style={{ width: 10, height: 10, backgroundColor: '#C96A3E', borderRadius: 2 }} />
            High (&gt;40%)
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
            <span style={{ width: 10, height: 10, backgroundColor: '#D6C2A7', borderRadius: 2 }} />
            Elevated (25-40%)
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
            <span style={{ width: 10, height: 10, backgroundColor: '#2D5F5D', borderRadius: 2 }} />
            Normal (&lt;25%)
          </span>
        </div>
      </div>

      {/* SVG Map Canvas */}
      <div
        style={{
          width: '100%',
          overflow: 'hidden',
          borderRadius: '3px',
          background: '#F0EBE1',
          border: '1px solid var(--border-sand)',
          position: 'relative',
        }}
      >
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
          role="img"
          aria-label="Map of Southern Africa showing drought risk and rainfall anomalies across 4 subregions"
        >
          {/* Background Graticule Grid Lines */}
          <g stroke="rgba(31, 31, 31, 0.08)" strokeWidth="1" strokeDasharray="3 3">
            {[-30, -28, -26, -24, -22].map((lat) => (
              <line key={`lat-${lat}`} x1={0} y1={projectY(lat)} x2={WIDTH} y2={projectY(lat)} />
            ))}
            {[26, 28, 30, 32].map((lon) => (
              <line key={`lon-${lon}`} x1={projectX(lon)} y1={0} x2={projectX(lon)} y2={HEIGHT} />
            ))}
          </g>

          {/* Latitude / Longitude Labels */}
          <g fontSize="9" fill="var(--chart-axis)" fontFamily="var(--font-mono)">
            {[-30, -26, -22].map((lat) => (
              <text key={`txt-lat-${lat}`} x={8} y={projectY(lat) - 4}>
                {Math.abs(lat)}°S
              </text>
            ))}
            {[26, 29, 32].map((lon) => (
              <text key={`txt-lon-${lon}`} x={projectX(lon) + 4} y={HEIGHT - 6}>
                {lon}°E
              </text>
            ))}
          </g>

          {/* Subregion Polygons (Rendering non-aggregate subregions first) */}
          {subregions
            .filter((s) => s.region_id !== 'ZA_SRZ')
            .map((sub) => {
              const coords = subregionPolygons[sub.region_id]
              if (!coords) return null
              const isSelected = selectedRegionId === sub.region_id
              const isHovered = hoveredRegionId === sub.region_id
              const pointsStr = coords
                .map(([lon, lat]) => `${projectX(lon)},${projectY(lat)}`)
                .join(' ')

              const centroidX = projectX(sub.centroid[1])
              const centroidY = projectY(sub.centroid[0])
              const fillColor = getFillColor(sub, isSelected, isHovered)

              return (
                <g key={sub.region_id}>
                  <polygon
                    id={`region-poly-${sub.region_id}`}
                    data-testid={`region-poly-${sub.region_id.toLowerCase()}`}
                    points={pointsStr}
                    fill={fillColor}
                    fillOpacity={isSelected ? 0.95 : 0.8}
                    stroke={isSelected ? '#1F1F1F' : 'rgba(31, 31, 31, 0.4)'}
                    strokeWidth={isSelected ? 3 : 1.5}
                    tabIndex={0}
                    role="button"
                    aria-label={`${sub.region_name}: ${Math.round(sub.forecast.probability * 100)}% drought probability, ${sub.forecast.risk_category} risk`}
                    aria-pressed={isSelected}
                    style={{
                      cursor: 'pointer',
                      transition: 'fill 0.15s ease, stroke-width 0.15s ease',
                      outline: 'none',
                    }}
                    onClick={() => onSelectRegion(sub.region_id)}
                    onMouseEnter={() => setHoveredRegionId(sub.region_id)}
                    onMouseLeave={() => setHoveredRegionId(null)}
                    onKeyDown={(e) => handleKeyDown(e, sub.region_id)}
                  />

                  {/* Centroid Label & Pill */}
                  <g pointerEvents="none">
                    <rect
                      x={centroidX - 45}
                      y={centroidY - 14}
                      width={90}
                      height={24}
                      rx={3}
                      fill="var(--bg-white)"
                      fillOpacity={0.92}
                      stroke={isSelected ? '#1F1F1F' : 'var(--border-sand)'}
                      strokeWidth={isSelected ? 1.5 : 1}
                    />
                    <text
                      x={centroidX}
                      y={centroidY - 1}
                      textAnchor="middle"
                      fontSize="9"
                      fontWeight="700"
                      fill="var(--text-charcoal)"
                      fontFamily="var(--font-sans)"
                    >
                      {sub.region_id.replace('ZA_', '')}
                    </text>
                    <text
                      x={centroidX}
                      y={centroidY + 8}
                      textAnchor="middle"
                      fontSize="8.5"
                      fontWeight="600"
                      fill={sub.forecast.probability >= 0.4 ? '#C96A3E' : 'var(--text-muted)'}
                      fontFamily="var(--font-mono)"
                    >
                      P: {Math.round(sub.forecast.probability * 100)}%
                    </text>
                  </g>
                </g>
              )
            })}

          {/* Aggregate Zone Outline (ZA_SRZ) */}
          {(() => {
            const aggregateSub = subregions.find((s) => s.region_id === 'ZA_SRZ')
            if (!aggregateSub) return null
            const coords = subregionPolygons.ZA_SRZ
            const pointsStr = coords
              .map(([lon, lat]) => `${projectX(lon)},${projectY(lat)}`)
              .join(' ')
            const isSelected = selectedRegionId === 'ZA_SRZ'

            return (
              <polygon
                key="ZA_SRZ_OUTLINE"
                data-testid="region-poly-za_srz"
                points={pointsStr}
                fill="none"
                stroke={isSelected ? '#C96A3E' : 'rgba(31, 31, 31, 0.45)'}
                strokeWidth={isSelected ? 2.5 : 1.5}
                strokeDasharray="5 4"
                tabIndex={0}
                role="button"
                aria-label="Limpopo and Maize Belt Summer Rainfall Zone Aggregate Boundary"
                style={{ cursor: 'pointer', outline: 'none' }}
                onClick={() => onSelectRegion('ZA_SRZ')}
                onKeyDown={(e) => handleKeyDown(e, 'ZA_SRZ')}
              />
            )
          })()}
        </svg>
      </div>

      {/* Subregion Quick Switcher Tabs */}
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
        {subregions.map((sub) => {
          const isSelected = selectedRegionId === sub.region_id
          return (
            <button
              key={sub.region_id}
              data-testid={`select-region-${sub.region_id.toLowerCase()}`}
              type="button"
              className={`btn ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
              style={{
                fontSize: '0.75rem',
                padding: '0.3rem 0.6rem',
                borderRadius: '3px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
              onClick={() => onSelectRegion(sub.region_id)}
            >
              <span>{sub.region_name.split('(')[0].trim()}</span>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontFamily: 'var(--font-mono)',
                  padding: '0.1rem 0.3rem',
                  borderRadius: '2px',
                  backgroundColor: isSelected ? 'rgba(255,255,255,0.2)' : 'var(--bg-cream)',
                }}
              >
                {Math.round(sub.forecast.probability * 100)}%
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
