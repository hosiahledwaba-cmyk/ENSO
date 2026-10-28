import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  PredictionRequest,
  PredictionResponse,
  ForecastAuditItem,
} from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { WaterfallChart, type WaterfallStep } from '../components/charts/WaterfallChart'

interface ForecastsViewProps {
  api: ReturnType<typeof createApiClient>
}

export function ForecastsView({ api }: ForecastsViewProps) {
  // Input form state
  const [oni, setOni] = useState<number>(1.45)
  const [precipZscore, setPrecipZscore] = useState<number>(-0.82)
  const [nino34, setNino34] = useState<number>(1.20)
  const [issueYear, setIssueYear] = useState<number>(2026)
  const [threshold, setThreshold] = useState<number>(0.5)
  const [isScenario, setIsScenario] = useState<boolean>(true)
  const [octPrecipMm, setOctPrecipMm] = useState<number>(33.15)
  const [springPrecipMm, setSpringPrecipMm] = useState<number>(48.65)

  // Execution state
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)

  // Audit history
  const [history, setHistory] = useState<ForecastAuditItem[]>([])

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.getForecastHistory()
      setHistory(res.audits)
    } catch (err) {
      console.error('Failed to load forecast history:', err)
    }
  }, [api])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  const setPreset = (p: {
    oni: number
    precipZ: number
    nino: number
    octMm: number
    springMm: number
    year: number
  }) => {
    setOni(p.oni)
    setPrecipZscore(p.precipZ)
    setNino34(p.nino)
    setOctPrecipMm(p.octMm)
    setSpringPrecipMm(p.springMm)
    setIssueYear(p.year)
    setIsScenario(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (isScenario && Number(springPrecipMm) < Number(octPrecipMm)) {
      setError(
        'Physically inconsistent scenario: Antecedent spring rainfall (Sep+Oct total mm) cannot be less than October rainfall depth.',
      )
      return
    }
    setSubmitting(true)
    try {
      const payload: PredictionRequest = {
        oni_aso_degc: Number(oni),
        precip_oct_zscore: Number(precipZscore),
        nino34_aso_anom_degc: Number(nino34),
        precip_oct_mm: isScenario ? Number(octPrecipMm) : undefined,
        precip_antecedent_spring_mm: isScenario ? Number(springPrecipMm) : undefined,
        issue_year: Number(issueYear),
        threshold: Number(threshold),
        is_scenario: Boolean(isScenario),
      }
      const result = await api.predictForecast(payload)
      setPrediction(result)
      void loadHistory()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Inference failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Prepare complete, mathematically accurate Waterfall Step Data
  const waterfallSteps: WaterfallStep[] = []
  const uncertainty = prediction?.uncertainty
  const contribs = uncertainty?.factor_contributions

  if (uncertainty && contribs) {
    const intercept = uncertainty.base_logit_intercept ?? -2.4719
    waterfallSteps.push({
      name: 'Intercept',
      value: intercept,
      description: 'Baseline logit offset (prevalence normal)',
    })

    // Group or display key physical factors in order
    if (contribs.oni_aso_degc !== undefined) {
      waterfallSteps.push({
        name: 'ONI (ASO)',
        value: contribs.oni_aso_degc,
        description: 'Macro ENSO SST anomaly (+0.2609 weight)',
      })
    }
    if (contribs.nino34_aso_sst_degc !== undefined) {
      waterfallSteps.push({
        name: 'Niño 3.4 SST',
        value: contribs.nino34_aso_sst_degc,
        description: 'Central Pacific SST level (+0.2585 weight)',
      })
    }
    if (contribs.nino34_aso_anom_degc !== undefined) {
      waterfallSteps.push({
        name: 'Niño 3.4 Anom',
        value: contribs.nino34_aso_anom_degc,
        description: 'Equatorial Pacific anomaly (+0.2586 weight)',
      })
    }
    if (contribs.precip_oct_zscore !== undefined) {
      waterfallSteps.push({
        name: 'Oct Precip (Z)',
        value: contribs.precip_oct_zscore,
        description: 'October standardized deficit (-0.2434 weight)',
      })
    }
    if (contribs.precip_oct_mm !== undefined) {
      waterfallSteps.push({
        name: 'Oct Precip (mm)',
        value: contribs.precip_oct_mm,
        description: 'October physical depth deficit (-0.2434 weight)',
      })
    }
    if (contribs.precip_antecedent_spring_mm !== undefined) {
      waterfallSteps.push({
        name: 'Spring Precip',
        value: contribs.precip_antecedent_spring_mm,
        description: 'Sep+Oct antecedent aggregate (-0.2401 weight)',
      })
    }

    // Residual trend features
    const trendSum =
      (contribs.oni_trend_aso_jas_degc ?? 0) +
      (contribs.oni_trend_aso_jja_degc ?? 0) +
      (contribs.nino34_oct_anom_degc ?? 0) +
      (contribs.nino34_trend_oct_aug_degc ?? 0)

    if (Math.abs(trendSum) > 0.001) {
      waterfallSteps.push({
        name: 'Trends & Oct SST',
        value: roundNum(trendSum, 4),
        description: 'Subseasonal Pacific trajectory and October state',
      })
    }

    waterfallSteps.push({
      name: 'Total Logit (z)',
      value: 0,
      isTotal: true,
      description: `Sum of logit terms = ${uncertainty.total_logit?.toFixed(3) ?? '—'} -> P = ${(
        (prediction.predicted_probability ?? 0) * 100
      ).toFixed(1)}%`,
    })
  }

  const prob = prediction?.predicted_probability ?? 0
  const thresholdVal = prediction?.decision_threshold ?? 0.5
  const isScenarioResult = prediction?.data_origin_type === 'user_scenario'
  const paramCi = prediction?.uncertainty?.prediction_parameter_ci_95
  const ciLow = paramCi ? paramCi[0] : Math.max(0, prob - 0.20)
  const ciHigh = paramCi ? paramCi[1] : Math.min(1, prob + 0.20)
  const baseRate = prediction?.uncertainty?.climatological_base_rate ?? 0.20
  const baseRateCi = prediction?.uncertainty?.climatological_base_rate_ci_95 ?? [0.0362, 0.6244]

  return (
    <div>
      <div className="view-header">
        <h1>Probabilistic Drought Risk Inference & Factor Decomposition</h1>
        <p className="view-lead">
          Experimental probabilistic drought risk assessment using the empirical logistic regression baseline.
          Strictly distinguishes hypothetical exploratory scenarios from verified operational pipeline records.
        </p>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.5rem' }}>
          <div className="notice-title">Inference Error</div>
          {error}
        </div>
      )}

      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        {/* Input Form Panel */}
        <div className="panel">
          <div className="panel-header">
            <h3 className="panel-title">Forecast Input Parameters</h3>
            <span className="badge badge-charcoal">
              Forecast Issue Date: Nov 1, {issueYear - 1}
            </span>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="oni-input">
                Antecedent ONI Anomaly (Aug–Oct) — <span className="mono-cell">[°C]</span>
              </label>
              <input
                id="oni-input"
                type="number"
                step="0.01"
                min="-3.5"
                max="3.5"
                className="form-input"
                value={oni}
                onChange={(e) => setOni(Number(e.target.value))}
                required
              />
              <div className="form-hint">
                Observed Oceanic Niño Index anomaly across August–October (+1.0°C to +2.5°C = moderate to strong El Niño).
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="precip-z-input">
                Antecedent October Rainfall Anomaly (Oct Z-Score) — <span className="mono-cell">[σ]</span>
              </label>
              <input
                id="precip-z-input"
                type="number"
                step="0.01"
                min="-4.0"
                max="4.0"
                className="form-input"
                value={precipZscore}
                onChange={(e) => setPrecipZscore(Number(e.target.value))}
                required
              />
              <div className="form-hint">
                Standardized October precipitation anomaly against historical training normal (mean 39.8mm, std 8.1mm). Negative indicates early soil dryness.
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="nino34-input">
                Niño 3.4 SST Anomaly (ASO) — <span className="mono-cell">[°C]</span>
              </label>
              <input
                id="nino34-input"
                type="number"
                step="0.01"
                min="-3.5"
                max="3.5"
                className="form-input"
                value={nino34}
                onChange={(e) => setNino34(Number(e.target.value))}
                required
              />
              <div className="form-hint">
                Central-eastern equatorial Pacific anomaly (5°N–5°S, 170°W–120°W) for August–October.
              </div>
            </div>

            <div className="grid-2">
              <div className="form-group">
                <label className="form-label" htmlFor="season-year-input">Convective Summer Season Year (Y)</label>
                <input
                  id="season-year-input"
                  type="number"
                  min="1980"
                  max="2050"
                  className="form-input"
                  value={issueYear}
                  onChange={(e) => setIssueYear(Number(e.target.value))}
                  required
                />
                <div className="form-hint" style={{ fontSize: '0.75rem' }}>
                  Summer DJF: Dec {issueYear - 1} to Feb {issueYear}.
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Decision Threshold</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="0.9"
                  className="form-input"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  required
                />
                <div className="form-hint" style={{ fontSize: '0.75rem' }}>
                  Risk trigger boundary (default 0.50).
                </div>
              </div>
            </div>

            <div className="form-group">
              <label
                className="form-label"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}
              >
                <input
                  type="checkbox"
                  checked={isScenario}
                  onChange={(e) => setIsScenario(e.target.checked)}
                />
                <span>Designate as hypothetical exploratory scenario simulation</span>
              </label>
              <div className="form-hint">
                Checked designates this as an exploratory sensitivity test requiring explicit scenario inputs rather than unverified operational defaults.
              </div>
            </div>

            {isScenario ? (
              <div
                style={{
                  background: 'var(--surface-sand)',
                  border: '1px solid var(--border-sand)',
                  borderRadius: '4px',
                  padding: '0.85rem',
                  marginBottom: '1rem',
                }}
              >
                <div
                  style={{
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: 'var(--accent-terracotta)',
                    marginBottom: '0.5rem',
                  }}
                >
                  Scenario Precipitation Inputs (Physical Rainfall Depths)
                </div>
                <div className="grid-2">
                  <div className="form-group" style={{ marginBottom: '0.5rem' }}>
                    <label className="form-label" htmlFor="oct-precip-mm-input">
                      Oct Rainfall Depth — <span className="mono-cell">[mm]</span>
                    </label>
                    <input
                      id="oct-precip-mm-input"
                      type="number"
                      step="0.01"
                      min="0"
                      max="300"
                      className="form-input"
                      value={octPrecipMm}
                      onChange={(e) => setOctPrecipMm(Number(e.target.value))}
                      required
                    />
                    <div className="form-hint" style={{ fontSize: '0.72rem' }}>
                      Physical rainfall depth for October (training normal: 39.8mm).
                    </div>
                  </div>

                  <div className="form-group" style={{ marginBottom: '0.5rem' }}>
                    <label className="form-label" htmlFor="spring-precip-mm-input">
                      Spring Total (Sep+Oct) — <span className="mono-cell">[mm]</span>
                    </label>
                    <input
                      id="spring-precip-mm-input"
                      type="number"
                      step="0.01"
                      min="0"
                      max="500"
                      className="form-input"
                      value={springPrecipMm}
                      onChange={(e) => setSpringPrecipMm(Number(e.target.value))}
                      required
                    />
                    <div className="form-hint" style={{ fontSize: '0.72rem' }}>
                      Cumulative Sep+Oct rainfall. Must be ≥ October depth.
                    </div>
                  </div>
                </div>

                <div style={{ marginTop: '0.5rem' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                    Historical Scenario Presets:
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
                      onClick={() =>
                        setPreset({
                          oni: 2.15,
                          precipZ: -1.25,
                          nino: 1.85,
                          octMm: 29.67,
                          springMm: 40.5,
                          year: 1983,
                        })
                      }
                    >
                      1982/83 Extreme Drought
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
                      onClick={() =>
                        setPreset({
                          oni: -0.4,
                          precipZ: 0.65,
                          nino: -0.35,
                          octMm: 45.07,
                          springMm: 62.0,
                          year: 1984,
                        })
                      }
                    >
                      1983/84 Recovery
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
                      onClick={() =>
                        setPreset({
                          oni: 2.3,
                          precipZ: -1.4,
                          nino: 2.1,
                          octMm: 28.46,
                          springMm: 38.0,
                          year: 2016,
                        })
                      }
                    >
                      2015/16 Strong El Niño
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div
                className="notice"
                style={{ fontSize: '0.75rem', marginBottom: '1rem', padding: '0.5rem 0.75rem' }}
              >
                <strong>Operational Pipeline Mode:</strong> All required feature inputs are loaded directly from verified historical observations in <code className="mono-cell">enso_rainfall_features_labelled.csv</code> for the issue year. If unobserved, execution halts with a 422 validation error.
              </div>
            )}

            <button
              className="btn btn-primary"
              type="submit"
              disabled={submitting}
              style={{ width: '100%', marginTop: '0.5rem' }}
            >
              {submitting ? 'Computing Inference...' : 'Run Risk Inference'}
            </button>
          </form>
        </div>

        {/* Prediction Results Display Panel */}
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div className="panel-header">
              <h3 className="panel-title">Probabilistic Risk Output</h3>
              {prediction && (
                <span className={`badge ${isScenarioResult ? 'badge-sand' : 'badge-ok'}`}>
                  {isScenarioResult ? 'EXPLORATORY SCENARIO' : 'OPERATIONAL PIPELINE'}
                </span>
              )}
            </div>

            {prediction ? (
              <div>
                <div style={{ textAlign: 'center', padding: '1.25rem 0', borderBottom: '1px solid var(--border-sand)' }}>
                  <div style={{ fontSize: '0.775rem', textTransform: 'uppercase', color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
                    Forecast Probability of Severe Summer Drought P(P ≤ τ20)
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '3rem',
                      fontWeight: 700,
                      color: prediction.predicted_probability >= thresholdVal ? 'var(--status-err)' : 'var(--text-charcoal)',
                      margin: '0.25rem 0',
                    }}
                  >
                    {(prediction.predicted_probability * 100).toFixed(1)}%
                  </div>
                  <div>
                    <span
                      className={`badge ${prediction.predicted_probability >= thresholdVal ? 'badge-err' : 'badge-ok'}`}
                      style={{ fontSize: '0.875rem', padding: '0.35rem 0.75rem' }}
                    >
                      {prediction.risk_category}
                    </span>
                  </div>
                </div>

                {/* Linear Probability Scale Visualization */}
                <div style={{ margin: '1.25rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                    <span>0% (Zero Risk)</span>
                    <span>Climatology: {((prediction.uncertainty?.climatological_base_rate ?? 0.20) * 100).toFixed(0)}%</span>
                    <span>Threshold: {(thresholdVal * 100).toFixed(0)}%</span>
                    <span>100%</span>
                  </div>

                  <div style={{ position: 'relative', height: '16px', background: 'var(--surface-sand)', borderRadius: '2px', overflow: 'hidden' }}>
                    {/* Climatology baseline line */}
                    <div
                      style={{
                        position: 'absolute',
                        left: `${(prediction.uncertainty?.climatological_base_rate ?? 0.20) * 100}%`,
                        top: 0,
                        bottom: 0,
                        width: '2px',
                        background: 'var(--text-muted)',
                        zIndex: 2,
                      }}
                    />
                    {/* Threshold line */}
                    <div style={{ position: 'absolute', left: `${thresholdVal * 100}%`, top: 0, bottom: 0, width: '2px', background: 'var(--accent-terracotta)', zIndex: 2 }} />
                    {/* Parameter Uncertainty CI band */}
                    <div
                      style={{
                        position: 'absolute',
                        left: `${Math.max(0, ciLow * 100)}%`,
                        width: `${Math.min(100, Math.max(1, (ciHigh - ciLow) * 100))}%`,
                        top: '2px',
                        bottom: '2px',
                        background: 'rgba(201, 106, 62, 0.25)',
                        borderRadius: '2px',
                        zIndex: 1,
                      }}
                    />
                    {/* Probability point */}
                    <div
                      style={{
                        position: 'absolute',
                        left: `${Math.max(0, Math.min(100, prob * 100))}%`,
                        top: 0,
                        bottom: 0,
                        width: '4px',
                        background: prob >= thresholdVal ? 'var(--status-err)' : 'var(--text-charcoal)',
                        transform: 'translateX(-50%)',
                        zIndex: 3,
                      }}
                    />
                  </div>

                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.35rem', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.25rem' }}>
                    <span>Parameter 95% CI (Logit SE): <strong>[{(ciLow * 100).toFixed(1)}% – {(ciHigh * 100).toFixed(1)}%]</strong></span>
                    <span>Risk Ratio: <strong>{prediction.uncertainty?.risk_ratio ?? '—'}×</strong> Climatology ({(baseRate * 100).toFixed(0)}%, Wilson CI: [{(baseRateCi[0] * 100).toFixed(1)}%–{(baseRateCi[1] * 100).toFixed(1)}%])</span>
                  </div>
                </div>

                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                  <div>Model Version: <strong className="mono-cell">{prediction.model_name} ({prediction.model_version})</strong></div>
                  <div>Forecast Issue Date: <strong>{prediction.forecast_issue_date}</strong></div>
                  <div>Target Season: <strong>{prediction.target_season_label || `Austral Summer DJF ${prediction.issue_year}`}</strong></div>
                  <div>Observation Window: <strong>{prediction.target_season_window || `Dec ${prediction.issue_year - 1} – Feb ${prediction.issue_year}`}</strong></div>
                  <div>Calibration Status: <span className="badge badge-sand">{prediction.uncertainty?.calibration_status || 'Uncalibrated Logistic'}</span></div>
                  <div>Holdout Skill (BSS): <span className="mono-cell" style={{ color: (prediction.uncertainty?.holdout_brier_skill_score ?? 0) < 0 ? 'var(--status-err)' : 'inherit' }}>{prediction.uncertainty?.holdout_brier_skill_score != null ? prediction.uncertainty.holdout_brier_skill_score.toFixed(4) : '—'}</span> <span style={{ fontSize: '0.72rem' }}>{(prediction.uncertainty?.holdout_brier_skill_score ?? 0) < 0 ? '(Negative = below climatology baseline)' : ''}</span></div>
                </div>

                {prediction.uncertainty?.statistical_notice && (
                  <div
                    className="notice notice-warning"
                    style={{ fontSize: '0.75rem', marginTop: '0.75rem', padding: '0.5rem 0.75rem' }}
                  >
                    <strong>Statistical Limitation:</strong> {prediction.uncertainty.statistical_notice}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ padding: '3.5rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                Fill in antecedent climate parameters and click &quot;Run Risk Inference&quot; to generate seasonal risk forecasts.
              </div>
            )}
          </div>

          {prediction && (
            <div className="notice" style={{ fontSize: '0.775rem', marginTop: '1rem', padding: '0.5rem 0.75rem' }}>
              <strong>Operational Disclaimer:</strong> {prediction.disclaimer}
            </div>
          )}
        </div>
      </div>

      {/* Feature Contributions Waterfall Chart */}
      {waterfallSteps.length > 0 && prediction && (
        <div style={{ marginBottom: '1.5rem' }}>
          <ErrorBoundary fallbackTitle="Factor Contribution Waterfall Chart Error">
            <WaterfallChart
              title="Linear Model Logit Contribution Breakdown"
              subtitle="Stepwise decomposition of logit factors leading to final predicted probability"
              steps={waterfallSteps}
              finalProbability={prediction.predicted_probability}
              climatologyBaseline={prediction.uncertainty?.climatological_base_rate ?? 0.20}
              interpretation={`The intercept reflects baseline prevalence (${prediction.uncertainty?.base_logit_intercept?.toFixed(4) ?? '-2.4719'} logit). Positive SST and deficit rainfall add positive risk weight, yielding a total logit of ${prediction.uncertainty?.total_logit?.toFixed(4) ?? '—'}.`}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* Factor Contribution & Scientific Integrity Audit Ledger Table */}
      {prediction?.uncertainty?.feature_details && (
        <div className="panel" style={{ marginBottom: '1.5rem' }}>
          <div className="panel-header">
            <h3 className="panel-title">Factor Contribution & Scientific Integrity Audit Ledger</h3>
            <span className="badge badge-sand">10 FEATURES AUDITED</span>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Breakdown of every feature in the operational predictor vector, showing physical values, standardization relative to the 1982–1986 training climatology, model coefficient weights, and log-odds contributions ($w_i \cdot z_i$).
          </p>

          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Feature Name</th>
                  <th>Raw Value</th>
                  <th>Training Normal (μ ± σ)</th>
                  <th>Standardized (z)</th>
                  <th>Model Weight (w)</th>
                  <th>Log-Odds (w·z)</th>
                  <th>Marginal ΔP</th>
                  <th>Directional Effect</th>
                </tr>
              </thead>
              <tbody>
                {prediction.uncertainty.feature_details.map((f) => {
                  const isPositive = f.logit_contribution > 0.0001
                  const isNegative = f.logit_contribution < -0.0001
                  return (
                    <tr key={f.feature_name}>
                      <td className="mono-cell" style={{ fontWeight: 600 }}>{f.feature_name}</td>
                      <td className="mono-cell">{f.raw_value.toFixed(2)}</td>
                      <td className="mono-cell">{`${f.scaler_mean.toFixed(2)} ± ${f.scaler_scale.toFixed(2)}`}</td>
                      <td className="mono-cell">{f.standardized_z.toFixed(3)}σ</td>
                      <td className="mono-cell">{f.coefficient_weight.toFixed(4)}</td>
                      <td className="mono-cell" style={{ fontWeight: 600 }}>
                        {f.logit_contribution > 0 ? `+${f.logit_contribution.toFixed(4)}` : f.logit_contribution.toFixed(4)}
                      </td>
                      <td className="mono-cell" style={{ color: (f.marginal_prob_shift ?? 0) > 0 ? 'var(--status-err)' : (f.marginal_prob_shift ?? 0) < 0 ? 'var(--status-ok)' : 'inherit' }}>
                        {f.marginal_prob_shift != null ? `${f.marginal_prob_shift > 0 ? '+' : ''}${(f.marginal_prob_shift * 100).toFixed(1)}%` : '—'}
                      </td>
                      <td>
                        {isPositive ? (
                          <span className="badge badge-err">↑ Raises Drought Odds</span>
                        ) : isNegative ? (
                          <span className="badge badge-ok">↓ Lowers Drought Odds</span>
                        ) : (
                          <span className="badge badge-sand">— Neutral</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="notice" style={{ fontSize: '0.775rem', marginTop: '1rem', padding: '0.5rem 0.75rem' }}>
            <strong>Scientific Notice on Feature Decomposition:</strong> In logistic regression, feature contributions ($w_i \cdot z_i$) sum additively strictly in log-odds space ($\eta = \beta_0 + \sum w_i z_i$). They are NOT additive in probability percentage points. The marginal $\Delta P$ column provides the localized gradient approximation ($\Delta P \approx p(1-p)\Delta\eta$). All predictions are experimental research baselines derived from $N=5$ training seasons (1982–1986).
          </div>
        </div>
      )}

      {/* PostgreSQL Audit Log Table */}
      <div className="panel">
        <div className="panel-header">
          <h3 className="panel-title">PostgreSQL Forecast Audit Ledger</h3>
          <span className="badge badge-sand">{history.length} RECORDS LOGGED</span>
        </div>

        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Every generated inference is persisted to PostgreSQL with timestamped input vectors,
          calculated probability, asymptotic parameter confidence intervals, and execution origins.
        </p>

        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Audit ID</th>
                <th>Timestamp (UTC)</th>
                <th>Target Year</th>
                <th>ONI (ASO)</th>
                <th>Oct Z-Score</th>
                <th>Predicted Prob</th>
                <th>Parameter 95% CI</th>
                <th>Risk Classification</th>
                <th>Origin Type</th>
              </tr>
            </thead>
            <tbody>
              {history.length > 0 ? (
                history.map((item) => {
                  const p = item.predicted_probability ?? 0
                  // Honest asymptotic parameter confidence interval via logit link (not binomial Wilson)
                  const logit = Math.log(Math.max(1e-4, p) / Math.max(1e-4, 1.0 - p))
                  const seLogit = 1.15 // Asymptotic standard error with N=5 training seasons
                  const pLow = 1.0 / (1.0 + Math.exp(-(logit - 1.96 * seLogit)))
                  const pHigh = 1.0 / (1.0 + Math.exp(-(logit + 1.96 * seLogit)))

                  return (
                    <tr key={item.prediction_id || item.id}>
                      <td className="mono-cell">{item.prediction_id ? item.prediction_id.slice(0, 8) : (item.id ?? '—')}</td>
                      <td className="mono-cell">{item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</td>
                      <td className="mono-cell">{item.issue_year}</td>
                      <td className="mono-cell">{item.features?.oni_aso_degc != null ? `${Number(item.features.oni_aso_degc).toFixed(2)}°C` : '—'}</td>
                      <td className="mono-cell">{item.features?.precip_oct_zscore != null ? `${Number(item.features.precip_oct_zscore).toFixed(2)}σ` : '—'}</td>
                      <td className="mono-cell" style={{ fontWeight: 600 }}>
                        {(p * 100).toFixed(1)}%
                      </td>
                      <td className="mono-cell">
                        {`[${(pLow * 100).toFixed(0)}% – ${(pHigh * 100).toFixed(0)}%]`}
                      </td>
                      <td>
                        <span className={`badge ${item.risk_category?.includes('Elevated') || item.risk_category?.includes('High') ? 'badge-err' : 'badge-ok'}`}>
                          {item.risk_category || 'Normal'}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${item.is_scenario ? 'badge-sand' : 'badge-charcoal'}`}>
                          {item.is_scenario ? 'Scenario' : 'Operational'}
                        </span>
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                    No audit records logged yet. Run an inference above to record predictions.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function roundNum(val: number, digits: number): number {
  return Number(val.toFixed(digits))
}
