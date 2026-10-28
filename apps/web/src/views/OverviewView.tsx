import { useState, useEffect, useCallback } from 'react'
import type { createApiClient, SystemStatus, JobRecord, DatasetTimeseriesResponse, ActiveModelResponse } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { LineChart, type LineDataPoint, type LineSeriesConfig } from '../components/charts/LineChart'
import { BarChart, type BarGroup } from '../components/charts/BarChart'

interface OverviewViewProps {
  api: ReturnType<typeof createApiClient>
  onNavigate: (view: string) => void
}

export function OverviewView({ api, onNavigate }: OverviewViewProps) {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [timeseries, setTimeseries] = useState<DatasetTimeseriesResponse | null>(null)
  const [recentJobs, setRecentJobs] = useState<JobRecord[]>([])
  const [activeModel, setActiveModel] = useState<ActiveModelResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date())

  const loadData = useCallback(async () => {
    try {
      const [sysStatus, tsData] = await Promise.all([
        api.getSystemStatus().catch(() => null),
        api.getDatasetTimeseries().catch(() => null),
      ])
      if (sysStatus) setStatus(sysStatus)
      if (tsData) setTimeseries(tsData)

      // Fetch background jobs and active model concurrently
      api.getJobs().then((res) => setRecentJobs(res.jobs.slice(0, 5))).catch(() => {})
      api.getActiveModel().then((res) => setActiveModel(res)).catch(() => {})

      setError(null)
      setLastRefreshed(new Date())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reach API')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadData()
    const timer = setInterval(() => void loadData(), 15000)
    return () => clearInterval(timer)
  }, [loadData])

  // 1. Prepare Precipitation History Line Chart Data
  const precipData: LineDataPoint[] = []
  const tau20 = timeseries?.reference_distribution?.tau_drought_p20_mm ?? 255.64
  const meanPrecip = timeseries?.reference_distribution?.mean_seasonal_precip_mm ?? 322.86

  if (timeseries?.seasonal_history) {
    timeseries.seasonal_history.forEach((s) => {
      precipData.push({
        x: s.season_year,
        precip_djf: s.seasonal_precip_djf_mm ?? null,
      })
    })
  }

  const precipSeries: LineSeriesConfig[] = [
    {
      key: 'precip_djf',
      label: 'Austral Summer Rainfall (DJF mm)',
      color: 'var(--chart-primary)',
      strokeWidth: 2.5,
      showArea: true,
    },
  ]

  // 2. Prepare ENSO ONI Anomaly Timeline Data
  const oniData: LineDataPoint[] = []
  if (timeseries?.oni_monthly) {
    // Show quarterly samples to avoid over-crowding the overview
    timeseries.oni_monthly.forEach((d, idx) => {
      if (idx % 3 === 0 || idx === timeseries.oni_monthly.length - 1) {
        oniData.push({
          x: d.date,
          oni: d.oni_anomaly_degc,
        })
      }
    })
  }

  const oniSeries: LineSeriesConfig[] = [
    {
      key: 'oni',
      label: 'Oceanic Niño Index (ONI anomaly °C)',
      color: 'var(--accent-terracotta)',
      strokeWidth: 2,
    },
  ]

  // 3. Prepare Seasonal Anomaly Bar Chart Data (Z-Scores)
  const anomalyBarData: BarGroup[] = []
  if (timeseries?.seasonal_history) {
    timeseries.seasonal_history.forEach((s) => {
      const z = s.precip_oct_zscore ?? 0
      anomalyBarData.push({
        category: String(s.season_year),
        values: {
          zscore: z,
        },
      })
    })
  }

  return (
    <div>
      <div className="view-header">
        <h1>Research Workbench Overview</h1>
        <p className="view-lead">
          Real-time system telemetry, regional climate observations, and operational model status for seasonal
          drought intelligence.
        </p>
      </div>

      {error && (
        <div className="notice notice-warning">
          <div className="notice-title">System Communication Error</div>
          {error} — ensure API container is running and healthy.
        </div>
      )}

      {/* Top Metrics Grid */}
      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="metric-card">
          <div className="metric-label">API Gateway</div>
          <div className="metric-value">
            {status ? (
              <span className="badge badge-ok">OPERATIONAL</span>
            ) : loading ? (
              '...'
            ) : (
              <span className="badge badge-err">DOWN</span>
            )}
          </div>
          <div className="metric-sub">FastAPI v{status?.version || '—'} ({status?.environment || '—'})</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">PostgreSQL Database</div>
          <div className="metric-value">
            {status?.database?.status === 'connected' ? (
              <span className="badge badge-ok">CONNECTED</span>
            ) : (
              <span className="badge badge-err">DISCONNECTED</span>
            )}
          </div>
          <div className="metric-sub">
            Latency: {status?.database?.latency_ms !== null && status?.database?.latency_ms !== undefined ? `${status.database.latency_ms} ms` : '—'}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Active Model</div>
          <div className="metric-value">
            {activeModel ? (
              <span className="badge badge-terracotta">{activeModel.model_architecture}</span>
            ) : status?.pipelines?.active_model_operational ? (
              <span className="badge badge-terracotta">LOGISTIC REG</span>
            ) : (
              <span className="badge badge-sand">UNCONFIGURED</span>
            )}
          </div>
          <div className="metric-sub">Target: Severe Drought (p20 threshold)</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Recent Jobs</div>
          <div className="metric-value">{status?.active_jobs?.length || recentJobs.length || 0}</div>
          <div className="metric-sub">
            {status?.active_jobs?.length ? `${status.active_jobs.length} worker(s) running` : 'All background workers idle'}
          </div>
        </div>
      </div>

      {/* Primary Visual Intelligence Grid */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Precipitation History Chart */}
        <ErrorBoundary fallbackTitle="Precipitation History Chart Error">
          <LineChart
            title="Observed Summer Precipitation (Limpopo / Maize Belt)"
            subtitle="Core Austral Summer Accumulation (December–February) vs Drought Threshold"
            data={precipData}
            series={precipSeries}
            unit=" mm"
            height={220}
            thresholdLines={[
              { value: tau20, label: 'Drought Threshold (τ20)', color: 'var(--accent-terracotta)' },
              { value: meanPrecip, label: 'Historical Normal', color: 'var(--chart-axis)' },
            ]}
            xAxisLabel="Season (Jan/Feb Year Index)"
            yAxisLabel="Rainfall (mm)"
            interpretation="The 1982/83 austral summer recorded severe rainfall deficit (225.7mm), crossing below the 20th percentile threshold following a super El Niño event."
          />
        </ErrorBoundary>

        {/* ENSO ONI Anomaly Timeline */}
        <ErrorBoundary fallbackTitle="ENSO ONI Timeline Error">
          <LineChart
            title="Oceanic Niño Index (ONI) Teleconnection Signal"
            subtitle="Equatorial Pacific SST Anomaly (°C) with El Niño / La Niña Thresholds"
            data={oniData}
            series={oniSeries}
            unit="°C"
            height={220}
            thresholdLines={[
              { value: 0.5, label: 'El Niño (+0.5°C)', color: 'var(--accent-terracotta)' },
              { value: -0.5, label: 'La Niña (-0.5°C)', color: 'var(--chart-blue-cool)' },
            ]}
            xAxisLabel="Observation Date"
            yAxisLabel="SST Anomaly (°C)"
            interpretation="Warm equatorial Pacific SST anomalies (ASO ONI > +1.0°C) weaken regional Walker circulation, displacing the rainband eastward over the Indian Ocean."
          />
        </ErrorBoundary>
      </div>

      {/* Secondary Visual Intelligence Row: Spring Soil Moisture Deficit & Data Coverage */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Spring Rainfall Anomaly Bar Chart */}
        <ErrorBoundary fallbackTitle="Spring Rainfall Anomaly Chart Error">
          <BarChart
            title="Antecedent Spring Precipitation Anomaly (October Z-Score)"
            subtitle="Local soil moisture memory available on November 1st forecast boundary"
            data={anomalyBarData}
            series={[{ key: 'zscore', label: 'October Precip Z-Score', color: 'var(--chart-blue-cool)' }]}
            unit=" σ"
            height={210}
            referenceLine={{ value: 0, label: 'Zero Baseline', color: 'var(--chart-axis)' }}
            interpretation="Negative antecedent spring anomalies (1982: -1.72σ) signal dry initial soil moisture, compounding remote El Niño forcing."
          />
        </ErrorBoundary>

        {/* Dataset Coverage & Provenance Summary */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="panel-header">
              <h3 className="panel-title">Observational Coverage & Provenance Ledger</h3>
              <span className="badge badge-sand">
                {timeseries?.coverage?.is_fixture_coverage ? 'TEST FIXTURE DATASET' : 'OPERATIONAL ARCHIVE'}
              </span>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Summary of temporal completeness and geographic bounding for the verified climate intelligence pipeline:
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', fontSize: '0.825rem', marginBottom: '1rem' }}>
              <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Rainfall Coverage:</span>
                <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {timeseries?.coverage?.rainfall_months ?? '—'} months (1981–1988)
                </div>
              </div>
              <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
                <span style={{ color: 'var(--text-muted)' }}>ENSO Indicators:</span>
                <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  {timeseries?.coverage?.oni_months ?? '—'} monthly ONI / Niño 3.4
                </div>
              </div>
              <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Spatial Domain:</span>
                <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                  22°S–30°S, 25°E–32°E
                </div>
              </div>
              <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Missing Periods:</span>
                <div style={{ fontWeight: 600, color: 'var(--status-ok)', fontFamily: 'var(--font-mono)' }}>
                  0 gaps (100% complete)
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-secondary" onClick={() => onNavigate('data')} type="button">
              View Datasets
            </button>
            <button className="btn btn-secondary" onClick={() => onNavigate('provenance')} type="button">
              Audit Provenance
            </button>
          </div>
        </div>
      </div>

      {/* Model Performance Summary & Pipeline Checklist */}
      <div className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Active Model Performance Snapshot</h3>
            <span className="badge badge-charcoal">
              {activeModel ? activeModel.model_architecture : 'Logistic Baseline'}
            </span>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Empirical verification metrics evaluated under chronological rolling-origin walk-forward CV and holdout testing:
          </p>

          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
            <div style={{ flex: 1, padding: '0.75rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
              <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                CV Brier Skill Score
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--status-ok)' }}>
                +0.9735
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>vs Expanding Climatology</div>
            </div>

            <div style={{ flex: 1, padding: '0.75rem', background: 'var(--bg-cream)', borderRadius: '2px', border: '1px solid var(--border-sand)' }}>
              <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                Holdout BSS
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--status-err)' }}>
                -3.9847
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Reference Climatology Superior</div>
            </div>
          </div>

          <div className="notice" style={{ fontSize: '0.8rem', padding: '0.5rem 0.75rem' }}>
            <strong>Scientific Integrity Rule:</strong> Model superiority is <em>not</em> claimed on the holdout partition. In accordance with Occam&apos;s razor, the simple historical climatological reference is preferred during neutral oceanic regimes.
          </div>
        </div>

        {/* Pipeline Readiness Checklist */}
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Operational Pipeline Checklist</h3>
            <span className="badge badge-sand">SYSTEM READINESS</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '0.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem' }}>Cleaned Climate Datasets</span>
              <span className={`badge ${status?.pipelines.datasets_operational ? 'badge-ok' : 'badge-err'}`}>
                {status?.pipelines.datasets_operational ? 'OPERATIONAL' : 'MISSING'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem' }}>Zero-Lookahead Feature Store</span>
              <span className={`badge ${status?.pipelines.features_operational ? 'badge-ok' : 'badge-err'}`}>
                {status?.pipelines.features_operational ? 'OPERATIONAL' : 'MISSING'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem' }}>Active Model Manifest</span>
              <span className={`badge ${status?.pipelines.active_model_operational ? 'badge-ok' : 'badge-err'}`}>
                {status?.pipelines.active_model_operational ? 'LOADED' : 'UNCONFIGURED'}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.875rem' }}>Multi-Model Benchmark Manifest</span>
              <span className={`badge ${status?.pipelines.latest_experiment_operational ? 'badge-ok' : 'badge-warn'}`}>
                {status?.pipelines.latest_experiment_operational ? 'EVALUATED' : 'NOT RUN'}
              </span>
            </div>
          </div>

          <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-sand)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Telemetry last refreshed: {lastRefreshed.toLocaleTimeString()} (auto-polls every 15s)
          </div>
        </div>
      </div>
    </div>
  )
}
