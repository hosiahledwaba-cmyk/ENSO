import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  PreparednessMatrixResponse,
  PreparednessActionItem,
} from '../api/client'

interface PreparednessViewProps {
  api: ReturnType<typeof createApiClient>
}

export function PreparednessView({ api }: PreparednessViewProps) {
  const [matrixData, setMatrixData] = useState<PreparednessMatrixResponse | null>(null)
  const [selectedSector, setSelectedSector] = useState<string>('ALL')
  const [selectedTier, setSelectedTier] = useState<string>('ALL')
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // Execution modal state
  const [activeModalAction, setActiveModalAction] = useState<PreparednessActionItem | null>(null)
  const [operatorName, setOperatorName] = useState<string>('Operational Agro-Meteorologist')
  const [operatorNotes, setOperatorNotes] = useState<string>('')
  const [targetStatus, setTargetStatus] = useState<string>('EXECUTED')
  const [executing, setExecuting] = useState<boolean>(false)
  const [executionMessage, setExecutionMessage] = useState<string | null>(null)

  const loadMatrix = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getPreparednessMatrix()
      setMatrixData(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load preparedness matrix')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadMatrix()
  }, [loadMatrix])

  const handleExecuteAction = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!activeModalAction) return

    setExecuting(true)
    setExecutionMessage(null)
    try {
      const res = await api.triggerPreparednessAction(activeModalAction.id, {
        status: targetStatus,
        operator_name: operatorName,
        notes: operatorNotes || 'Anticipatory action execution recorded based on operational forecast.',
      })
      setExecutionMessage(res.message)
      void loadMatrix()
      setTimeout(() => {
        setActiveModalAction(null)
        setExecutionMessage(null)
      }, 1200)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute action')
    } finally {
      setExecuting(false)
    }
  }

  const filteredActions = (matrixData?.actions ?? []).filter((action) => {
    if (selectedSector !== 'ALL' && action.sector !== selectedSector) return false
    if (selectedTier !== 'ALL' && action.tier !== selectedTier) return false
    return true
  })

  return (
    <div className="preparedness-view-shell" data-testid="preparedness-view">
      {/* Top Header */}
      <div className="view-header" style={{ marginBottom: '1.25rem' }}>
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span>Drought Preparedness & Anticipatory Action Workflow</span>
          <span className="badge badge-terracotta" style={{ fontSize: '0.75rem' }}>
            EARLY-ACTION PROTOCOL
          </span>
        </h1>
        <p className="view-lead">
          Structured threshold-based trigger matrix and operational workflows translating probabilistic climate
          forecasts into early mitigation actions for agriculture, water basins, and disaster authorities.
        </p>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.25rem' }}>
          <div className="notice-title">Action Workflow Notice</div>
          {error}
        </div>
      )}

      {loading && !matrixData && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <span className="status-dot status-dot--green" style={{ display: 'inline-block', marginRight: '0.5rem' }} />
          Loading Anticipatory Action Matrix from ENSO Shield API...
        </div>
      )}

      {matrixData && (
        <>
          {/* Operational Risk Tier Banner */}
          <div
            className="panel"
            style={{
              background: 'var(--bg-cream)',
              borderLeft: '4px solid var(--accent-terracotta)',
              marginBottom: '1.5rem',
              padding: '1.25rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <span className="badge badge-err" style={{ fontSize: '0.75rem', marginBottom: '0.35rem' }}>
                  ACTIVE OPERATIONAL TRIGGER: {matrixData.operational_context.active_risk_tier} RISK
                </span>
                <h2 style={{ fontSize: '1.35rem', margin: '0.2rem 0' }}>
                  {matrixData.operational_context.active_risk_label}
                </h2>
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-charcoal)', maxWidth: '680px' }}>
                  {matrixData.operational_context.decision_rule}
                </p>
              </div>

              {/* Status Pill Metrics */}
              <div style={{ display: 'flex', gap: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-white)', borderRadius: '3px', border: '1px solid var(--border-sand)' }}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>FORECAST PROBABILITY</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-terracotta)' }}>
                    {matrixData.operational_context.forecast_probability_pct}%
                  </div>
                </div>

                <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-white)', borderRadius: '3px', border: '1px solid var(--border-sand)' }}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>RISK RATIO</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-charcoal)' }}>
                    {matrixData.operational_context.risk_ratio}x
                  </div>
                </div>

                <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-white)', borderRadius: '3px', border: '1px solid var(--border-sand)' }}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>ACTIONS TRIGGERED</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--status-err)' }}>
                    {matrixData.actions_summary.triggered} / {matrixData.actions_summary.total_actions}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 4-Tier Trigger Threshold Visual Progression */}
          <div style={{ marginBottom: '1.75rem' }}>
            <h3 style={{ fontSize: '1rem', margin: '0 0 0.6rem 0' }}>Anticipatory Action Trigger Matrix</h3>
            <div className="grid-4">
              {matrixData.trigger_tiers.map((t) => {
                const isCurrent = t.tier === matrixData.operational_context.active_risk_tier
                return (
                  <div
                    key={t.tier}
                    className="panel"
                    style={{
                      background: isCurrent ? '#FFF5F0' : 'var(--bg-cream)',
                      border: isCurrent ? '2px solid var(--accent-terracotta)' : '1px solid var(--border-sand)',
                      padding: '0.85rem',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)' }}>
                          TIER: {t.tier}
                        </span>
                        <span
                          className={`badge ${
                            isCurrent
                              ? 'badge-err'
                              : t.status === 'CLEARED'
                                ? 'badge-ok'
                                : t.status === 'ACTIVE_SURPASS'
                                  ? 'badge-warn'
                                  : 'badge-sand'
                          }`}
                          style={{ fontSize: '0.65rem' }}
                        >
                          {t.status}
                        </span>
                      </div>
                      <div style={{ fontSize: '1.05rem', fontWeight: 700, fontFamily: 'var(--font-mono)', marginBottom: '0.2rem' }}>
                        {t.range}
                      </div>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-charcoal)', marginBottom: '0.4rem' }}>
                        {t.label}
                      </div>
                      <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.35 }}>
                        {t.description}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Filter Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
              marginBottom: '1rem',
              padding: '0.65rem 0.85rem',
              background: 'var(--bg-cream)',
              borderRadius: '3px',
              border: '1px solid var(--border-sand)',
            }}
          >
            {/* Sector Filters */}
            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.25rem' }}>
                SECTOR:
              </span>
              {['ALL', 'AGRICULTURE', 'WATER_RESOURCES', 'LIVESTOCK', 'DISASTER_RELIEF'].map((sec) => (
                <button
                  key={sec}
                  type="button"
                  data-testid={`filter-sector-${sec.toLowerCase()}`}
                  className={`btn ${selectedSector === sec ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem' }}
                  onClick={() => setSelectedSector(sec)}
                >
                  {sec.replace('_', ' ')}
                </button>
              ))}
            </div>

            {/* Tier Filters */}
            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.25rem' }}>
                TIER:
              </span>
              {['ALL', 'ELEVATED', 'HIGH', 'CRITICAL'].map((tr) => (
                <button
                  key={tr}
                  type="button"
                  data-testid={`filter-tier-${tr.toLowerCase()}`}
                  className={`btn ${selectedTier === tr ? 'btn-primary' : 'btn-secondary'}`}
                  style={{ fontSize: '0.72rem', padding: '0.25rem 0.55rem' }}
                  onClick={() => setSelectedTier(tr)}
                >
                  {tr}
                </button>
              ))}
            </div>
          </div>

          {/* Action Cards Grid */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginBottom: '1.75rem' }}>
            {filteredActions.map((action) => {
              const isTriggered = action.status === 'TRIGGERED'
              const isExecuted = action.status === 'EXECUTED'
              return (
                <div
                  key={action.id}
                  data-testid={`action-card-${action.id.toLowerCase()}`}
                  className="panel"
                  style={{
                    borderLeft: `4px solid ${
                      isExecuted
                        ? 'var(--status-ok)'
                        : isTriggered
                          ? 'var(--accent-terracotta)'
                          : 'var(--border-sand)'
                    }`,
                    background: 'var(--bg-white)',
                    padding: '1rem 1.25rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.4rem' }}>
                    <div>
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginBottom: '0.25rem' }}>
                        <span className="badge badge-charcoal" style={{ fontSize: '0.68rem' }}>
                          {action.id}
                        </span>
                        <span className="badge badge-sand" style={{ fontSize: '0.68rem' }}>
                          {action.sector.replace('_', ' ')}
                        </span>
                        <span
                          className={`badge ${
                            action.tier === 'HIGH' || action.tier === 'CRITICAL' ? 'badge-err' : 'badge-warn'
                          }`}
                          style={{ fontSize: '0.68rem' }}
                        >
                          TRIGGER: &gt;={action.threshold_min_pct}%
                        </span>
                      </div>
                      <h4 style={{ fontSize: '1rem', margin: 0, color: 'var(--text-charcoal)' }}>
                        {action.action_name}
                      </h4>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <span
                        className={`badge ${
                          isExecuted
                            ? 'badge-ok'
                            : isTriggered
                              ? 'badge-err'
                              : action.status === 'READY'
                                ? 'badge-warn'
                                : 'badge-sand'
                        }`}
                        style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem' }}
                      >
                        {action.status}
                      </span>
                      <button
                        type="button"
                        data-testid={`btn-action-trigger-${action.id.toLowerCase()}`}
                        className={`btn ${isTriggered ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
                        onClick={() => {
                          setActiveModalAction(action)
                          setTargetStatus(isTriggered ? 'EXECUTED' : 'TRIGGERED')
                          setOperatorNotes(action.operator_notes || '')
                        }}
                      >
                        {isTriggered ? 'Confirm Execution' : 'Update Status'}
                      </button>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.825rem', color: 'var(--text-charcoal)', lineHeight: 1.45, margin: '0 0 0.6rem 0' }}>
                    {action.description}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.75rem', borderTop: '1px solid var(--border-sand)', paddingTop: '0.5rem' }}>
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Lead Agency: </span>
                      <strong>{action.lead_agency}</strong>
                    </div>
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Lead Time: </span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{action.lead_time_days} days</span>
                    </div>
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Target Subregions: </span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{action.target_subregions.join(', ')}</span>
                    </div>
                  </div>

                  {action.operator_notes && (
                    <div
                      style={{
                        marginTop: '0.4rem',
                        fontSize: '0.72rem',
                        fontStyle: 'italic',
                        color: 'var(--text-muted)',
                        background: 'var(--bg-cream)',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '2px',
                      }}
                    >
                      Field Notes: {action.operator_notes}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Action Execution Modal */}
          {activeModalAction && (
            <div
              className="modal-overlay"
              style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                background: 'rgba(31, 31, 31, 0.65)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                padding: '1rem',
              }}
            >
              <div
                className="panel"
                style={{
                  width: '100%',
                  maxWidth: '520px',
                  background: 'var(--bg-white)',
                  borderRadius: '4px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                  padding: '1.5rem',
                }}
              >
                <div className="panel-header" style={{ marginBottom: '1rem' }}>
                  <div>
                    <span className="badge badge-charcoal" style={{ fontSize: '0.7rem' }}>
                      {activeModalAction.id}
                    </span>
                    <h3 style={{ margin: '0.2rem 0', fontSize: '1.1rem' }}>Dispatch Anticipatory Action</h3>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem' }}
                    onClick={() => setActiveModalAction(null)}
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleExecuteAction}>
                  <div style={{ marginBottom: '0.75rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>Action:</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 700 }}>{activeModalAction.action_name}</div>
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <label htmlFor="select-target-status" style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                      Transition To Status:
                    </label>
                    <select
                      id="select-target-status"
                      value={targetStatus}
                      onChange={(e) => setTargetStatus(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '0.45rem',
                        fontSize: '0.85rem',
                        border: '1px solid var(--border-sand)',
                        borderRadius: '3px',
                      }}
                    >
                      <option value="MONITORING">MONITORING (Standby)</option>
                      <option value="READY">READY (Staged)</option>
                      <option value="TRIGGERED">TRIGGERED (Threshold Reached)</option>
                      <option value="EXECUTED">EXECUTED (Recorded Workflow State)</option>
                    </select>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.35rem', lineHeight: '1.3' }}>
                      Status records operational dispatch decisions in PostgreSQL. Physical field delivery is confirmed through separate monitoring channels.
                    </div>
                  </div>

                  <div style={{ marginBottom: '0.75rem' }}>
                    <label htmlFor="input-operator-name" style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                      Operator Name / Unit:
                    </label>
                    <input
                      id="input-operator-name"
                      type="text"
                      value={operatorName}
                      onChange={(e) => setOperatorName(e.target.value)}
                      required
                      style={{
                        width: '100%',
                        padding: '0.45rem',
                        fontSize: '0.85rem',
                        border: '1px solid var(--border-sand)',
                        borderRadius: '3px',
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: '1.25rem' }}>
                    <label htmlFor="textarea-operator-notes" style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                      Deployment Notes & Field Authorization:
                    </label>
                    <textarea
                      id="textarea-operator-notes"
                      rows={3}
                      value={operatorNotes}
                      onChange={(e) => setOperatorNotes(e.target.value)}
                      placeholder="e.g. Seed vouchers staged with Limpopo Agricultural Extension Directorate."
                      style={{
                        width: '100%',
                        padding: '0.45rem',
                        fontSize: '0.85rem',
                        border: '1px solid var(--border-sand)',
                        borderRadius: '3px',
                        fontFamily: 'inherit',
                      }}
                    />
                  </div>

                  {executionMessage && (
                    <div className="notice notice-info" style={{ marginBottom: '1rem', fontSize: '0.8rem' }}>
                      {executionMessage}
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setActiveModalAction(null)}
                      disabled={executing}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      data-testid="btn-modal-submit-execution"
                      className="btn btn-primary"
                      disabled={executing}
                    >
                      {executing ? 'Updating...' : `Confirm ${targetStatus}`}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
