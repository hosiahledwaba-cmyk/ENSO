import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  ActiveModelResponse,
  JobRecord,
  ModelsAuditResponse,
  QuarantineDossierItem,
  PoisoningScenarioItem,
  PoisoningReportItem,
} from '../api/client'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { BarChart, type BarGroup } from '../components/charts/BarChart'

interface ModelsViewProps {
  api: ReturnType<typeof createApiClient>
}

type ModelSubTab = 'overview' | 'integrity' | 'poisoning'

export function ModelsView({ api }: ModelsViewProps) {
  const [activeTab, setActiveTab] = useState<ModelSubTab>('overview')

  // Operational model state
  const [model, setModel] = useState<ActiveModelResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Retrain job state
  const [holdoutCount, setHoldoutCount] = useState(2)
  const [seed, setSeed] = useState(42)
  const [submitting, setSubmitting] = useState(false)
  const [currentJob, setCurrentJob] = useState<JobRecord | null>(null)

  // Integrity & Quarantine state
  const [auditData, setAuditData] = useState<ModelsAuditResponse | null>(null)
  const [quarantinedDossiers, setQuarantinedDossiers] = useState<QuarantineDossierItem[]>([])
  const [verifying, setVerifying] = useState(false)
  const [verifyOutcome, setVerifyOutcome] = useState<{ message: string; isOk: boolean } | null>(null)

  // Quarantine action modal / form state
  const [quarantineReason, setQuarantineReason] = useState('ARTEFACT_DIGEST_MISMATCH')
  const [quarantineDetails, setQuarantineDetails] = useState('Manual security audit inspection.')
  const [quarantining, setQuarantining] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const [replacementStatus, setReplacementStatus] = useState<string | null>(null)

  // Poisoning Harness state
  const [poisoningScenarios, setPoisoningScenarios] = useState<PoisoningScenarioItem[]>([])
  const [threatLimitations, setThreatLimitations] = useState<string[]>([])
  const [recoveryProtocol, setRecoveryProtocol] = useState<string[]>([])
  const [selectedAttackClass, setSelectedAttackClass] = useState<string>('LABEL_FLIPPING')
  const [flipFraction, setFlipFraction] = useState<number>(0.20)
  const [shiftDelta, setShiftDelta] = useState<number>(-1.5)
  const [outlierCount, setOutlierCount] = useState<number>(1)
  const [poisoningRunning, setPoisoningRunning] = useState(false)
  const [poisoningReport, setPoisoningReport] = useState<PoisoningReportItem | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [activeData, auditRes, quarRes, scenRes] = await Promise.all([
        api.getActiveModel().catch((err: unknown) => {
          console.warn('Active model load note:', err)
          return null
        }),
        api.auditModels().catch(() => null),
        api.listQuarantinedModels().catch(() => ({ quarantined_models: [], count: 0 })),
        api.getPoisoningScenarios().catch(() => ({ scenarios: [], threat_limitations: [], recovery_protocol: [] })),
      ])

      setModel(activeData)
      setAuditData(auditRes)
      setQuarantinedDossiers(quarRes.quarantined_models)
      setPoisoningScenarios(scenRes.scenarios)
      setThreatLimitations(scenRes.threat_limitations)
      setRecoveryProtocol(scenRes.recovery_protocol)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load model registry')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadData()
  }, [loadData])

  // Poll current training job
  useEffect(() => {
    if (!currentJob || currentJob.status === 'completed' || currentJob.status === 'failed') {
      return
    }
    const timer = setInterval(async () => {
      try {
        const updated = await api.getJob(currentJob.job_id)
        setCurrentJob(updated)
        if (updated.status === 'completed') {
          void loadData()
        }
      } catch (err) {
        console.error('Training job polling error:', err)
      }
    }, 1500)
    return () => clearInterval(timer)
  }, [api, currentJob, loadData])

  const handleStartTraining = async () => {
    try {
      setSubmitting(true)
      const res = await api.startTrainingJob({ holdout_count: holdoutCount, seed })
      const initialJob = await api.getJob(res.job_id)
      setCurrentJob(initialJob)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to launch training job')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVerifyIntegrity = async () => {
    setVerifying(true)
    setVerifyOutcome(null)
    try {
      const res = await api.verifyModelIntegrity('models/logistic_regression_baseline')
      if (res.verified) {
        setVerifyOutcome({
          message: `Integrity VERIFIED: SHA-256 match confirmed (${res.audit.expected_digest.substring(0, 16)}...)`,
          isOk: true,
        })
      } else {
        setVerifyOutcome({
          message: `Integrity FAILURE: Issues detected - ${res.audit.issues.join('; ')}`,
          isOk: false,
        })
      }
      void loadData()
    } catch (err: unknown) {
      setVerifyOutcome({
        message: err instanceof Error ? err.message : 'Verification failed',
        isOk: false,
      })
    } finally {
      setVerifying(false)
    }
  }

  const handleQuarantineModel = async () => {
    if (!confirm('Are you sure you want to isolate and quarantine this active model artefact?')) {
      return
    }
    setQuarantining(true)
    try {
      const res = await api.quarantineModel({
        model_dir: 'models/logistic_regression_baseline',
        reason: quarantineReason,
        details: quarantineDetails,
      })
      alert(`Model quarantined successfully! Dossier ID: ${res.dossier.dossier_id}`)
      void loadData()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Quarantine action failed')
    } finally {
      setQuarantining(false)
    }
  }

  const handleReplaceModel = async () => {
    if (!confirm('Replace suspect model directory with verified approved golden baseline?')) {
      return
    }
    setReplacing(true)
    setReplacementStatus(null)
    try {
      const res = await api.replaceQuarantinedModel({
        target_model_dir: 'models/logistic_regression_baseline',
        replacement_source_dir: 'models/logistic_regression_baseline',
        approved_by: 'lead_security_evaluator',
      })
      setReplacementStatus(`Restoration completed: ${res.message}`)
      void loadData()
    } catch (err: unknown) {
      setReplacementStatus(`Restoration failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setReplacing(false)
    }
  }

  const handleRunPoisoningTest = async () => {
    setPoisoningRunning(true)
    setPoisoningReport(null)
    try {
      const params: Record<string, unknown> = {}
      if (selectedAttackClass === 'LABEL_FLIPPING') {
        params.flip_fraction = flipFraction
      } else if (selectedAttackClass === 'SUBPOPULATION_FEATURE_POISONING') {
        params.feature_name = 'oni_aso_degc'
        params.shift_delta = shiftDelta
      } else if (selectedAttackClass === 'EXTREME_LEVERAGE_OUTLIER') {
        params.n_outliers = outlierCount
      } else if (selectedAttackClass === 'TARGETED_BACKDOOR') {
        params.trigger_feature = 'nino34_aso_anom_degc'
        params.trigger_value = 3.14
      }

      const res = await api.evaluatePoisoningExperiment({
        attack_class: selectedAttackClass,
        attack_params: params,
        holdout_count: 2,
      })
      setPoisoningReport(res.report)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Poisoning experiment failed')
    } finally {
      setPoisoningRunning(false)
    }
  }

  // Visualizations for Operational Overview
  const weightBarData: BarGroup[] = []
  if (model?.coefficients) {
    Object.entries(model.coefficients).forEach(([feat, w]) => {
      weightBarData.push({
        category: feat,
        values: { weight: w },
      })
    })
  }

  const metricBarData: BarGroup[] = []
  if (model?.baseline_metrics && model?.logistic_metrics) {
    metricBarData.push(
      {
        category: 'Climatology Baseline',
        values: {
          brier: model.baseline_metrics.brier_score ?? 0,
          log_loss: model.baseline_metrics.log_loss ?? 0,
        },
      },
      {
        category: 'Logistic Regression',
        values: {
          brier: model.logistic_metrics.brier_score ?? 0,
          log_loss: model.logistic_metrics.log_loss ?? 0,
        },
      }
    )
  }

  // Visualization for Poisoning Coefficient Displacements
  const poisoningCoeffBarData: BarGroup[] = []
  if (poisoningReport?.coefficient_shifts) {
    Object.entries(poisoningReport.coefficient_shifts).forEach(([feat, delta]) => {
      poisoningCoeffBarData.push({
        category: feat,
        values: { delta_weight: delta },
      })
    })
  }

  const bss = model?.logistic_metrics?.brier_skill_score ?? 0

  return (
    <div>
      <div className="view-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Climate Model Registry &amp; Tampering Defenses</h1>
          <p className="view-lead">
            Inspect cryptographic model manifests v2.0, verify artefact digests, enforce schema compatibility,
            and benchmark poisoning resilience on isolated training copies.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-secondary" onClick={() => void loadData()} disabled={loading} type="button">
            Refresh Registry
          </button>
        </div>
      </div>

      {/* Subtab Navigation Bar */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem' }}>
        <button
          className={`btn ${activeTab === 'overview' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('overview')}
          type="button"
        >
          Model Overview &amp; Verification
        </button>
        <button
          className={`btn ${activeTab === 'integrity' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('integrity')}
          type="button"
        >
          Artefact Integrity &amp; Quarantine
          {auditData?.quarantined_count ? (
            <span className="badge badge-err" style={{ marginLeft: '0.4rem', fontSize: '0.7rem' }}>
              {auditData.quarantined_count}
            </span>
          ) : null}
        </button>
        <button
          className={`btn ${activeTab === 'poisoning' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('poisoning')}
          type="button"
        >
          Training Poisoning Resilience Harness
        </button>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.5rem' }}>
          <div className="notice-title">Model Registry Notice</div>
          {error}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: OVERVIEW & BASELINE VERIFICATION                                    */}
      {/* ========================================================================= */}
      {activeTab === 'overview' && (
        <div>
          {/* Manifest v2.0 Metadata Strip */}
          <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
            <div className="metric-card">
              <div className="metric-label">Model Version &amp; Status</div>
              <div className="metric-value" style={{ fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>{model?.model_version || 'v1.0.0'}</span>
                {model?.approval_status === 'APPROVED' ? (
                  <span className="badge badge-ok">APPROVED</span>
                ) : model?.approval_status === 'QUARANTINED' ? (
                  <span className="badge badge-err">QUARANTINED</span>
                ) : (
                  <span className="badge badge-warn">{model?.approval_status || 'UNKNOWN'}</span>
                )}
              </div>
              <div className="metric-sub mono-cell">{model?.model_id || '—'}</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Artefact SHA-256 Digest</div>
              <div className="metric-value mono-cell" style={{ fontSize: '0.85rem', wordBreak: 'break-all' }}>
                {model?.artefact_digest ? `${model.artefact_digest.substring(0, 16)}...` : 'Pre-audit'}
              </div>
              <div className="metric-sub">
                {model?.audit?.digest_matches ? (
                  <span style={{ color: 'var(--status-ok)' }}>Digest Matches Manifest</span>
                ) : (
                  <span>Verified at Load Time</span>
                )}
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Training Data Fingerprint</div>
              <div className="metric-value mono-cell" style={{ fontSize: '0.85rem' }}>
                {model?.training_data_fingerprint
                  ? `${model.training_data_fingerprint.substring(0, 16)}...`
                  : model?.dataset_fingerprint
                  ? `${model.dataset_fingerprint.substring(0, 16)}...`
                  : '—'}
              </div>
              <div className="metric-sub">Provenance Authenticated</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Holdout Brier Skill Score</div>
              <div className="metric-value mono-cell" style={{ color: bss >= 0 ? 'var(--status-ok)' : 'var(--status-err)' }}>
                {bss >= 0 ? `+${bss.toFixed(4)}` : bss.toFixed(4)}
              </div>
              <div className="metric-sub">Reference: Historical Climatology</div>
            </div>
          </div>

          {/* Visual Intelligence: Feature Weights & Verification Metrics */}
          <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
            <ErrorBoundary fallbackTitle="Feature Weights Chart Error">
              <BarChart
                title="Learned Model Feature Weights (wi)"
                subtitle="Logistic regression coefficients (positive = risk increasing, negative = suppressing)"
                data={weightBarData}
                series={[{ key: 'weight', label: 'Coefficient Weight', color: 'var(--chart-primary)' }]}
                horizontal
                height={260}
                referenceLine={{ value: 0, label: 'Zero Line', color: 'var(--chart-axis)' }}
                interpretation="Warm ENSO anomalies (`oni_aso_degc`) carry positive weights increasing drought logit, while antecedent spring soil moisture (`precip_oct_zscore`) acts as a negative risk suppressor."
              />
            </ErrorBoundary>

            <ErrorBoundary fallbackTitle="Model Metrics Chart Error">
              <BarChart
                title="Holdout Verification Score Comparison"
                subtitle="Brier Score & Log Loss on Untouched Test Partition (Lower is Better)"
                data={metricBarData}
                series={[
                  { key: 'brier', label: 'Holdout Brier Score', color: 'var(--accent-terracotta)' },
                  { key: 'log_loss', label: 'Holdout Log Loss', color: 'var(--chart-blue-cool)' },
                ]}
                height={260}
                interpretation="Historical climatology reference provides robust probabilistic baseline against over-fitting in small-sample climate regimes."
              />
            </ErrorBoundary>
          </div>

          {/* Retrain Workflow Launcher & Log Output */}
          <div className="grid-2">
            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">Retrain Baseline Model</h3>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Executes rolling-origin expanding-window training, serializes model weights, computes streaming
                SHA-256 artefact digest, and commits reproducible manifest v2.0.
              </p>

              <div className="form-group">
                <label className="form-label">Holdout Season Count</label>
                <input
                  type="number"
                  min="1"
                  max="5"
                  className="form-input"
                  value={holdoutCount}
                  onChange={(e) => setHoldoutCount(Number(e.target.value))}
                />
                <div className="form-hint">Number of final seasons reserved as untouched holdout test partition.</div>
              </div>

              <div className="form-group">
                <label className="form-label">Random Seed</label>
                <input
                  type="number"
                  className="form-input"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                />
              </div>

              <button
                className="btn btn-primary"
                onClick={() => void handleStartTraining()}
                disabled={submitting || (currentJob !== null && currentJob.status === 'running')}
                type="button"
              >
                {submitting || currentJob?.status === 'running' ? 'Training Model Pipeline...' : 'Train Model Pipeline'}
              </button>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">Training Execution Output</h3>
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
                    {currentJob.logs || 'Awaiting training output...\n'}
                  </div>
                </div>
              ) : (
                <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                  No active training execution. Click &quot;Train Model Pipeline&quot; to refit and re-sign the baseline model.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: ARTEFACT INTEGRITY & QUARANTINE PROTOCOL                           */}
      {/* ========================================================================= */}
      {activeTab === 'integrity' && (
        <div>
          {/* Posture Summary Banner */}
          <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
            <div className="metric-card">
              <div className="metric-label">Registry Integrity Posture</div>
              <div className="metric-value">
                {auditData?.posture === 'HEALTHY' ? (
                  <span className="badge badge-ok">HEALTHY (VERIFIED)</span>
                ) : (
                  <span className="badge badge-err">DEGRADED / ACTION REQ</span>
                )}
              </div>
              <div className="metric-sub">{auditData?.passed_count ?? 0} of {auditData?.total_scanned ?? 0} models passed audit</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Quarantined Artefacts</div>
              <div className="metric-value mono-cell">
                {quarantinedDossiers.length}
              </div>
              <div className="metric-sub">Isolated in secure forensic quarantine</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Verification Gate</div>
              <div className="metric-value" style={{ fontSize: '1rem', color: 'var(--status-ok)' }}>
                ENFORCED PRE-INFERENCE
              </div>
              <div className="metric-sub">Auto-quarantine on hash mismatch</div>
            </div>
          </div>

          {/* Action Trigger Card */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 className="panel-title">Active Operational Model Integrity Status</h3>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => void handleVerifyIntegrity()}
                  disabled={verifying}
                  type="button"
                >
                  {verifying ? 'Computing SHA-256...' : 'Verify Artefact Integrity Now'}
                </button>
              </div>
            </div>

            {verifyOutcome && (
              <div
                className={`notice ${verifyOutcome.isOk ? 'notice-ok' : 'notice-warning'}`}
                style={{ marginBottom: '1rem' }}
              >
                <div className="notice-title">{verifyOutcome.isOk ? 'Verification Passed' : 'Verification Alert'}</div>
                {verifyOutcome.message}
              </div>
            )}

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Model Directory</th>
                    <th>Version</th>
                    <th>Approval Status</th>
                    <th>Artefact Digest</th>
                    <th>Digest Match</th>
                    <th>Quarantined</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {auditData?.models.map((m) => (
                    <tr key={m.model_id}>
                      <td className="mono-cell">{m.model_dir}</td>
                      <td>{m.model_version || '1.0.0'}</td>
                      <td>
                        <span className={`badge ${m.approval_status === 'APPROVED' ? 'badge-ok' : 'badge-err'}`}>
                          {m.approval_status}
                        </span>
                      </td>
                      <td className="mono-cell" style={{ fontSize: '0.75rem' }}>
                        {m.expected_digest ? `${m.expected_digest.substring(0, 16)}...` : '—'}
                      </td>
                      <td>
                        {m.digest_matches ? (
                          <span className="badge badge-ok">MATCH</span>
                        ) : (
                          <span className="badge badge-err">MISMATCH</span>
                        )}
                      </td>
                      <td>
                        {m.quarantined ? (
                          <span className="badge badge-err">YES</span>
                        ) : (
                          <span className="badge badge-ok">NO</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary"
                          style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                          onClick={() => void handleVerifyIntegrity()}
                          type="button"
                        >
                          Re-audit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Quarantine & Safe Replacement Controls */}
          <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">Quarantine Suspect Artefact</h3>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Isolate suspect or tampered model artefacts, generate a forensic audit dossier, and revoke
                operational authorization.
              </p>

              <div className="form-group">
                <label className="form-label">Quarantine Reason</label>
                <select
                  className="form-input"
                  value={quarantineReason}
                  onChange={(e) => setQuarantineReason(e.target.value)}
                >
                  <option value="ARTEFACT_DIGEST_MISMATCH">ARTEFACT_DIGEST_MISMATCH (Hash Discrepancy)</option>
                  <option value="UNAPPROVED_VERSION">UNAPPROVED_VERSION (Unauthorized Promotion)</option>
                  <option value="INCOMPATIBLE_SCHEMA">INCOMPATIBLE_SCHEMA (Missing Required Predictors)</option>
                  <option value="SUSPECTED_POISONING">SUSPECTED_POISONING (Adversarial Data Modification)</option>
                  <option value="MANUAL_QUARANTINE">MANUAL_QUARANTINE (Investigator Hold)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Investigation Details / Notes</label>
                <textarea
                  className="form-input"
                  rows={3}
                  value={quarantineDetails}
                  onChange={(e) => setQuarantineDetails(e.target.value)}
                />
              </div>

              <button
                className="btn btn-secondary"
                style={{ borderColor: 'var(--status-err)', color: 'var(--status-err)' }}
                onClick={() => void handleQuarantineModel()}
                disabled={quarantining}
                type="button"
              >
                {quarantining ? 'Quarantining Artefact...' : 'Quarantine Active Model'}
              </button>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h3 className="panel-title">Safe Artefact Replacement</h3>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Restore the operational baseline from a verified golden model after completing quarantine review.
                Enforces cryptographic check before restoring traffic.
              </p>

              {replacementStatus && (
                <div className="notice notice-ok" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
                  {replacementStatus}
                </div>
              )}

              <div style={{ marginBottom: '1rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Replacement Source: <strong className="mono-cell">models/logistic_regression_baseline</strong> (Approved Golden Candidate)
              </div>

              <button
                className="btn btn-primary"
                onClick={() => void handleReplaceModel()}
                disabled={replacing}
                type="button"
              >
                {replacing ? 'Restoring Model...' : 'Restore Verified Operational Baseline'}
              </button>
            </div>
          </div>

          {/* Quarantined Dossiers Ledger */}
          <div className="panel">
            <div className="panel-header">
              <h3 className="panel-title">Quarantined Artefacts Forensic Ledger</h3>
            </div>
            {quarantinedDossiers.length === 0 ? (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                No artefacts currently in quarantine. All model manifests pass cryptographic verification.
              </div>
            ) : (
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Dossier ID</th>
                      <th>Model ID</th>
                      <th>Quarantined At</th>
                      <th>Reason Code</th>
                      <th>Investigation Status</th>
                      <th>Expected Digest</th>
                      <th>Observed Digest</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quarantinedDossiers.map((d) => (
                      <tr key={d.dossier_id}>
                        <td className="mono-cell">{d.dossier_id}</td>
                        <td className="mono-cell">{d.model_id}</td>
                        <td style={{ fontSize: '0.8rem' }}>{d.quarantined_at_utc}</td>
                        <td>
                          <span className="badge badge-warn">{d.reason}</span>
                        </td>
                        <td>
                          <span className={`badge ${d.investigation_status === 'REPLACED' ? 'badge-ok' : 'badge-err'}`}>
                            {d.investigation_status}
                          </span>
                        </td>
                        <td className="mono-cell" style={{ fontSize: '0.7rem' }}>
                          {d.expected_digest ? `${d.expected_digest.substring(0, 12)}...` : 'None'}
                        </td>
                        <td className="mono-cell" style={{ fontSize: '0.7rem' }}>
                          {d.observed_digest ? `${d.observed_digest.substring(0, 12)}...` : 'None'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: TRAINING POISONING RESILIENCE HARNESS                              */}
      {/* ========================================================================= */}
      {activeTab === 'poisoning' && (
        <div>
          {/* Scientific Callout: Threats, Boundaries & Limitations */}
          <div className="notice" style={{ marginBottom: '1.5rem' }}>
            <div className="notice-title">Adversarial Threat Boundaries &amp; Defense Limitations (RD-015)</div>
            <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem' }}>
              <strong>Zero Universal Protection Guarantee:</strong> Cryptographic model manifests verify at-rest
              weights against post-training tampering, but cannot prevent clean-label poisoning injected into upstream
              observations prior to training unless input anomaly screening detects the perturbation.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', fontSize: '0.8rem', marginTop: '0.75rem' }}>
              <div>
                <strong>Tested Attack Classes:</strong>
                <ul style={{ margin: '0.25rem 0', paddingLeft: '1.2rem' }}>
                  <li>Label Flipping (Drought Alert Suppression)</li>
                  <li>Clean-Label Subpopulation Feature Bias</li>
                  <li>Extreme Leverage Outlier Injection</li>
                  <li>Targeted Backdoor Watermarking</li>
                </ul>
              </div>
              <div>
                <strong>Inherent Limitations:</strong>
                <ul style={{ margin: '0.25rem 0', paddingLeft: '1.2rem' }}>
                  {threatLimitations.length > 0 ? (
                    threatLimitations.map((lim, idx) => <li key={idx}>{lim}</li>)
                  ) : (
                    <>
                      <li>Linear models with N=24 seasons are sensitive to Cook&apos;s D &gt; 1.0 points</li>
                      <li>Inverted slopes can occur within statistical margins</li>
                      <li>Stealthy bilevel optimization attacks evade basic 3-sigma filters</li>
                    </>
                  )}
                </ul>
              </div>
              <div>
                <strong>Recovery Protocol:</strong>
                <ul style={{ margin: '0.25rem 0', paddingLeft: '1.2rem' }}>
                  {recoveryProtocol.length > 0 ? (
                    recoveryProtocol.map((step, idx) => <li key={idx}>{step}</li>)
                  ) : (
                    <>
                      <li>1. Immediate quarantine via ModelQuarantineManager</li>
                      <li>2. Training dataset hash check against provenance log</li>
                      <li>3. Dataset rollback to authenticated snapshot</li>
                      <li>4. Retraining &amp; holdout BSS verification</li>
                    </>
                  )}
                </ul>
              </div>
            </div>
          </div>

          {/* Poisoning Experiment Config Panel */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div className="panel-header">
              <h3 className="panel-title">Isolated Poisoning Attack Simulator</h3>
            </div>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Creates an isolated scratch clone of the training dataset, injects controlled modifications,
              retrains a candidate model, and evaluates performance degradation against the clean baseline.
            </p>

            <div className="grid-3" style={{ marginBottom: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Attack Class</label>
                <select
                  className="form-input"
                  value={selectedAttackClass}
                  onChange={(e) => setSelectedAttackClass(e.target.value)}
                >
                  {poisoningScenarios.map((s) => (
                    <option key={s.attack_class} value={s.attack_class}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              {selectedAttackClass === 'LABEL_FLIPPING' && (
                <div className="form-group">
                  <label className="form-label">Label Flip Ratio ({Math.round(flipFraction * 100)}%)</label>
                  <input
                    type="range"
                    min="0.05"
                    max="0.50"
                    step="0.05"
                    className="form-input"
                    value={flipFraction}
                    onChange={(e) => setFlipFraction(Number(e.target.value))}
                  />
                  <div className="form-hint">Fraction of severe drought labels flipped 1 -&gt; 0.</div>
                </div>
              )}

              {selectedAttackClass === 'SUBPOPULATION_FEATURE_POISONING' && (
                <div className="form-group">
                  <label className="form-label">SST Anomaly Bias ({shiftDelta > 0 ? `+${shiftDelta}` : shiftDelta}°C)</label>
                  <input
                    type="range"
                    min="-3.0"
                    max="3.0"
                    step="0.25"
                    className="form-input"
                    value={shiftDelta}
                    onChange={(e) => setShiftDelta(Number(e.target.value))}
                  />
                  <div className="form-hint">Shift injected into `oni_aso_degc` on positive drought years.</div>
                </div>
              )}

              {selectedAttackClass === 'EXTREME_LEVERAGE_OUTLIER' && (
                <div className="form-group">
                  <label className="form-label">Synthetic Outliers Count</label>
                  <input
                    type="number"
                    min="1"
                    max="3"
                    className="form-input"
                    value={outlierCount}
                    onChange={(e) => setOutlierCount(Number(e.target.value))}
                  />
                  <div className="form-hint">Number of extreme super-El Niño points paired with label 0.</div>
                </div>
              )}

              <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => void handleRunPoisoningTest()}
                  disabled={poisoningRunning}
                  type="button"
                  style={{ width: '100%' }}
                >
                  {poisoningRunning ? 'Simulating on Isolated Copy...' : 'Run Isolated Poisoning Test'}
                </button>
              </div>
            </div>
          </div>

          {/* Comparative Audit Report */}
          {poisoningReport && (
            <div>
              <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
                <div className="metric-card">
                  <div className="metric-label">Brier Score Degradation (ΔBS)</div>
                  <div
                    className="metric-value mono-cell"
                    style={{ color: poisoningReport.brier_score_degradation > 0 ? 'var(--status-err)' : 'var(--status-ok)' }}
                  >
                    {poisoningReport.brier_score_degradation > 0
                      ? `+${poisoningReport.brier_score_degradation.toFixed(4)}`
                      : poisoningReport.brier_score_degradation.toFixed(4)}
                  </div>
                  <div className="metric-sub">
                    Clean: {poisoningReport.clean_holdout_brier_score.toFixed(4)} → Pois: {poisoningReport.poisoned_holdout_brier_score.toFixed(4)}
                  </div>
                </div>

                <div className="metric-card">
                  <div className="metric-label">L2 Weight Displacement</div>
                  <div className="metric-value mono-cell" style={{ fontSize: '1.1rem' }}>
                    ||Δw|| = {poisoningReport.l2_weight_displacement.toFixed(4)}
                  </div>
                  <div className="metric-sub">
                    Intercept Drift: {poisoningReport.intercept_shift > 0 ? `+${poisoningReport.intercept_shift.toFixed(4)}` : poisoningReport.intercept_shift.toFixed(4)}
                  </div>
                </div>

                <div className="metric-card">
                  <div className="metric-label">Holdout Risk Flips</div>
                  <div className="metric-value mono-cell" style={{ color: poisoningReport.flipped_holdout_predictions_count > 0 ? 'var(--status-err)' : 'var(--status-ok)' }}>
                    {poisoningReport.flipped_holdout_predictions_count} seasons
                  </div>
                  <div className="metric-sub">Forecast category changes on untouched test partition</div>
                </div>

                <div className="metric-card">
                  <div className="metric-label">Max Probability Drift</div>
                  <div className="metric-value mono-cell">
                    {Math.round(poisoningReport.max_probability_drift * 100)}%
                  </div>
                  <div className="metric-sub">Max |P_clean - P_poisoned|</div>
                </div>
              </div>

              {/* Coefficient Shifts Visualization */}
              <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
                <ErrorBoundary fallbackTitle="Coefficient Shifts Chart Error">
                  <BarChart
                    title="Coefficient Displacements (w_poisoned - w_clean)"
                    subtitle="Parameter shift induced by injected training data modification"
                    data={poisoningCoeffBarData}
                    series={[{ key: 'delta_weight', label: 'Weight Shift (Δw)', color: 'var(--accent-terracotta)' }]}
                    horizontal
                    height={260}
                    referenceLine={{ value: 0, label: 'No Shift', color: 'var(--chart-axis)' }}
                    interpretation="Notice how targeted data modification distorts specific physical weights (e.g., inverting SST slope or diminishing precipitation suppression)."
                  />
                </ErrorBoundary>

                <div className="panel">
                  <div className="panel-header">
                    <h3 className="panel-title">Holdout Prediction Impact Ledger</h3>
                  </div>
                  {poisoningReport.flipped_holdout_seasons.length === 0 ? (
                    <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                      No forecast category flips observed on the holdout partition at this attack intensity.
                    </div>
                  ) : (
                    <div className="table-container">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Season Year</th>
                            <th>Truth</th>
                            <th>Clean P(Drought)</th>
                            <th>Poisoned P(Drought)</th>
                            <th>Clean Category</th>
                            <th>Poisoned Category</th>
                          </tr>
                        </thead>
                        <tbody>
                          {poisoningReport.flipped_holdout_seasons.map((f) => (
                            <tr key={f.season_year}>
                              <td>{f.season_year}</td>
                              <td>{f.ground_truth === 1 ? 'DROUGHT' : 'NORMAL'}</td>
                              <td className="mono-cell">{Math.round(f.clean_probability * 100)}%</td>
                              <td className="mono-cell" style={{ color: 'var(--status-err)' }}>
                                {Math.round(f.poisoned_probability * 100)}%
                              </td>
                              <td>{f.clean_category}</td>
                              <td style={{ color: 'var(--status-err)', fontWeight: 600 }}>{f.poisoned_category}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
