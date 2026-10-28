import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  SystemStatus,
  JobRecord,
  SimulationReportItem,
  SimulationScenarioResultItem,
  SimulationScenarioMetadata,
  DefensiveInspectionReportItem,
  SimulationConfigItem,
} from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'

interface DiagnosticsViewProps {
  api: ReturnType<typeof createApiClient>
  apiBaseUrl: string
}

type SubTab = 'defense' | 'system'

export function DiagnosticsView({ api, apiBaseUrl }: DiagnosticsViewProps) {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('defense')

  // System Diagnostics State
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [jobs, setJobs] = useState<JobRecord[]>([])
  const [selectedJob, setSelectedJob] = useState<JobRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Defense & Simulation State
  const [scenarios, setScenarios] = useState<SimulationScenarioMetadata[]>([])
  const [benchmarkReport, setBenchmarkReport] = useState<SimulationReportItem | null>(null)
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>('ADVERSARIAL_FDI')
  const [simSeed, setSimSeed] = useState<number>(42)
  const [simMagnitude, setSimMagnitude] = useState<number>(1.0)
  const [simRatio, setSimRatio] = useState<number>(0.35)
  const [simulating, setSimulating] = useState(false)
  const [simulationResult, setSimulationResult] = useState<SimulationScenarioResultItem | null>(null)

  // Live Telemetry Inspector State
  const [inspecting, setInspecting] = useState(false)
  const [inspectReport, setInspectReport] = useState<DefensiveInspectionReportItem | null>(null)
  const [testPayloadType, setTestPayloadType] = useState<string>('sentinel')

  const loadData = useCallback(async () => {
    try {
      setError(null)
      const [sysStatus, jobsData, scenariosData, benchmarks] = await Promise.all([
        api.getSystemStatus(),
        api.getJobs(),
        api.getDefenseScenarios().catch(() => ({ scenarios: [], total_scenarios: 0, protocol_reference: '' })),
        api.getDefenseBenchmarks().catch(() => null),
      ])
      setStatus(sysStatus)
      setJobs(jobsData.jobs)
      setScenarios(scenariosData.scenarios)
      setBenchmarkReport(benchmarks)

      if (benchmarks && benchmarks.scenarios.length > 0) {
        const defaultResult = benchmarks.scenarios.find((s) => s.scenario === 'ADVERSARIAL_FDI') || benchmarks.scenarios[0]
        setSimulationResult(defaultResult)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Diagnostics query failed')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleRunSimulation = async () => {
    setSimulating(true)
    setError(null)
    try {
      const res = await api.simulateDefenseScenario({
        scenario: selectedScenarioId as SimulationConfigItem['scenario'],
        seed: simSeed,
        perturbation_magnitude: simMagnitude,
        injection_ratio: simRatio,
        target_feature: 'oni_aso_degc',
      })
      setSimulationResult(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Simulation run failed')
    } finally {
      setSimulating(false)
    }
  }

  const handleRunInspection = async (type: string) => {
    setInspecting(true)
    setTestPayloadType(type)
    setError(null)
    try {
      let records: Array<Record<string, unknown>> = []
      if (type === 'clean') {
        records = [
          { date: '2024-08', sst_degc: 26.8, oni_anomaly_degc: 0.1, precip_mm: 30.5 },
          { date: '2024-09', sst_degc: 26.6, oni_anomaly_degc: 0.2, precip_mm: 45.0 },
          { date: '2024-10', sst_degc: 26.5, oni_anomaly_degc: 0.3, precip_mm: 88.0 },
        ]
      } else if (type === 'sentinel') {
        records = [
          { date: '2024-08', sst_degc: 26.8, oni_anomaly_degc: 0.1, precip_mm: 30.5 },
          { date: '2024-09', sst_degc: -999.0, oni_anomaly_degc: -999.0, precip_mm: 999.9 },
        ]
      } else if (type === 'jump') {
        records = [
          { date: '2024-08', sst_degc: 26.5, oni_anomaly_degc: 0.2, precip_mm: 40.0 },
          { date: '2024-09', sst_degc: 31.8, oni_anomaly_degc: 2.1, precip_mm: 42.0 },
        ]
      } else if (type === 'freeze') {
        records = [
          { date: '2024-07', sst_degc: 27.123, oni_anomaly_degc: 0.45 },
          { date: '2024-08', sst_degc: 27.123, oni_anomaly_degc: 0.45 },
          { date: '2024-09', sst_degc: 27.123, oni_anomaly_degc: 0.45 },
          { date: '2024-10', sst_degc: 27.123, oni_anomaly_degc: 0.45 },
        ]
      } else if (type === 'impossible') {
        records = [
          { date: '2024-10', sst_degc: 48.5, oni_anomaly_degc: 6.2, precip_mm: -35.0 },
        ]
      }

      const res = await api.inspectDefenseTelemetry(`live_test_${type}`, records)
      setInspectReport(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Telemetry inspection failed')
    } finally {
      setInspecting(false)
    }
  }

  const swaggerUrl = `${apiBaseUrl.replace(/\/+$/, '')}/docs`
  const openApiUrl = `${apiBaseUrl.replace(/\/+$/, '')}/openapi.json`

  const pipelineStages = [
    {
      step: '01',
      name: 'Climate Ingestion & Provenance',
      module: 'ml.data',
      status: status?.pipelines.datasets_operational ? 'OPERATIONAL' : 'MISSING',
      details: 'CHIRPS, NOAA ONI, NOAA Niño 3.4 · SHA-256 Verified',
    },
    {
      step: '02',
      name: 'Zero-Lookahead Features',
      module: 'ml.features',
      status: status?.pipelines.features_operational ? 'OPERATIONAL' : 'MISSING',
      details: 'Nov 1 issue boundary, τ20 reference distribution',
    },
    {
      step: '03',
      name: 'Defensive Anomaly Screening',
      module: 'ml.defense',
      status: 'OPERATIONAL',
      details: '6 Transparent checks + Multivariate baseline envelope',
    },
    {
      step: '04',
      name: 'Operational ML & Benchmarks',
      module: 'ml.training & inference',
      status: status?.pipelines.active_model_operational ? 'LOADED' : 'UNCONFIGURED',
      details: 'Regularized L2 Logistic Regression, walk-forward CV',
    },
  ]

  return (
    <div>
      <div className="view-header">
        <h1>Defensive Telemetry Intelligence & System Diagnostics</h1>
        <p className="view-lead">
          Screen climate observations for impossible values, rate-of-change violations, frozen telemetry,
          and stealthy False Data Injection (FDI) attacks. Controlled perturbation simulations evaluate
          detection latency and forecast resilience.
        </p>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.5rem' }}>
          <div className="notice-title">Diagnostic Warning</div>
          {error}
        </div>
      )}

      {/* Sub-navigation tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-sand)', paddingBottom: '0.5rem' }}>
        <button
          className={`btn ${activeSubTab === 'defense' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('defense')}
          type="button"
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <span>Defensive Anomaly Screening & FDI Simulation</span>
          <span className="badge badge-sand" style={{ fontSize: '0.65rem' }}>SEC-HARNESS</span>
        </button>
        <button
          className={`btn ${activeSubTab === 'system' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('system')}
          type="button"
          style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
        >
          <span>Container Telemetry & Jobs</span>
          <span className="badge badge-charcoal" style={{ fontSize: '0.65rem' }}>INFRA</span>
        </button>
      </div>

      {activeSubTab === 'defense' && (
        <div>
          {/* Epistemic Protocol Guarantee Notice */}
          <div className="notice notice-info" style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--accent-terracotta)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
              <div className="notice-title" style={{ color: 'var(--accent-terracotta)', fontWeight: 700 }}>
                Protocol §4 & RD-014: Non-Malicious Epistemic Guardrail
              </div>
              <span className="badge badge-ok">CONTROLLED ISOLATION</span>
            </div>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-charcoal)', lineHeight: 1.5 }}>
              Ordinary anomalies (stochastic sensor flutter, missing records, out-of-range readings) are <strong>never</strong> treated
              as confirmed malicious activity (<code>is_confirmed_malicious = false</code>). Classification is strictly calibrated:
              <span className="badge badge-sand" style={{ margin: '0 0.3rem' }}>MEASUREMENT_NOISE</span>
              <span className="badge badge-sand" style={{ margin: '0 0.3rem' }}>DATA_QUALITY_ANOMALY</span>
              <span className="badge badge-warn" style={{ margin: '0 0.3rem' }}>SUSPICIOUS_ANOMALY</span>
              <span className="badge badge-err" style={{ margin: '0 0.3rem' }}>POTENTIAL_ADVERSARIAL_PERTURBATION</span>.
              Simulations run entirely in isolated memory, decoupled from real ingestion credentials.
            </p>
          </div>

          {/* Benchmark Overview Cards */}
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            <div className="card stat-card" style={{ padding: '1rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)' }}>
              <div className="stat-label">Attack Detection Rate (ADR)</div>
              <div className="stat-value" style={{ color: 'var(--accent-terracotta)', fontSize: '1.8rem' }}>
                {benchmarkReport ? `${(benchmarkReport.mean_attack_detection_rate * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="stat-desc">Mean sensitivity across 5 attack scenarios</div>
            </div>

            <div className="card stat-card" style={{ padding: '1rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)' }}>
              <div className="stat-label">False Positive Rate (FPR)</div>
              <div className="stat-value" style={{ color: '#2E7D32', fontSize: '1.8rem' }}>
                {benchmarkReport ? `${(benchmarkReport.mean_false_positive_rate * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="stat-desc">Zero false alarms on clean reference data</div>
            </div>

            <div className="card stat-card" style={{ padding: '1rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)' }}>
              <div className="stat-label">Mean Detection Delay</div>
              <div className="stat-value" style={{ color: 'var(--text-charcoal)', fontSize: '1.8rem' }}>
                {simulationResult ? `${simulationResult.detection_delay_timesteps.toFixed(1)} steps` : '0.0 steps'}
              </div>
              <div className="stat-desc">Timesteps before first alert activation</div>
            </div>

            <div className="card stat-card" style={{ padding: '1rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)' }}>
              <div className="stat-label">Recovery Efficiency (RE)</div>
              <div className="stat-value" style={{ color: '#C96A3E', fontSize: '1.8rem' }}>
                {benchmarkReport ? `${(benchmarkReport.mean_recovery_efficiency * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="stat-desc">Defensive forecast error restoration</div>
            </div>
          </div>

          {/* Controlled Simulation Harness Section */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header">
              <h3 className="panel-title">Controlled Perturbation Simulation Harness</h3>
              <span className="badge badge-charcoal">DETERMINISTIC EVALUATION</span>
            </div>

            {/* Scenario Selection Pills */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
              {scenarios.map((sc) => (
                <button
                  key={sc.id}
                  type="button"
                  onClick={() => setSelectedScenarioId(sc.id)}
                  style={{
                    padding: '0.4rem 0.8rem',
                    borderRadius: '3px',
                    border: '1px solid',
                    borderColor: selectedScenarioId === sc.id ? 'var(--accent-terracotta)' : 'var(--border-sand)',
                    background: selectedScenarioId === sc.id ? 'var(--accent-terracotta)' : 'var(--bg-cream)',
                    color: selectedScenarioId === sc.id ? '#ffffff' : 'var(--text-charcoal)',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {sc.name}
                </button>
              ))}
            </div>

            {/* Scenario Description & Controls */}
            {scenarios.length > 0 && (
              <div style={{ background: 'var(--bg-cream)', padding: '0.9rem', borderRadius: '3px', border: '1px solid var(--border-sand)', marginBottom: '1rem' }}>
                {(() => {
                  const currentSc = scenarios.find((s) => s.id === selectedScenarioId)
                  return currentSc ? (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.3rem' }}>
                        <strong style={{ fontSize: '0.9rem', color: 'var(--text-charcoal)' }}>{currentSc.name}</strong>
                        <span className="badge badge-sand">{currentSc.threat_model_ref}</span>
                      </div>
                      <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', color: 'var(--text-dim)' }}>
                        {currentSc.description}
                      </p>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', alignItems: 'center' }}>
                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                            Random Seed (Reproducibility):
                          </label>
                          <input
                            type="number"
                            value={simSeed}
                            onChange={(e) => setSimSeed(parseInt(e.target.value, 10) || 42)}
                            style={{ width: '100%', padding: '0.3rem 0.5rem', border: '1px solid var(--border-sand)', borderRadius: '2px' }}
                          />
                        </div>

                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                            Perturbation Magnitude (σ):
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            value={simMagnitude}
                            onChange={(e) => setSimMagnitude(parseFloat(e.target.value) || 1.0)}
                            style={{ width: '100%', padding: '0.3rem 0.5rem', border: '1px solid var(--border-sand)', borderRadius: '2px' }}
                          />
                        </div>

                        <div>
                          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.2rem' }}>
                            Injection Ratio:
                          </label>
                          <input
                            type="number"
                            step="0.05"
                            min="0.1"
                            max="0.8"
                            value={simRatio}
                            onChange={(e) => setSimRatio(parseFloat(e.target.value) || 0.35)}
                            style={{ width: '100%', padding: '0.3rem 0.5rem', border: '1px solid var(--border-sand)', borderRadius: '2px' }}
                          />
                        </div>

                        <div style={{ alignSelf: 'flex-end' }}>
                          <button
                            className="btn btn-primary"
                            onClick={handleRunSimulation}
                            disabled={simulating}
                            type="button"
                            style={{ width: '100%' }}
                          >
                            {simulating ? 'Simulating...' : 'Execute Simulation Run'}
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : null
                })()}
              </div>
            )}

            {/* Simulation Results Display */}
            {simulationResult && (
              <div style={{ borderTop: '1px solid var(--border-sand)', paddingTop: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <h4 style={{ margin: 0, fontSize: '0.95rem' }}>
                    Empirical Evaluation: <code>{simulationResult.scenario}</code> (Seed={simulationResult.seed})
                  </h4>
                  <span className="badge badge-ok">ISOLATED MEMORY RUN</span>
                </div>

                <div className="grid-4" style={{ marginBottom: '1rem' }}>
                  <div style={{ padding: '0.75rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Attack Detection (ADR)</div>
                    <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent-terracotta)' }}>
                      {(simulationResult.attack_detection_rate * 100).toFixed(1)}%
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                      {simulationResult.detected_samples} / {simulationResult.injected_samples} injections caught
                    </div>
                  </div>

                  <div style={{ padding: '0.75rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>False Positive Rate (FPR)</div>
                    <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#2E7D32' }}>
                      {(simulationResult.false_positive_rate * 100).toFixed(1)}%
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                      {simulationResult.false_alarms} / {simulationResult.clean_samples} false alarms
                    </div>
                  </div>

                  <div style={{ padding: '0.75rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Forecast Degradation (ΔBS)</div>
                    <div style={{ fontSize: '1.3rem', fontWeight: 700, color: simulationResult.brier_score_degradation > 0 ? '#C96A3E' : '#2E7D32' }}>
                      {simulationResult.brier_score_degradation >= 0 ? `+${simulationResult.brier_score_degradation.toFixed(4)}` : simulationResult.brier_score_degradation.toFixed(4)}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                      Clean BS: {simulationResult.clean_brier_score.toFixed(4)} &rarr; Attacked: {simulationResult.attack_brier_score.toFixed(4)}
                    </div>
                  </div>

                  <div style={{ padding: '0.75rem', background: 'var(--bg-cream)', border: '1px solid var(--border-sand)', borderRadius: '2px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Recovery Efficiency (RE)</div>
                    <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent-terracotta)' }}>
                      {(simulationResult.defensive_recovery_efficiency * 100).toFixed(1)}%
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                      Defended BS: {simulationResult.defended_brier_score.toFixed(4)}
                    </div>
                  </div>
                </div>

                {/* Sample-by-Sample Telemetry Detection Strip */}
                <div style={{ marginBottom: '0.5rem' }}>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, display: 'block', marginBottom: '0.4rem' }}>
                    Sample Sequence Telemetry Strip (Ground Truth vs Detector Flag):
                  </label>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {simulationResult.ground_truth_labels.map((isInjected, idx) => {
                      const isFlagged = simulationResult.detector_flags[idx]
                      const classification = simulationResult.detector_classifications[idx] || 'CLEAN_BENCHMARK'

                      let bgColor = '#E8F5E9'
                      let borderColor = '#81C784'
                      let labelText = 'CLEAN'

                      if (isInjected && isFlagged) {
                        bgColor = '#FFEBEE'
                        borderColor = '#E57373'
                        labelText = 'INJ+FLAG'
                      } else if (isInjected && !isFlagged) {
                        bgColor = '#FFF3E0'
                        borderColor = '#FFB74D'
                        labelText = 'MISSED'
                      } else if (!isInjected && isFlagged) {
                        bgColor = '#FFF9C4'
                        borderColor = '#FFF176'
                        labelText = 'FALSE ALARM'
                      }

                      return (
                        <div
                          key={idx}
                          style={{
                            padding: '0.35rem 0.6rem',
                            background: bgColor,
                            border: `1px solid ${borderColor}`,
                            borderRadius: '3px',
                            fontSize: '0.75rem',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            gap: '0.15rem',
                          }}
                        >
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>#{idx + 1}</span>
                          <span style={{ fontSize: '0.65rem', fontWeight: 600 }}>{labelText}</span>
                          <span style={{ fontSize: '0.6rem', color: 'var(--text-dim)' }}>{classification}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic', marginTop: '0.5rem' }}>
                  {simulationResult.summary}
                </div>
              </div>
            )}
          </div>

          {/* Transparent Checks vs Baseline Detector Matrix */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header">
              <h3 className="panel-title">Active Defensive Checks & Baseline Detector Specification</h3>
              <span className="badge badge-sand">6 TRANSPARENT CHECKS + MULTIVARIATE ENVELOPE</span>
            </div>

            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Defensive Check Name</th>
                    <th>Detection Mechanism</th>
                    <th>Physical Limits / Bounds</th>
                    <th>Severity</th>
                    <th>Calibrated Classification</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>1. Impossible Values</strong></td>
                    <td>Domain-boundary verification</td>
                    <td className="mono-cell">Precip: [0, 1500] mm · SST: [15, 35]°C · ONI: [-4.5, 4.5]°C</td>
                    <td><span className="badge badge-err">CRITICAL</span></td>
                    <td><code>DATA_QUALITY_ANOMALY</code> / <code>SUSPICIOUS_ANOMALY</code></td>
                  </tr>
                  <tr>
                    <td><strong>2. Sudden Step Changes</strong></td>
                    <td>Thermal/mass inertia rate limits</td>
                    <td className="mono-cell">SST jump &le; 2.5°C/mo · ONI jump &le; 1.2°C/mo</td>
                    <td><span className="badge badge-warn">HIGH</span></td>
                    <td><code>SUSPICIOUS_ANOMALY</code></td>
                  </tr>
                  <tr>
                    <td><strong>3. Missingness & Sentinels</strong></td>
                    <td>Null and telemetry sentinel scanning</td>
                    <td className="mono-cell">NaN, null, -999.0, 999.9, -99.9</td>
                    <td><span className="badge badge-sand">MEDIUM</span></td>
                    <td><code>DATA_QUALITY_ANOMALY</code></td>
                  </tr>
                  <tr>
                    <td><strong>4. Timestamp Irregularities</strong></td>
                    <td>Temporal monotonicity & duplicate check</td>
                    <td className="mono-cell">Strictly forward sequence, unique monthly stamps</td>
                    <td><span className="badge badge-sand">MEDIUM</span></td>
                    <td><code>DATA_QUALITY_ANOMALY</code></td>
                  </tr>
                  <tr>
                    <td><strong>5. Replayed & Frozen Telemetry</strong></td>
                    <td>Turbulent fluid variance verification</td>
                    <td className="mono-cell">&ge;3-period constant sensor freeze or exact sequence repeat</td>
                    <td><span className="badge badge-warn">HIGH</span></td>
                    <td><code>SUSPICIOUS_ANOMALY</code></td>
                  </tr>
                  <tr>
                    <td><strong>6. Cross-Source Coherence</strong></td>
                    <td>Teleconnection multi-sensor comparison</td>
                    <td className="mono-cell">|ONI - 3mo Niño 3.4 mean| &le; 0.50°C</td>
                    <td><span className="badge badge-err">CRITICAL</span></td>
                    <td><code>POTENTIAL_ADVERSARIAL_PERTURBATION</code></td>
                  </tr>
                  <tr>
                    <td><strong>7. Baseline Multivariate Detector</strong></td>
                    <td>Mahalanobis distance D_M^2 on clean covariance</td>
                    <td className="mono-cell">D_M^2 &le; &chi;^2_p(0.99) · Fits joint teleconnection structure</td>
                    <td><span className="badge badge-warn">HIGH</span></td>
                    <td><code>POTENTIAL_ADVERSARIAL_PERTURBATION</code></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Live Telemetry Stream Inspector */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header">
              <h3 className="panel-title">Interactive Telemetry Stream Inspector</h3>
              <span className="badge badge-sand">LIVE VERIFICATION</span>
            </div>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-dim)', margin: '0 0 0.75rem 0' }}>
              Test incoming observation streams against the defensive engine. Select a test scenario payload to trigger live screening:
            </p>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <button
                className={`btn ${testPayloadType === 'clean' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => void handleRunInspection('clean')}
                disabled={inspecting}
                type="button"
              >
                Clean Telemetry
              </button>
              <button
                className={`btn ${testPayloadType === 'sentinel' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => void handleRunInspection('sentinel')}
                disabled={inspecting}
                type="button"
              >
                Sentinel Code (-999.0)
              </button>
              <button
                className={`btn ${testPayloadType === 'jump' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => void handleRunInspection('jump')}
                disabled={inspecting}
                type="button"
              >
                Sudden Jump (+5.3°C)
              </button>
              <button
                className={`btn ${testPayloadType === 'freeze' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => void handleRunInspection('freeze')}
                disabled={inspecting}
                type="button"
              >
                Sensor Freeze (Dead Telemetry)
              </button>
              <button
                className={`btn ${testPayloadType === 'impossible' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => void handleRunInspection('impossible')}
                disabled={inspecting}
                type="button"
              >
                Impossible Domain Values
              </button>
            </div>

            {inspectReport && (
              <div style={{ background: 'var(--bg-cream)', padding: '1rem', border: '1px solid var(--border-sand)', borderRadius: '3px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div>
                    <strong>Stream ID:</strong> <code className="mono-cell">{inspectReport.series_id}</code> · Records: {inspectReport.total_records}
                  </div>
                  <span className={`badge ${inspectReport.passed ? 'badge-ok' : 'badge-warn'}`}>
                    {inspectReport.passed ? 'PASSED SCREENING' : `FLAGGED (${inspectReport.overall_classification})`}
                  </span>
                </div>

                <div style={{ fontSize: '0.85rem', color: 'var(--text-charcoal)', marginBottom: '0.75rem' }}>
                  {inspectReport.summary}
                </div>

                {inspectReport.anomalies.length > 0 && (
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Feature</th>
                          <th>Observed</th>
                          <th>Expected Range</th>
                          <th>Type</th>
                          <th>Classification</th>
                          <th>Suspicion Score</th>
                          <th>Confirmed Malicious?</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inspectReport.anomalies.map((anom, idx) => (
                          <tr key={idx}>
                            <td className="mono-cell">{anom.timestamp ?? '—'}</td>
                            <td><code>{anom.feature_name}</code></td>
                            <td className="mono-cell">{JSON.stringify(anom.observed_value)}</td>
                            <td>{anom.expected_range}</td>
                            <td><span className="badge badge-sand">{anom.anomaly_type}</span></td>
                            <td><span className="badge badge-warn">{anom.classification}</span></td>
                            <td className="mono-cell">{(anom.suspicion_score * 100).toFixed(0)}%</td>
                            <td>
                              <span className="badge badge-ok" style={{ fontSize: '0.7rem' }}>
                                {anom.is_confirmed_malicious ? 'YES' : 'NO (Epistemic Rule)'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {activeSubTab === 'system' && (
        <div>
          {/* Visual Pipeline Stages Flow */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header">
              <h3 className="panel-title">End-to-End Computational Pipeline Flow</h3>
              <span className="badge badge-sand">MODULAR MONOLITH</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem', marginTop: '0.5rem' }}>
              {pipelineStages.map((stage) => (
                <div
                  key={stage.step}
                  style={{
                    padding: '0.75rem',
                    background: 'var(--bg-cream)',
                    border: '1px solid var(--border-sand)',
                    borderRadius: '2px',
                    position: 'relative',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--accent-terracotta)' }}>
                      STAGE {stage.step}
                    </span>
                    <span className={`badge ${stage.status === 'OPERATIONAL' || stage.status === 'LOADED' || stage.status === 'EVALUATED' ? 'badge-ok' : 'badge-warn'}`} style={{ fontSize: '0.65rem' }}>
                      {stage.status}
                    </span>
                  </div>
                  <strong style={{ fontSize: '0.9rem', color: 'var(--text-charcoal)' }}>{stage.name}</strong>
                  <div style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', margin: '0.2rem 0' }}>
                    {stage.module}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                    {stage.details}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Telemetry Panels */}
          <div className="grid-2">
            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">FastAPI Service Metadata</h3>
                <span className="badge badge-charcoal">v{status?.version || '0.1.0'}</span>
              </div>
              <table className="data-table">
                <tbody>
                  <tr>
                    <td><strong>Service Identifier</strong></td>
                    <td className="mono-cell">{status?.service ?? 'enso-shield-api'}</td>
                  </tr>
                  <tr>
                    <td><strong>Runtime Environment</strong></td>
                    <td className="mono-cell">{status?.environment ?? 'development'}</td>
                  </tr>
                  <tr>
                    <td><strong>Swagger Interactive UI</strong></td>
                    <td>
                      <a href={swaggerUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-terracotta)', fontWeight: 600 }}>
                        {swaggerUrl} &rarr;
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>OpenAPI Specification</strong></td>
                    <td>
                      <a href={openApiUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--text-muted)' }}>
                        {openApiUrl}
                      </a>
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Server Timestamp (UTC)</strong></td>
                    <td className="mono-cell">{status?.timestamp_utc ?? '—'}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">PostgreSQL Container State</h3>
                <span className={`badge ${status?.database.status === 'connected' ? 'badge-ok' : 'badge-err'}`}>
                  {status?.database.status.toUpperCase() ?? 'UNKNOWN'}
                </span>
              </div>
              <table className="data-table">
                <tbody>
                  <tr>
                    <td><strong>Connection Latency</strong></td>
                    <td className="mono-cell">
                      {status?.database.latency_ms !== null ? `${status?.database.latency_ms} ms` : '—'}
                    </td>
                  </tr>
                  <tr>
                    <td><strong>Persistence Volume</strong></td>
                    <td className="mono-cell">enso_pgdata (Named Docker Volume)</td>
                  </tr>
                  <tr>
                    <td><strong>Internal Container Network</strong></td>
                    <td className="mono-cell">db:5432 (bridge enso-net)</td>
                  </tr>
                  <tr>
                    <td><strong>Host Port Forwarding</strong></td>
                    <td className="mono-cell">127.0.0.1:5433 (no collision with host 5432)</td>
                  </tr>
                  <tr>
                    <td><strong>Schema Migrations</strong></td>
                    <td className="mono-cell">2 applied (reversible SQL files)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Background Jobs Audit & Log Inspector */}
          <ErrorBoundary fallbackTitle="Job Audit Table Error">
            <div className="panel" style={{ marginTop: '1.5rem' }}>
              <div className="panel-header">
                <h3 className="panel-title">Job Execution Audit History</h3>
                <button className="btn btn-secondary" onClick={() => void loadData()} disabled={loading} type="button">
                  Refresh Jobs
                </button>
              </div>

              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Job ID</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Created</th>
                      <th>Duration</th>
                      <th>Error</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j: JobRecord) => (
                      <tr key={j.job_id}>
                        <td className="mono-cell"><strong>{j.job_id}</strong></td>
                        <td><span className="badge badge-sand">{j.job_type}</span></td>
                        <td>
                          <span className={`badge ${j.status === 'completed' ? 'badge-ok' : j.status === 'failed' ? 'badge-err' : 'badge-warn'}`}>
                            {j.status}
                          </span>
                        </td>
                        <td className="mono-cell" style={{ fontSize: '0.75rem' }}>
                          {new Date(j.created_at).toLocaleString()}
                        </td>
                        <td className="mono-cell">
                          {typeof j.duration_seconds === 'number' ? `${j.duration_seconds.toFixed(2)}s` : '—'}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: j.error_message ? 'var(--status-err)' : 'var(--text-dim)' }}>
                          {j.error_message || 'None'}
                        </td>
                        <td>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => setSelectedJob(j)}
                            type="button"
                          >
                            View Logs
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Selected Job Log Detail Modal / Panel */}
              {selectedJob && (
                <div style={{ marginTop: '1.25rem', borderTop: '1px solid var(--border-sand)', paddingTop: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div>
                      <strong>Job Log:</strong> <code className="mono-cell">{selectedJob.job_id}</code> ({selectedJob.job_type})
                    </div>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem' }}
                      onClick={() => setSelectedJob(null)}
                      type="button"
                    >
                      Close
                    </button>
                  </div>
                  <div className="terminal-output">
                    {selectedJob.logs || 'No log messages captured for this job.'}
                  </div>
                </div>
              )}
            </div>
          </ErrorBoundary>
        </div>
      )}
    </div>
  )
}
