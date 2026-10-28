import { useState, useEffect, useCallback } from 'react'
import type { createApiClient, FeaturesStatusResponse, JobRecord, DatasetTimeseriesResponse } from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { LineChart, type LineDataPoint, type LineSeriesConfig } from '../components/charts/LineChart'

interface FeaturesViewProps {
  api: ReturnType<typeof createApiClient>
}

export function FeaturesView({ api }: FeaturesViewProps) {
  const [status, setStatus] = useState<FeaturesStatusResponse | null>(null)
  const [timeseries, setTimeseries] = useState<DatasetTimeseriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [includeLag1, setIncludeLag1] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [currentJob, setCurrentJob] = useState<JobRecord | null>(null)

  const loadFeatures = useCallback(async () => {
    setLoading(true)
    try {
      const [resStatus, resTs] = await Promise.all([
        api.getFeaturesStatus().catch(() => null),
        api.getDatasetTimeseries().catch(() => null),
      ])
      if (resStatus) setStatus(resStatus)
      if (resTs) setTimeseries(resTs)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load feature store status')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadFeatures()
  }, [loadFeatures])

  // Poll current job
  useEffect(() => {
    if (!currentJob || currentJob.status === 'completed' || currentJob.status === 'failed') {
      return
    }
    const timer = setInterval(async () => {
      try {
        const updated = await api.getJob(currentJob.job_id)
        setCurrentJob(updated)
        if (updated.status === 'completed') {
          void loadFeatures()
        }
      } catch (err) {
        console.error('Feature job polling error:', err)
      }
    }, 1500)
    return () => clearInterval(timer)
  }, [api, currentJob, loadFeatures])

  const handleStartFeatures = async () => {
    try {
      setSubmitting(true)
      const res = await api.startFeaturesJob({ include_lag1: includeLag1 })
      const initialJob = await api.getJob(res.job_id)
      setCurrentJob(initialJob)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to launch feature engineering job')
    } finally {
      setSubmitting(false)
    }
  }

  // Antecedent ENSO vs Seasonal Rainfall Target Data
  const ensoVsPrecipData: LineDataPoint[] = []
  const tau20 = timeseries?.reference_distribution?.tau_drought_p20_mm ?? 255.64

  if (timeseries?.seasonal_history) {
    timeseries.seasonal_history.forEach((s) => {
      ensoVsPrecipData.push({
        x: s.season_year,
        oni_aso: s.oni_aso_degc ?? 0,
        precip_djf: s.seasonal_precip_djf_mm ?? 0,
      })
    })
  }

  const ensoPrecipSeries: LineSeriesConfig[] = [
    { key: 'precip_djf', label: 'DJF Seasonal Rainfall (mm)', color: 'var(--chart-primary)', strokeWidth: 2.25 },
  ]

  const featureDefinitions = [
    { name: 'oni_aso_degc', type: 'Float (°C)', role: 'Predictor', description: '3-month running mean Oceanic Niño Index (August–October antecedent SST anomaly)' },
    { name: 'oni_trend_aso_jas_degc', type: 'Float (°C)', role: 'Predictor', description: 'Short-term ENSO acceleration: ONI(ASO) - ONI(JAS)' },
    { name: 'nino34_aso_anom_degc', type: 'Float (°C)', role: 'Predictor', description: 'Niño 3.4 index ASO anomaly (5°N–5°S, 170°W–120°W)' },
    { name: 'precip_oct_mm', type: 'Float (mm)', role: 'Predictor', description: 'October total rainfall: antecedent local soil-moisture proxy before accumulation onset' },
    { name: 'precip_oct_zscore', type: 'Float (σ)', role: 'Predictor', description: 'Standardized October rainfall anomaly evaluated against training-only reference distribution' },
    { name: 'target_drought_p20', type: 'Binary {0,1}', role: 'Target', description: 'Drought event indicator: 1 if seasonal DJF rainfall ≤ τ20 (255.6 mm), 0 otherwise' },
    { name: 'target_below_normal_p33', type: 'Binary {0,1}', role: 'Target', description: 'Tercile below-normal indicator: 1 if seasonal DJF rainfall ≤ τ33 (298.2 mm), 0 otherwise' },
  ]

  return (
    <div>
      <div className="view-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Feature Engineering & Climatological Reference Baseline</h1>
          <p className="view-lead">
            Strict zero-lookahead feature extraction and target labelling frozen on the training reference
            distribution (RD-001 &amp; RD-002).
          </p>
        </div>
        <button className="btn btn-secondary" onClick={() => void loadFeatures()} disabled={loading} type="button">
          Refresh Store
        </button>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.5rem' }}>
          <div className="notice-title">Error Loading Features</div>
          {error}
        </div>
      )}

      {/* Top Metrics Grid */}
      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="metric-card">
          <div className="metric-label">Feature Store</div>
          <div className="metric-value">
            {status?.exists ? (
              <span className="badge badge-ok">AVAILABLE</span>
            ) : (
              <span className="badge badge-warn">MISSING</span>
            )}
          </div>
          <div className="metric-sub">{status?.features_csv || 'data/features/enso_rainfall_features_labelled.csv'}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Row Count</div>
          <div className="metric-value">{status?.row_count ?? timeseries?.seasonal_history.length ?? 0} seasons</div>
          <div className="metric-sub">Partitioned 1982–1988</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Predictors</div>
          <div className="metric-value">{status?.feature_count ?? 10} features</div>
          <div className="metric-sub">Zero-lookahead ENSO &amp; soil moisture</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Forecast Boundary</div>
          <div className="metric-value">Nov 1 (Y-1)</div>
          <div className="metric-sub">30-day operational lead to Dec 1</div>
        </div>
      </div>

      {/* Visual Intelligence: Relationship Between Antecedent Predictors and Target */}
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        <ErrorBoundary fallbackTitle="ENSO vs Rainfall Target Chart Error">
          <LineChart
            title="Austral Summer Rainfall vs Drought Percentile (τ20)"
            subtitle="Observed DJF Accumulation with Frozen Training Drought Threshold (255.6 mm)"
            data={ensoVsPrecipData}
            series={ensoPrecipSeries}
            unit=" mm"
            height={220}
            thresholdLines={[
              { value: tau20, label: 'Drought Cutoff (τ20: 255.6 mm)', color: 'var(--accent-terracotta)' },
            ]}
            xAxisLabel="Season Year"
            yAxisLabel="Seasonal Rainfall (mm)"
            interpretation="Physical teleconnection: Warm Pacific anomalies precede severe DJF rainfall deficits (e.g. 1983: 225.7 mm, below τ20). Correlation does not guarantee causation."
          />
        </ErrorBoundary>

        {/* Operational Timeline & Zero-Lookahead Architecture */}
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Zero-Lookahead Temporal Alignment</h3>
            <span className="badge badge-charcoal">PROTOCOL ENFORCED</span>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
            Strict chronology guarantees zero future data leakage into simulated historical forecasts:
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginBottom: '1rem', fontSize: '0.825rem' }}>
            <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
              <strong style={{ color: 'var(--accent-terracotta)' }}>1. Predictor Window (Aug–Oct):</strong>
              <div style={{ color: 'var(--text-muted)' }}>Oceanic Niño Index (ASO) and October monthly rainfall collected and validated.</div>
            </div>

            <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', border: '1px solid var(--accent-terracotta)', borderRadius: '2px' }}>
              <strong style={{ color: 'var(--text-charcoal)' }}>2. Forecast Issue Boundary (November 1st):</strong>
              <div style={{ color: 'var(--text-muted)' }}>
                Feature vector x_Y is frozen. No observations post-dating Nov 1st are accessible to the model.
              </div>
            </div>

            <div style={{ padding: '0.5rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
              <strong style={{ color: 'var(--chart-blue-cool)' }}>3. Target Accumulation Period (Dec 1 – Feb 28):</strong>
              <div style={{ color: 'var(--text-muted)' }}>
                Austral summer rainfall P_Y = Dec(Y-1) + Jan(Y) + Feb(Y) is accumulated to evaluate prediction.
              </div>
            </div>

          </div>

          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Reference Parameters: Mean = {timeseries?.reference_distribution?.mean_seasonal_precip_mm?.toFixed(1) ?? '322.9'} mm,
            Std = {timeseries?.reference_distribution?.std_seasonal_precip_mm?.toFixed(1) ?? '55.8'} mm,
            τ20 = {timeseries?.reference_distribution?.tau_drought_p20_mm?.toFixed(1) ?? '255.6'} mm.
          </div>
        </div>
      </div>

      {/* Feature Catalog Table */}
      <div className="panel" style={{ marginBottom: '1.5rem' }}>
        <div className="panel-header">
          <h3 className="panel-title">Extracted Predictor Schema &amp; Data Dictionary</h3>
          <span className="badge badge-sand">10 FEATURES</span>
        </div>

        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Feature Column</th>
                <th>Data Type</th>
                <th>Role</th>
                <th>Scientific Definition</th>
              </tr>
            </thead>
            <tbody>
              {featureDefinitions.map((feat) => (
                <tr key={feat.name}>
                  <td className="mono-cell"><strong>{feat.name}</strong></td>
                  <td className="mono-cell">{feat.type}</td>
                  <td>
                    <span className={`badge ${feat.role === 'Predictor' ? 'badge-charcoal' : 'badge-terracotta'}`}>
                      {feat.role}
                    </span>
                  </td>
                  <td>{feat.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Feature Pipeline Execution Launcher */}
      <div className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Execute Feature Pipeline</h3>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Applies zero-lookahead feature engineering rules to cleaned datasets, computes training-only
            climatological distributions ($\mu, \sigma, \tau_{20}, \tau_{33}$), and outputs labelled datasets.
          </p>

          <div className="form-group">
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={includeLag1}
                onChange={(e) => setIncludeLag1(e.target.checked)}
              />
              <span>Include Lag-1 previous season rainfall feature (`precip_djf_lag1_mm`)</span>
            </label>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => void handleStartFeatures()}
            disabled={submitting || (currentJob !== null && currentJob.status === 'running')}
            type="button"
          >
            {submitting || currentJob?.status === 'running' ? 'Generating Features...' : 'Run Feature Pipeline'}
          </button>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Feature Pipeline Logs</h3>
            {currentJob && (
              <span className={`badge ${currentJob.status === 'completed' ? 'badge-ok' : currentJob.status === 'failed' ? 'badge-err' : 'badge-warn'}`}>
                {currentJob.status.toUpperCase()}
              </span>
            )}
          </div>

          {currentJob ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                <span>Job: <strong className="mono-cell">{currentJob.job_id}</strong></span>
                <span>Duration: <strong>{typeof currentJob.duration_seconds === 'number' ? `${currentJob.duration_seconds.toFixed(2)}s` : 'running...'}</strong></span>
              </div>
              <div className="terminal-output">
                {currentJob.logs || 'Awaiting feature pipeline worker output...\n'}
              </div>
            </div>
          ) : (
            <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              No active feature execution. Click &quot;Run Feature Pipeline&quot; to re-extract features.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
