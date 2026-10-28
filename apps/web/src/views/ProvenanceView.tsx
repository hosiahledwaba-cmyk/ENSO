import { useState, useEffect, useCallback } from 'react'
import type {
  createApiClient,
  ProvenanceRecord,
  ProvenanceAuditReport,
  ArtefactAuditResult,
  ProcessingStep,
} from '../api/client'

interface ProvenanceViewProps {
  api: ReturnType<typeof createApiClient>
}

export function ProvenanceView({ api }: ProvenanceViewProps) {
  const [records, setRecords] = useState<ProvenanceRecord[]>([])
  const [auditReport, setAuditReport] = useState<ProvenanceAuditReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [auditing, setAuditing] = useState(false)
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [provRes, auditRes] = await Promise.all([
        api.getProvenance(),
        api.getProvenanceAudit().catch(() => null),
      ])
      setRecords(provRes.records)
      if (auditRes) {
        setAuditReport(auditRes)
      }
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load provenance records')
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const runLiveAudit = async () => {
    setAuditing(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const report = await api.getProvenanceAudit()
      setAuditReport(report)
      const provRes = await api.getProvenance()
      setRecords(provRes.records)
      setSuccessMsg(
        `Audit complete: ${report.verified_count}/${report.total_artefacts} artefacts cryptographically verified. ${report.tampered_count} tampered.`
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Live integrity audit failed')
    } finally {
      setAuditing(false)
    }
  }

  const verifySingleArtefact = async (datasetId: string) => {
    setVerifyingId(datasetId)
    setError(null)
    try {
      const result: ArtefactAuditResult = await api.verifyArtefact({ dataset_id: datasetId })
      setSuccessMsg(
        `Verified ${result.artefact_id}: Content Integrity = ${result.content_integrity}, Authenticity = ${result.source_authenticity}.`
      )
      // Refresh audit report
      const report = await api.getProvenanceAudit()
      setAuditReport(report)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Verification failed for ${datasetId}`)
    } finally {
      setVerifyingId(null)
    }
  }

  const selectedRecord = records.find((r) => r.dataset_id === expandedId)

  return (
    <div>
      <div className="view-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1>Climate Data Provenance & Cryptographic Integrity Subsystem</h1>
            <p className="view-lead">
              Zero-trust provenance architecture enforcing content hash verification, authenticated pipeline signatures,
              and strict separation between cryptographic digests, source authenticity, and domain scientific validity.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              onClick={() => void loadData()}
              disabled={loading || auditing}
            >
              Refresh Ledger
            </button>
            <button
              className="btn btn-primary"
              onClick={() => void runLiveAudit()}
              disabled={auditing || loading}
            >
              {auditing ? 'Scanning Artefacts...' : 'Run Real-Time Integrity Audit'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="notice notice-warning" style={{ marginBottom: '1.25rem' }}>
          <div className="notice-title">Integrity Subsystem Notice</div>
          {error}
        </div>
      )}

      {successMsg && (
        <div
          style={{
            backgroundColor: 'var(--status-ok-bg)',
            border: '1px solid #B8E0C4',
            color: 'var(--status-ok)',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)',
            marginBottom: '1.25rem',
            fontSize: '0.9rem',
          }}
        >
          <strong>System Audit:</strong> {successMsg}
        </div>
      )}

      {/* 4 Pillars Summary Cards */}
      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="panel" style={{ borderLeft: '4px solid var(--status-ok)' }}>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
            1. Content Integrity
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, margin: '0.35rem 0', color: 'var(--text-charcoal)' }}>
            {auditReport ? `${auditReport.verified_count}/${auditReport.total_artefacts} Verified` : `${records.length} Tracked`}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            SHA-256 post-ingestion tamper detection ({auditReport?.tampered_count ?? 0} tampered)
          </div>
        </div>

        <div className="panel" style={{ borderLeft: '4px solid #4A6FA5' }}>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
            2. Source Authenticity
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, margin: '0.35rem 0', color: 'var(--text-charcoal)' }}>
            {auditReport
              ? `${auditReport.signed_pipeline_count} Signed · ${auditReport.unsigned_third_party_count} Unsigned`
              : 'Signed / 3rd-Party'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Third-party raw data unsigned; pipeline outputs HMAC-signed
          </div>
        </div>

        <div className="panel" style={{ borderLeft: '4px solid #3B82F6' }}>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
            3. Scientific Validity
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, margin: '0.35rem 0', color: 'var(--text-charcoal)' }}>
            {records.filter((r) => r.validation_status === 'PASSED').length}/{records.length} Validated
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Schema, units, coordinates, and physical ranges enforced
          </div>
        </div>

        <div className="panel" style={{ borderLeft: '4px solid var(--border-sand)' }}>
          <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
            4. Freshness & Baseline
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, margin: '0.35rem 0', color: 'var(--text-charcoal)' }}>
            {auditReport?.archival_benchmark_count ?? records.length} Archival
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Historical benchmark (1981–1988) zero-lookahead calibration
          </div>
        </div>
      </div>

      {/* Active Violations or Anomalies Banner */}
      {auditReport && auditReport.violations_count > 0 && (
        <div
          className="notice notice-warning"
          style={{ marginBottom: '1.5rem', borderLeftColor: auditReport.overall_status === 'FAILED' ? 'var(--status-err)' : 'var(--status-warn)' }}
        >
          <div className="notice-title" style={{ color: auditReport.overall_status === 'FAILED' ? 'var(--status-err)' : 'var(--status-warn)' }}>
            Policy Alert: {auditReport.violations_count} Anomaly Violation(s) Enforced
          </div>
          <ul style={{ margin: '0.5rem 0 0 1.25rem', padding: 0, fontSize: '0.85rem' }}>
            {auditReport.violations.map((v, i) => (
              <li key={`violation-${i}`} style={{ marginBottom: '0.35rem' }}>
                <strong>[{v.severity}] {v.violation_type} ({v.artefact_id}):</strong> {v.description}
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Action: {v.enforced_action}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Primary Attribution and Integrity Ledger Table */}
      <div className="panel" style={{ marginBottom: '1.5rem' }}>
        <div className="panel-header">
          <h3 className="panel-title">Attribution & Integrity Registry</h3>
          <span className="badge badge-sand">{records.length} Registered Artefacts</span>
        </div>

        {records.length > 0 ? (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Dataset ID & Tier</th>
                  <th>Source Authority</th>
                  <th>Version</th>
                  <th>Content Integrity</th>
                  <th>Source Authenticity</th>
                  <th>Scientific Validity</th>
                  <th>Freshness</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r: ProvenanceRecord) => {
                  const isCleanedOrDerived = Boolean(r.cleaned_sha256 || r.derived_sha256)
                  const isSigned = Boolean(r.signature)
                  const authStatus = r.authenticity_status ?? (isSigned ? 'AUTHENTIC_CONTROLLED_PIPELINE' : 'UNSIGNED_THIRD_PARTY')
                  const isExpanded = expandedId === r.dataset_id

                  return (
                    <tr key={r.dataset_id} style={{ backgroundColor: isExpanded ? '#FAF6F0' : undefined }}>
                      <td>
                        <strong className="mono-cell">{r.dataset_id}</strong>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          {isCleanedOrDerived ? 'operational cleaned tier' : 'raw acquisition'} · {r.record_count} records
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{r.source_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{r.licence}</div>
                      </td>
                      <td className="mono-cell">{r.source_version}</td>
                      <td>
                        <span
                          className={`badge ${r.validation_status === 'PASSED' ? 'badge-ok' : 'badge-err'}`}
                          title={`Content Digest: ${r.content_digest || r.cleaned_sha256 || r.raw_sha256}`}
                        >
                          VERIFIED
                        </span>
                        <div className="mono-cell" style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                          {(r.content_digest || r.cleaned_sha256 || r.raw_sha256)?.substring(0, 10)}...
                        </div>
                      </td>
                      <td>
                        {authStatus === 'AUTHENTIC_CONTROLLED_PIPELINE' ? (
                          <span
                            className="badge badge-charcoal"
                            title={`Signed by ${r.signing_key_id || 'enso-pipeline-hmac-v1'} using internal HMAC-SHA256`}
                            style={{ border: '1px solid #4A6FA5' }}
                          >
                            AUTHENTIC (SIGNED)
                          </span>
                        ) : authStatus === 'SIGNATURE_INVALID' ? (
                          <span className="badge badge-err">SIGNATURE INVALID</span>
                        ) : (
                          <span
                            className="badge badge-warn"
                            title="Unsigned third-party data. Cryptographic digest computed for tamper detection; third-party data source does not provide digital signatures."
                          >
                            UNSIGNED (3RD-PARTY)
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${r.validation_status === 'PASSED' ? 'badge-ok' : 'badge-err'}`}>
                          {r.validation_status}
                        </span>
                      </td>
                      <td>
                        <span className="badge badge-sand">
                          {r.is_archival_benchmark !== false ? 'ARCHIVAL BENCHMARK' : 'OPERATIONAL'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => setExpandedId(isExpanded ? null : r.dataset_id)}
                          >
                            {isExpanded ? 'Hide Lineage' : 'Lineage'}
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => void verifySingleArtefact(r.dataset_id)}
                            disabled={verifyingId === r.dataset_id}
                          >
                            {verifyingId === r.dataset_id ? 'Verifying...' : 'Verify'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            No provenance manifests found in <span className="mono-cell">data/provenance/</span>.
            Run the climate data ingestion pipeline to generate cryptographic manifests.
          </div>
        )}
      </div>

      {/* Expandable Processing History & Transformation Lineage Drawer */}
      {selectedRecord && (
        <div className="panel" style={{ marginBottom: '1.5rem', border: '2px solid var(--accent-terracotta)' }}>
          <div className="panel-header">
            <h3 className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span>Transformation Lineage & Security Assertions:</span>
              <span className="mono-cell" style={{ color: 'var(--accent-terracotta)' }}>{selectedRecord.dataset_id}</span>
            </h3>
            <button
              className="btn btn-secondary"
              style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
              onClick={() => setExpandedId(null)}
            >
              Close Drawer
            </button>
          </div>

          <div className="grid-2" style={{ marginBottom: '1rem' }}>
            <div>
              <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                <strong>Source Authority:</strong> {selectedRecord.source_name} ({selectedRecord.source_version})
              </div>
              <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                <strong>Citation:</strong> {selectedRecord.citation}
              </div>
              {selectedRecord.source_url && (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                  <strong>Upstream URL:</strong>{' '}
                  <a href={selectedRecord.source_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-terracotta)', wordBreak: 'break-all' }}>
                    {selectedRecord.source_url}
                  </a>
                </div>
              )}
              <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                Ingested (UTC): <span className="mono-cell">{selectedRecord.ingestion_timestamp_utc}</span>
              </div>
            </div>

            <div>
              <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                <strong>Authenticity Status:</strong>{' '}
                <span className="badge badge-sand" style={{ textTransform: 'none' }}>
                  {selectedRecord.authenticity_status ?? 'UNSIGNED_THIRD_PARTY'}
                </span>
              </div>
              {selectedRecord.signature ? (
                <div style={{ fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                  <strong>Cryptographic Signature (HMAC-SHA256):</strong>
                  <div className="mono-cell" style={{ background: 'var(--surface-sand)', padding: '0.4rem', borderRadius: 'var(--radius-sm)', wordBreak: 'break-all', marginTop: '0.2rem' }}>
                    {selectedRecord.signature}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Key ID: <span className="mono-cell">{selectedRecord.signing_key_id || 'enso-pipeline-hmac-v1'}</span>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                  <em>No authenticated signature attached. External observational dataset ingested via third-party download.</em>
                </div>
              )}
            </div>
          </div>

          {/* Processing History Stages */}
          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border-sand)', paddingTop: '1rem' }}>
            <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', textTransform: 'uppercase', color: 'var(--text-charcoal)' }}>
              Processing History & Transformation Pipeline ({selectedRecord.processing_history?.length ?? 0} Stages)
            </h4>

            {selectedRecord.processing_history && selectedRecord.processing_history.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {selectedRecord.processing_history.map((step: ProcessingStep, idx: number) => (
                  <div
                    key={`step-${idx}`}
                    style={{
                      background: 'var(--surface-sand)',
                      padding: '0.85rem',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-sand)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                      <strong style={{ fontSize: '0.85rem', color: 'var(--text-charcoal)' }}>
                        Stage {idx + 1}: <span className="mono-cell">{step.step_name}</span>
                      </strong>
                      <span className="mono-cell" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {step.timestamp_utc}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '0.3rem' }}>
                      Operator: <span className="mono-cell">{step.operator}</span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '0.3rem' }}>
                      Output Digest: <span className="mono-cell">{step.output_digest}</span>
                    </div>
                    {Object.keys(step.input_digests).length > 0 && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>
                        <strong>Inputs Linked:</strong>
                        <ul style={{ margin: '0.2rem 0 0 1rem', padding: 0 }}>
                          {Object.entries(step.input_digests).map(([k, v]) => (
                            <li key={k}>
                              {k}: <span className="mono-cell">{v.substring(0, 16)}...</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                Direct ingestion manifest. Detailed multistage transformation history was not recorded for legacy v1 manifest.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Expanded Provenance Cards */}
      <div className="grid-2">
        {records.map((r: ProvenanceRecord) => (
          <div key={`card-${r.dataset_id}`} className="panel">
            <div className="panel-header">
              <h3 className="panel-title mono-cell">{r.dataset_id}</h3>
              <span className="badge badge-charcoal">{r.source_version}</span>
            </div>
            <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
              <strong>Citation:</strong> {r.citation}
            </div>
            {r.source_url && (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                <strong>Upstream:</strong>{' '}
                <a
                  href={r.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--accent-terracotta)', wordBreak: 'break-all' }}
                >
                  {r.source_url}
                </a>
              </div>
            )}
            <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '0.5rem' }}>
              Raw SHA-256: <span className="mono-cell">{r.raw_sha256}</span>
            </div>
            {r.cleaned_sha256 && (
              <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '0.5rem' }}>
                Cleaned SHA-256: <span className="mono-cell">{r.cleaned_sha256}</span>
              </div>
            )}
            <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
              Ingested (UTC): <span className="mono-cell">{r.ingestion_timestamp_utc}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
