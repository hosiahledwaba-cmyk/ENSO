import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  SecurityIncidentsResponse,
  SecuritySummaryResponse,
  SecurityIncidentItem,
} from '../api/client'
import { EpistemicBadge } from '../components/EpistemicBadge'

interface SecurityIncidentViewProps {
  api: ReturnType<typeof createApiClient>
}

export function SecurityIncidentView({ api }: SecurityIncidentViewProps) {
  const [incidentsData, setIncidentsData] = useState<SecurityIncidentsResponse | null>(null)
  const [summaryData, setSummaryData] = useState<SecuritySummaryResponse | null>(null)
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL')
  const [selectedSubsystem, setSelectedSubsystem] = useState<string>('ALL')
  const [selectedClassification, setSelectedClassification] = useState<string>('ALL')
  const [selectedIncident, setSelectedIncident] = useState<SecurityIncidentItem | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const loadSecurityData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [incidents, summary] = await Promise.all([
        api.getSecurityIncidents(),
        api.getSecuritySummary().catch(() => null),
      ])
      setIncidentsData(incidents)
      if (summary) setSummaryData(summary)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load security incident telemetry')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadSecurityData()
  }, [loadSecurityData])

  const filteredIncidents = (incidentsData?.incidents ?? []).filter((inc) => {
    if (selectedSeverity !== 'ALL' && inc.severity !== selectedSeverity) return false
    if (selectedSubsystem !== 'ALL' && inc.subsystem !== selectedSubsystem) return false
    if (selectedClassification !== 'ALL' && inc.epistemic_classification !== selectedClassification) return false
    return true
  })

  return (
    <div className="security-incident-view-shell" data-testid="security-incident-view">
      {/* Top Header */}
      <div className="view-header" style={{ marginBottom: '1.25rem' }}>
        <h1 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span>Security Incident Centre &amp; Data-Trust Telemetry</span>
          <span
            className={`badge ${
              summaryData?.overall_posture === 'HEALTHY'
                ? 'badge-ok'
                : summaryData?.overall_posture === 'DEGRADED'
                  ? 'badge-warn'
                  : 'badge-err'
            }`}
            style={{ fontSize: '0.75rem' }}
          >
            {summaryData?.overall_posture || 'HEALTHY'} POSTURE
          </span>
        </h1>
        <p className="view-lead">
          Continuous cryptographic integrity auditing, automated artefact quarantine logging, defensive ingestion
          screening alerts, and isolated adversarial perturbation verification.
        </p>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.25rem' }}>
          <div className="notice-title">Security Telemetry Notice</div>
          {error}
        </div>
      )}

      {loading && !incidentsData && (
        <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          <span className="status-dot status-dot--green" style={{ display: 'inline-block', marginRight: '0.5rem' }} />
          Loading security incident ledger from ENSO Shield API...
        </div>
      )}

      {/* Top Resilience & Trust Metrics */}
      {summaryData && (
        <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
          <div className="metric-card">
            <div className="metric-label">Data Trust Index</div>
            <div
              className="metric-value"
              style={{
                color: summaryData.data_trust_index >= 90 ? 'var(--status-ok)' : 'var(--accent-terracotta)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {summaryData.data_trust_index}/100
            </div>
            <div className="metric-sub">Cryptographic content integrity score</div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Quarantined Artefacts</div>
            <div
              className="metric-value"
              style={{
                color: summaryData.active_quarantined_models > 0 ? 'var(--status-err)' : 'var(--status-ok)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {summaryData.active_quarantined_models}
            </div>
            <div className="metric-sub">Suspect models quarantined from inference</div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Operational Gates</div>
            <div className="metric-value" style={{ color: 'var(--status-ok)' }}>
              {summaryData.subsystem_gates.length} ACTIVE
            </div>
            <div className="metric-sub">Pre-load, provenance, screening &amp; poisoning</div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Audited Incidents</div>
            <div className="metric-value" style={{ fontFamily: 'var(--font-mono)' }}>
              {incidentsData?.total_count || 0}
            </div>
            <div className="metric-sub">Total operational &amp; simulation events</div>
          </div>
        </div>
      )}

      {/* Epistemic Boundary Notice */}
      <div
        className="notice notice-warning"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          marginBottom: '1.5rem',
          background: 'var(--bg-cream)',
          borderLeft: '4px solid var(--accent-amber)',
        }}
      >
        <span style={{ fontSize: '1.25rem' }}>⚠️</span>
        <div style={{ fontSize: '0.8rem', lineHeight: 1.4 }}>
          <strong>Epistemic Demarcation Rule:</strong> Simulated adversarial perturbations (e.g. Label Flipping,
          False Data Injection benchmarks) are clearly labeled with the{' '}
          <span className="badge badge-warn" style={{ fontSize: '0.65rem' }}>SIMULATED EXPERIMENT</span> badge.
          Under scientific integrity protocol RD-015, simulated results are strictly isolated and never classified or
          displayed as live operational climate forecasts.
        </div>
      </div>

      {/* Subsystem Security Gates Status Row */}
      {summaryData && (
        <div className="panel" style={{ marginBottom: '1.5rem', background: 'var(--bg-cream)' }}>
          <div className="panel-header" style={{ marginBottom: '0.6rem' }}>
            <h3 className="panel-title" style={{ margin: 0, fontSize: '0.95rem' }}>Subsystem Defense-in-Depth Gates</h3>
            <span className="badge badge-ok">100% COVERAGE</span>
          </div>
          <div className="grid-4" style={{ gap: '0.6rem' }}>
            {summaryData.subsystem_gates.map((g) => (
              <div
                key={g.subsystem}
                style={{
                  padding: '0.6rem',
                  background: 'var(--bg-white)',
                  borderRadius: '3px',
                  border: '1px solid var(--border-sand)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700 }}>{g.subsystem}</span>
                  <span className="badge badge-ok" style={{ fontSize: '0.65rem' }}>
                    {g.status}
                  </span>
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.3 }}>
                  {g.gate_type}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
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
        {/* Subsystem Filters */}
        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.2rem' }}>
            SUBSYSTEM:
          </span>
          {['ALL', 'MODEL_ARTEFACT', 'DATA_PROVENANCE', 'DEFENSE_SCREENING', 'SIMULATION'].map((sub) => (
            <button
              key={sub}
              type="button"
              data-testid={`filter-subsystem-${sub.toLowerCase()}`}
              className={`btn ${selectedSubsystem === sub ? 'btn-primary' : 'btn-secondary'}`}
              style={{ fontSize: '0.7rem', padding: '0.25rem 0.5rem' }}
              onClick={() => setSelectedSubsystem(sub)}
            >
              {sub.replace('_', ' ')}
            </button>
          ))}
        </div>

        {/* Severity Filters */}
        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.2rem' }}>
            SEVERITY:
          </span>
          {['ALL', 'CRITICAL', 'WARNING', 'INFO'].map((sev) => (
            <button
              key={sev}
              type="button"
              data-testid={`filter-severity-${sev.toLowerCase()}`}
              className={`btn ${selectedSeverity === sev ? 'btn-primary' : 'btn-secondary'}`}
              style={{ fontSize: '0.7rem', padding: '0.25rem 0.5rem' }}
              onClick={() => setSelectedSeverity(sev)}
            >
              {sev}
            </button>
          ))}
        </div>

        {/* Classification Filter */}
        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.2rem' }}>
            TYPE:
          </span>
          {['ALL', 'OPERATIONAL_TELEMETRY', 'SIMULATED_EXPERIMENT'].map((cls) => (
            <button
              key={cls}
              type="button"
              data-testid={`filter-class-${cls.toLowerCase()}`}
              className={`btn ${selectedClassification === cls ? 'btn-primary' : 'btn-secondary'}`}
              style={{ fontSize: '0.7rem', padding: '0.25rem 0.5rem' }}
              onClick={() => setSelectedClassification(cls)}
            >
              {cls === 'ALL' ? 'ALL' : cls === 'OPERATIONAL_TELEMETRY' ? 'OPERATIONAL' : 'SIMULATION'}
            </button>
          ))}
        </div>
      </div>

      {/* Incidents Stream Table */}
      <div className="panel" style={{ marginBottom: '1.5rem', overflowX: 'auto' }}>
        <table className="data-table" style={{ width: '100%', fontSize: '0.8rem' }}>
          <thead>
            <tr>
              <th>ID &amp; Timestamp</th>
              <th>Severity</th>
              <th>Subsystem &amp; Title</th>
              <th>Epistemic Type</th>
              <th>Detection Rule</th>
              <th>Remediation</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredIncidents.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                  No security incidents match the selected filter criteria.
                </td>
              </tr>
            ) : (
              filteredIncidents.map((inc) => (
                <tr key={inc.id} data-testid={`incident-row-${inc.id.toLowerCase()}`}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>
                    <div style={{ fontWeight: 600 }}>{inc.id}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {new Date(inc.timestamp).toLocaleTimeString()}
                    </div>
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        inc.severity === 'CRITICAL'
                          ? 'badge-err'
                          : inc.severity === 'WARNING'
                            ? 'badge-warn'
                            : 'badge-ok'
                      }`}
                      style={{ fontSize: '0.68rem' }}
                    >
                      {inc.severity}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text-charcoal)' }}>{inc.title}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {inc.subsystem.replace('_', ' ')} · {inc.affected_asset}
                    </div>
                  </td>
                  <td>
                    <EpistemicBadge
                      classification={inc.epistemic_classification}
                      label={inc.epistemic_classification === 'SIMULATED_EXPERIMENT' ? 'SIMULATION' : 'OPERATIONAL'}
                    />
                  </td>
                  <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {inc.detection_rule}
                  </td>
                  <td>
                    <span className="badge badge-sand" style={{ fontSize: '0.68rem' }}>
                      {inc.remediation_status}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      data-testid={`btn-inspect-${inc.id.toLowerCase()}`}
                      className="btn btn-secondary"
                      style={{ fontSize: '0.7rem', padding: '0.2rem 0.5rem' }}
                      onClick={() => setSelectedIncident(inc)}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Incident Details Inspection Drawer */}
      {selectedIncident && (
        <div
          className="panel"
          data-testid="incident-detail-drawer"
          style={{
            background: 'var(--bg-cream)',
            borderLeft: '4px solid var(--accent-terracotta)',
            marginBottom: '1.5rem',
            padding: '1.25rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
            <div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.35rem' }}>
                <span className="badge badge-charcoal">{selectedIncident.id}</span>
                <span
                  className={`badge ${
                    selectedIncident.severity === 'CRITICAL'
                      ? 'badge-err'
                      : selectedIncident.severity === 'WARNING'
                        ? 'badge-warn'
                        : 'badge-ok'
                  }`}
                >
                  {selectedIncident.severity}
                </span>
                <EpistemicBadge classification={selectedIncident.epistemic_classification} />
              </div>
              <h3 style={{ margin: 0, fontSize: '1.15rem' }}>{selectedIncident.title}</h3>
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: '0.75rem' }}
              onClick={() => setSelectedIncident(null)}
            >
              Close Details ✕
            </button>
          </div>

          <p style={{ fontSize: '0.85rem', color: 'var(--text-charcoal)', lineHeight: 1.45, marginBottom: '0.75rem' }}>
            {selectedIncident.description}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.6rem', fontSize: '0.75rem', marginBottom: '0.75rem' }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Detection Rule: </span>
              <strong>{selectedIncident.detection_rule}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Affected Asset: </span>
              <strong>{selectedIncident.affected_asset}</strong>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Remediation Status: </span>
              <strong>{selectedIncident.remediation_status}</strong>
            </div>
          </div>

          {/* Technical Details JSON View */}
          <div style={{ marginTop: '0.5rem' }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              TECHNICAL AUDIT ATTRIBUTES:
            </span>
            <pre
              style={{
                background: '#1F1F1F',
                color: '#F7F4EF',
                padding: '0.75rem',
                borderRadius: '3px',
                fontSize: '0.72rem',
                fontFamily: 'var(--font-mono)',
                overflowX: 'auto',
                marginTop: '0.25rem',
              }}
            >
              {JSON.stringify(selectedIncident.technical_details, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
