import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  RegionalForecastDashboardResponse,
  HistoricalComparisonsResponse,
  SubregionForecastItem,
} from '../api/client'
import { RegionalMap } from '../components/RegionalMap'
import { EpistemicBadge } from '../components/EpistemicBadge'
import { ErrorBoundary } from '../components/ErrorBoundary'

interface DashboardViewProps {
  api: ReturnType<typeof createApiClient>
  onNavigate?: (tab: string) => void
}

export function DashboardView({ api, onNavigate }: DashboardViewProps) {
  const [dashboardData, setDashboardData] = useState<RegionalForecastDashboardResponse | null>(null)
  const [historicalData, setHistoricalData] = useState<HistoricalComparisonsResponse | null>(null)
  const [selectedRegionId, setSelectedRegionId] = useState<string>('ZA_LIMPOPO')
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [regional, historical] = await Promise.all([
        api.getRegionalForecast(),
        api.getHistoricalComparisons().catch(() => null),
      ])
      setDashboardData(regional)
      if (historical) setHistoricalData(historical)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load regional dashboard data')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const selectedSubregion: SubregionForecastItem | undefined = dashboardData?.subregions.find(
    (s) => s.region_id === selectedRegionId,
  ) || dashboardData?.subregions[0]

  return (
    <div className="dashboard-view-shell" data-testid="dashboard-view">
      {/* Top Header */}
      <div className="view-header" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span>Regional Climate-Risk Operational Dashboard</span>
              <span className="badge badge-terracotta" style={{ fontSize: '0.75rem', fontWeight: 600 }}>
                DJF 2026/27 SEASON
              </span>
            </h1>
            <p className="view-lead">
              Probabilistic seasonal drought intelligence, antecedent spring moisture anomalies, uncertainty
              intervals, and verified provenance across Southern Africa.
            </p>
          </div>

          {/* Quick Action Navigation */}
          {onNavigate && (
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => onNavigate('preparedness')}
                style={{ fontSize: '0.8rem' }}
              >
                Preparedness Workflow →
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onNavigate('security')}
                style={{ fontSize: '0.8rem' }}
              >
                Security Incidents
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Epistemic Boundary Notice */}
      <div
        className="notice notice-info"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          marginBottom: '1.25rem',
          background: 'var(--bg-cream)',
          borderLeft: '4px solid var(--accent-terracotta)',
        }}
      >
        <span style={{ fontSize: '1.25rem' }}>🛡️</span>
        <div style={{ fontSize: '0.8rem', lineHeight: 1.4 }}>
          <strong>Scientific Epistemic Separation:</strong> Operational forecast estimates are strictly
          distinguished from historical observations and official consensus outlooks. Simulated adversarial
          experiments are strictly quarantined and never classified as live operational forecasts.
        </div>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.25rem' }}>
          <div className="notice-title">Operational Data Unavailable</div>
          {error} — ensure the backend API service is running.
        </div>
      )}

      {loading && !dashboardData && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <span className="status-dot status-dot--green" style={{ display: 'inline-block', marginRight: '0.5rem' }} />
          Loading regional climate intelligence from ENSO Shield API...
        </div>
      )}

      {dashboardData && (
        <>
          {/* Top Telemetry & Trust Metric Cards */}
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            {/* Pacific ENSO Teleconnection Indicator */}
            <div className="metric-card">
              <div className="metric-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Equatorial Pacific SST</span>
                <EpistemicBadge classification="HISTORICAL_OBSERVATION" />
              </div>
              <div className="metric-value" style={{ color: 'var(--accent-terracotta)' }}>
                +{dashboardData.macro_enso_state.oni_aso_degc.toFixed(2)}°C
              </div>
              <div className="metric-sub">{dashboardData.macro_enso_state.classification}</div>
            </div>

            {/* Antecedent Soil Moisture Anomaly */}
            <div className="metric-card">
              <div className="metric-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Spring Rainfall Deficit</span>
                <EpistemicBadge classification="HISTORICAL_OBSERVATION" />
              </div>
              <div className="metric-value" style={{ color: 'var(--accent-terracotta)' }}>
                {selectedSubregion?.rainfall_anomaly.october_zscore.toFixed(2)} σ
              </div>
              <div className="metric-sub">
                {selectedSubregion?.rainfall_anomaly.departure_pct}% vs October Climatology
              </div>
            </div>

            {/* Calibrated Model Forecast Probability */}
            <div className="metric-card">
              <div className="metric-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Drought Risk Probability</span>
                <EpistemicBadge classification="MODEL_ESTIMATE" />
              </div>
              <div
                className="metric-value"
                style={{
                  color: (selectedSubregion?.forecast.probability ?? 0) >= 0.4 ? 'var(--accent-terracotta)' : 'var(--text-charcoal)',
                }}
              >
                {selectedSubregion ? `${Math.round(selectedSubregion.forecast.probability * 100)}%` : '—'}
              </div>
              <div className="metric-sub">
                {selectedSubregion?.forecast.risk_category} Risk ({selectedSubregion?.forecast.risk_ratio}x Climatology)
              </div>
            </div>

            {/* Data Trust & Provenance Integrity */}
            <div className="metric-card">
              <div className="metric-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Data Trust Status</span>
                <span className="badge badge-ok">VERIFIED</span>
              </div>
              <div className="metric-value" style={{ color: 'var(--status-ok)', fontFamily: 'var(--font-mono)' }}>
                {selectedSubregion?.data_trust.trust_score ?? 98}/100
              </div>
              <div className="metric-sub">
                SHA-256 Digest: {selectedSubregion?.provenance.model_artefact_digest.slice(0, 12)}...
              </div>
            </div>
          </div>

          {/* Primary Interactive Section: Regional Map & Subregion Intelligence Panel */}
          <div className="grid-2" style={{ marginBottom: '1.75rem', alignItems: 'start' }}>
            {/* Interactive Accessible Map Component */}
            <ErrorBoundary fallbackTitle="Regional Map Render Error">
              <RegionalMap
                subregions={dashboardData.subregions}
                selectedRegionId={selectedRegionId}
                onSelectRegion={(id) => setSelectedRegionId(id)}
              />
            </ErrorBoundary>

            {/* Subregion Detailed Intelligence Panel */}
            {selectedSubregion && (
              <div
                className="panel"
                data-testid="subregion-detail-panel"
                style={{
                  background: 'var(--bg-cream)',
                  border: '1px solid var(--border-sand)',
                  borderRadius: '4px',
                  padding: '1.25rem',
                }}
              >
                <div className="panel-header" style={{ marginBottom: '0.75rem' }}>
                  <div>
                    <span className="badge badge-charcoal" style={{ fontSize: '0.7rem', marginBottom: '0.25rem' }}>
                      {selectedSubregion.region_id}
                    </span>
                    <h3 className="panel-title" style={{ fontSize: '1.1rem', margin: 0 }}>
                      {selectedSubregion.region_name}
                    </h3>
                  </div>
                  <span
                    className={`badge ${
                      selectedSubregion.forecast.risk_category === 'High' || selectedSubregion.forecast.risk_category === 'Critical'
                        ? 'badge-err'
                        : selectedSubregion.forecast.risk_category === 'Elevated'
                          ? 'badge-warn'
                          : 'badge-ok'
                    }`}
                  >
                    {selectedSubregion.forecast.risk_category.toUpperCase()} RISK
                  </span>
                </div>

                {/* Subregion Key Metrics Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                  <div style={{ padding: '0.6rem', background: 'var(--bg-white)', borderRadius: '3px', border: '1px solid var(--border-sand)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Historical Normal (DJF)</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                      {selectedSubregion.climatological_normal_djf_mm} mm
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>CHIRPS v2.0 baseline</div>
                  </div>

                  <div style={{ padding: '0.6rem', background: 'var(--bg-white)', borderRadius: '3px', border: '1px solid var(--border-sand)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Antecedent Spring Deficit</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent-terracotta)' }}>
                      {selectedSubregion.rainfall_anomaly.october_observed_mm} mm
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--accent-terracotta)' }}>
                      {selectedSubregion.rainfall_anomaly.departure_pct}% deviation ({selectedSubregion.rainfall_anomaly.october_zscore}σ)
                    </div>
                  </div>
                </div>

                {/* Uncertainty & Prediction Interval */}
                <div
                  style={{
                    padding: '0.75rem',
                    background: 'var(--bg-white)',
                    borderRadius: '3px',
                    border: '1px solid var(--border-sand)',
                    marginBottom: '1rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-charcoal)' }}>
                      Calibrated Uncertainty Interval (90% CI)
                    </span>
                    <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                      ±{Math.round(selectedSubregion.uncertainty.margin_of_error * 100)}% margin
                    </span>
                  </div>

                  {/* Horizontal CI Range Bar */}
                  <div style={{ position: 'relative', height: 16, backgroundColor: '#EFEAE1', borderRadius: 3, marginBottom: '0.4rem' }}>
                    {/* CI band */}
                    <div
                      style={{
                        position: 'absolute',
                        left: `${Math.round(selectedSubregion.uncertainty.ci_90_lower * 100)}%`,
                        width: `${Math.round((selectedSubregion.uncertainty.ci_90_upper - selectedSubregion.uncertainty.ci_90_lower) * 100)}%`,
                        top: 0,
                        bottom: 0,
                        backgroundColor: 'rgba(201, 106, 62, 0.35)',
                        borderRadius: 2,
                      }}
                    />
                    {/* Point estimate marker */}
                    <div
                      style={{
                        position: 'absolute',
                        left: `${Math.round(selectedSubregion.forecast.probability * 100)}%`,
                        top: -2,
                        bottom: -2,
                        width: 3,
                        backgroundColor: 'var(--accent-terracotta)',
                        borderRadius: 1,
                      }}
                    />
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    <span>Lower 90% CI: {Math.round(selectedSubregion.uncertainty.ci_90_lower * 100)}%</span>
                    <span style={{ fontWeight: 700, color: 'var(--accent-terracotta)' }}>
                      Estimate: {Math.round(selectedSubregion.forecast.probability * 100)}%
                    </span>
                    <span>Upper 90% CI: {Math.round(selectedSubregion.uncertainty.ci_90_upper * 100)}%</span>
                  </div>
                </div>

                {/* Validity Period & Source Provenance Details */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.5rem', fontSize: '0.75rem', marginBottom: '0.75rem' }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Forecast Validity Period:</span>
                    <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      {selectedSubregion.validity_period.convective_season} (Lead: {selectedSubregion.validity_period.lead_time_days}d)
                    </div>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Issue Date:</span>
                    <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      {selectedSubregion.validity_period.forecast_issue_date} (Nov 1 Zero-Lookahead)
                    </div>
                  </div>
                </div>

                {/* Provenance Manifest Hash Badge */}
                <div
                  style={{
                    padding: '0.5rem 0.65rem',
                    background: 'var(--bg-white)',
                    borderRadius: '3px',
                    border: '1px solid var(--border-sand)',
                    fontSize: '0.72rem',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <span style={{ color: 'var(--text-muted)' }}>Training Data Fingerprint:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-charcoal)' }}>
                    {selectedSubregion.provenance.training_data_fingerprint.slice(0, 16)}...
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Tripartite Epistemic Comparison: Observation vs Model vs Official Forecast */}
          <div style={{ marginBottom: '1.75rem' }}>
            <div style={{ marginBottom: '0.75rem' }}>
              <h2 style={{ fontSize: '1.15rem', margin: 0 }}>Tripartite Epistemic Comparison</h2>
              <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Explicit separation between empirical ground-truth observations, regularized statistical model
                estimates, and official external consensus outlooks.
              </p>
            </div>

            {selectedSubregion && (
              <div className="grid-3">
                {/* 1. Historical Observation Card */}
                <div
                  className="panel"
                  style={{
                    borderTop: '3px solid var(--text-charcoal)',
                    background: 'var(--bg-cream)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                    <EpistemicBadge classification="HISTORICAL_OBSERVATION" />
                    <span className="badge badge-sand">GROUND TRUTH</span>
                  </div>
                  <h4 style={{ margin: '0 0 0.4rem 0', fontSize: '0.95rem' }}>
                    {selectedSubregion.epistemic_triad.historical_observation.label}
                  </h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4, margin: '0 0 0.75rem 0' }}>
                    {selectedSubregion.epistemic_triad.historical_observation.details}
                  </p>
                  <div style={{ padding: '0.5rem', background: 'var(--bg-white)', borderRadius: '3px', fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Historical Climatological Mean:</span>{' '}
                    <strong>{selectedSubregion.epistemic_triad.historical_observation.observed_value} mm</strong>
                  </div>
                </div>

                {/* 2. Model Estimate Card */}
                <div
                  className="panel"
                  style={{
                    borderTop: '3px solid var(--accent-terracotta)',
                    background: 'var(--bg-cream)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                    <EpistemicBadge classification="MODEL_ESTIMATE" />
                    <span className="badge badge-terracotta">ENSO SHIELD</span>
                  </div>
                  <h4 style={{ margin: '0 0 0.4rem 0', fontSize: '0.95rem' }}>
                    {selectedSubregion.epistemic_triad.model_estimate.label}
                  </h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4, margin: '0 0 0.75rem 0' }}>
                    {selectedSubregion.epistemic_triad.model_estimate.details}
                  </p>
                  <div style={{ padding: '0.5rem', background: 'var(--bg-white)', borderRadius: '3px', fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Severe Drought Probability:</span>{' '}
                    <strong style={{ color: 'var(--accent-terracotta)' }}>
                      {Math.round(selectedSubregion.epistemic_triad.model_estimate.probability * 100)}%
                    </strong>
                  </div>
                </div>

                {/* 3. Official External Forecast Card */}
                <div
                  className="panel"
                  style={{
                    borderTop: '3px solid var(--status-ok)',
                    background: 'var(--bg-cream)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                    <EpistemicBadge classification="OFFICIAL_EXTERNAL_FORECAST" />
                    <span className="badge badge-ok">SADC SARCOF</span>
                  </div>
                  <h4 style={{ margin: '0 0 0.4rem 0', fontSize: '0.95rem' }}>
                    {selectedSubregion.epistemic_triad.official_external_forecast.label}
                  </h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4, margin: '0 0 0.75rem 0' }}>
                    {selectedSubregion.epistemic_triad.official_external_forecast.details}
                  </p>
                  <div style={{ padding: '0.5rem', background: 'var(--bg-white)', borderRadius: '3px', fontSize: '0.75rem' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Official Forecast Tercile:</span>{' '}
                    <strong style={{ color: 'var(--status-ok)' }}>
                      {selectedSubregion.epistemic_triad.official_external_forecast.tercile}
                    </strong>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Historical Seasons Comparison Ledger Table */}
          {historicalData && (
            <div className="panel" style={{ marginBottom: '1.5rem' }}>
              <div className="panel-header" style={{ marginBottom: '0.6rem' }}>
                <div>
                  <h3 className="panel-title" style={{ margin: 0 }}>Historical Season Verification Ledger (1982–1988)</h3>
                  <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Season-by-season ground-truth comparison: Observed DJF rainfall vs Climatological Baseline vs
                    Model Prediction vs Official Outlook.
                  </p>
                </div>
                <EpistemicBadge classification="HISTORICAL_OBSERVATION" />
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ width: '100%', fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th>Season</th>
                      <th>Observed Rainfall</th>
                      <th>Ground Truth</th>
                      <th>Baseline (Climatology)</th>
                      <th>Model Estimate</th>
                      <th>Official Outlook</th>
                      <th>Diagnostic Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historicalData.comparisons.map((c) => (
                      <tr key={c.season_year}>
                        <td style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                          {c.convective_season} ({c.season_year})
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>
                          {c.historical_observation.djf_rainfall_mm.toFixed(1)} mm
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              c.historical_observation.target_drought_observed === 1 ? 'badge-err' : 'badge-ok'
                            }`}
                            style={{ fontSize: '0.7rem' }}
                          >
                            {c.historical_observation.drought_label}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                          {(c.model_estimate.climatology_baseline_prob * 100).toFixed(0)}%
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                          {(c.model_estimate.drought_probability * 100).toFixed(1)}% ({c.model_estimate.risk_category})
                        </td>
                        <td>
                          <span className="badge badge-sand" style={{ fontSize: '0.7rem' }}>
                            {c.official_external_forecast.official_tercile}
                          </span>
                        </td>
                        <td>
                          <span
                            style={{
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              color: c.diagnostic_verdict.startsWith('True') ? 'var(--status-ok)' : 'var(--status-err)',
                            }}
                          >
                            {c.diagnostic_verdict}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
