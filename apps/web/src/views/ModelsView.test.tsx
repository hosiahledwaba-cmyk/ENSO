import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModelsView } from './ModelsView'
import type { createApiClient, ActiveModelResponse } from '../api/client'

describe('ModelsView Artefact Integrity & Poisoning Resilience', () => {
  const mockActiveModel: ActiveModelResponse = {
    model_id: 'enso_logistic_baseline',
    model_architecture: 'regularized_logistic_regression',
    model_version: '1.0.0',
    target_variable: 'target_drought_p20',
    dataset_fingerprint: '3a4b5c6d7e8f',
    training_seasons: [1982, 1983, 1984],
    holdout_seasons: [2004, 2005],
    feature_columns: ['oni_aso_degc', 'precip_oct_zscore'],
    coefficients: { oni_aso_degc: 0.95, precip_oct_zscore: -0.72 },
    intercept: -0.85,
    baseline_metrics: { brier_score: 0.04 },
    logistic_metrics: { brier_score: 0.18, brier_skill_score: -0.25 },
    holdout_superiority_confirmed: false,
    scientific_notice: 'Evaluated using chronological rolling-origin and holdout period.',
    approval_status: 'APPROVED',
    artefact_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
    training_data_fingerprint: '3a4b5c6d7e8f',
  }

  const mockApi = {
    getActiveModel: vi.fn().mockResolvedValue(mockActiveModel),
    auditModels: vi.fn().mockResolvedValue({
      audit_timestamp_utc: true,
      total_scanned: 1,
      passed_count: 1,
      compromised_count: 0,
      quarantined_count: 0,
      posture: 'HEALTHY',
      models: [
        {
          model_id: 'logistic_regression_baseline',
          model_dir: 'models/logistic_regression_baseline',
          manifest_found: true,
          model_version: '1.0.0',
          approval_status: 'APPROVED',
          is_approved: true,
          artefact_found: true,
          expected_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
          observed_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
          digest_matches: true,
          feature_count: 10,
          quarantined: false,
          audit_passed: true,
          issues: [],
        },
      ],
      quarantined_dossiers: [],
    }),
    listQuarantinedModels: vi.fn().mockResolvedValue({ quarantined_models: [], count: 0 }),
    verifyModelIntegrity: vi.fn().mockResolvedValue({
      model_dir: 'models/logistic_regression_baseline',
      audit: {
        expected_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
        digest_matches: true,
        issues: [],
      },
      verified: true,
    }),
    quarantineModel: vi.fn(),
    replaceQuarantinedModel: vi.fn(),
    getPoisoningScenarios: vi.fn().mockResolvedValue({
      scenarios: [
        {
          attack_class: 'LABEL_FLIPPING',
          name: 'Label Flipping (Drought Alert Suppression)',
          description: 'Flips positive drought targets 1 -> 0',
          parameters: {},
          tested_threat: 'Manipulation of severe drought labels',
        },
      ],
      threat_limitations: ['Linear models vulnerable to leverage outliers'],
      recovery_protocol: ['Quarantine suspect artefact immediately'],
    }),
    evaluatePoisoningExperiment: vi.fn(),
    startTrainingJob: vi.fn(),
    getJob: vi.fn(),
  } as unknown as ReturnType<typeof createApiClient>

  it('renders model manifest v2.0 fields including approval status and artefact digest', async () => {
    render(<ModelsView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByText(/Climate Model Registry & Tampering Defenses/i)).toBeInTheDocument()
      expect(screen.getByText('APPROVED')).toBeInTheDocument()
      expect(screen.getByText(/b1a11d44ac764aaa/i)).toBeInTheDocument()
    })
  })

  it('switches between Overview, Integrity & Quarantine, and Poisoning Harness tabs', async () => {
    const user = userEvent.setup()
    render(<ModelsView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Artefact Integrity & Quarantine/i })).toBeInTheDocument()
    })

    // Click Integrity tab
    await user.click(screen.getByRole('button', { name: /Artefact Integrity & Quarantine/i }))
    await waitFor(() => {
      expect(screen.getByText(/Active Operational Model Integrity Status/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Verify Artefact Integrity Now/i })).toBeInTheDocument()
    })

    // Click Poisoning Harness tab
    await user.click(screen.getByRole('button', { name: /Training Poisoning Resilience Harness/i }))
    await waitFor(() => {
      expect(screen.getByText(/Isolated Poisoning Attack Simulator/i)).toBeInTheDocument()
      expect(screen.getByText(/Adversarial Threat Boundaries & Defense Limitations/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Run Isolated Poisoning Test/i })).toBeInTheDocument()
    })
  })
})
