import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SecurityIncidentView } from './SecurityIncidentView'
import type {
  createApiClient,
  SecurityIncidentsResponse,
  SecuritySummaryResponse,
} from '../api/client'

const mockSummary = (): SecuritySummaryResponse => ({
  overall_posture: 'HEALTHY',
  data_trust_index: 98,
  active_quarantined_models: 0,
  subsystem_gates: [
    {
      subsystem: 'Model Artefacts',
      gate_type: 'Streaming SHA-256 & Manifest v2.0 Verification',
      status: 'HEALTHY',
    },
    {
      subsystem: 'Data Provenance',
      gate_type: 'Cryptographic Content Hash & HMAC Signature Verification',
      status: 'HEALTHY',
    },
    {
      subsystem: 'Defensive Ingestion Screening',
      gate_type: '6 Transparent Physical Checks + Mahalanobis Envelope',
      status: 'ACTIVE',
    },
    {
      subsystem: 'Training Poisoning Resilience',
      gate_type: 'Isolated Scratch Harness & Post-Run Checksum Invariance',
      status: 'BENCHMARKED',
    },
  ],
  epistemic_rules_enforced: [
    'Raw third-party data is strictly classified as unsigned third-party data.',
    'Simulated adversarial tests are strictly marked with SIMULATED_EXPERIMENT badges.',
  ],
  last_audit_timestamp_utc: '2026-10-28T03:00:00Z',
})

const mockIncidents = (): SecurityIncidentsResponse => ({
  status: 'operational',
  total_count: 2,
  epistemic_notice: 'SECURITY INCIDENT LOG',
  incidents: [
    {
      id: 'INC_PROV_001',
      timestamp: '2026-10-28T01:30:00Z',
      severity: 'INFO',
      subsystem: 'DATA_PROVENANCE',
      title: 'Cryptographic Content Digest Verified: CHIRPS Precipitation',
      description: 'Automated SHA-256 integrity scan completed. Content matches registered manifest.',
      detection_rule: 'ProvenanceAuditor SHA-256 Digest Verification',
      affected_asset: 'data/cleaned/chirps_rainfall_monthly.csv',
      remediation_status: 'RESOLVED',
      epistemic_classification: 'OPERATIONAL_TELEMETRY',
      technical_details: {
        sha256: '4e7236d6eaee1a5264b301712a447c23a07ffce671df46497fba11b81665a3d7',
      },
    },
    {
      id: 'INC_SIM_001',
      timestamp: '2026-10-28T03:15:00Z',
      severity: 'WARNING',
      subsystem: 'SIMULATION',
      title: 'Controlled Poisoning Test: Label Flipping Injection',
      description: 'Isolated training dataset copy subjected to 20% drought target flipping.',
      detection_rule: 'TrainingPoisoningHarness',
      affected_asset: 'scratch/poisoning_benchmarks/pois_label_flipping',
      remediation_status: 'SIMULATION_COMPLETE',
      epistemic_classification: 'SIMULATED_EXPERIMENT',
      technical_details: {
        delta_brier_score: -0.1994,
        epistemic_boundary: 'Isolated scratch run only. Zero modification to production data.',
      },
    },
  ],
})

describe('SecurityIncidentView Centre & Trust Telemetry', () => {
  it('renders posture banner, data trust index, and incident stream with epistemic tags', async () => {
    const mockApi = {
      getSecurityIncidents: vi.fn().mockResolvedValue(mockIncidents()),
      getSecuritySummary: vi.fn().mockResolvedValue(mockSummary()),
    } as unknown as ReturnType<typeof createApiClient>

    render(<SecurityIncidentView api={mockApi} />)

    await waitFor(() => {
      expect(
        screen.getByText('Security Incident Centre & Data-Trust Telemetry'),
      ).toBeInTheDocument()
    })

    // Verify Data Trust Index
    expect(screen.getByText('98/100')).toBeInTheDocument()
    expect(screen.getByText('HEALTHY POSTURE')).toBeInTheDocument()

    // Verify operational incident
    expect(
      screen.getByText('Cryptographic Content Digest Verified: CHIRPS Precipitation'),
    ).toBeInTheDocument()

    // Verify simulated experiment is clearly distinguished
    expect(
      screen.getByText('Controlled Poisoning Test: Label Flipping Injection'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('epistemic-badge-simulated_experiment')).toBeInTheDocument()
  })

  it('filters incidents and opens inspection drawer', async () => {
    const mockApi = {
      getSecurityIncidents: vi.fn().mockResolvedValue(mockIncidents()),
      getSecuritySummary: vi.fn().mockResolvedValue(mockSummary()),
    } as unknown as ReturnType<typeof createApiClient>

    render(<SecurityIncidentView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByTestId('btn-inspect-inc_sim_001')).toBeInTheDocument()
    })

    // Click inspect on simulation incident
    await userEvent.click(screen.getByTestId('btn-inspect-inc_sim_001'))

    // Verify drawer opened
    expect(screen.getByTestId('incident-detail-drawer')).toBeInTheDocument()
    expect(screen.getByText(/TECHNICAL AUDIT ATTRIBUTES/)).toBeInTheDocument()
    expect(screen.getByText(/Isolated scratch run only/)).toBeInTheDocument()

    // Close drawer
    await userEvent.click(screen.getByText('Close Details ✕'))
    expect(screen.queryByTestId('incident-detail-drawer')).not.toBeInTheDocument()
  })
})
