import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ExperimentsView } from './ExperimentsView'
import type { createApiClient, ExperimentManifest } from '../api/client'

describe('ExperimentsView Reliability & Error Handling', () => {
  it('renders useful empty state when no experiment manifest exists (404)', async () => {
    const mockApi = {
      getLatestExperiment: vi.fn().mockRejectedValue(new Error('Experiment manifest not found (404)')),
      startExperimentJob: vi.fn(),
      getJob: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ExperimentsView api={mockApi} />)

    // Should not crash to a blank screen!
    expect(screen.getByText(/Model Evaluation & Scientific Benchmarks/i)).toBeInTheDocument()

    // Should display the error/empty notice and CTA
    await waitFor(() => {
      expect(screen.getByText(/No Multi-Model Benchmark Manifest Generated/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Execute Benchmark Experiment Suite Now/i })).toBeInTheDocument()
    })
  })

  it('renders visible error state with retry action on network failure', async () => {
    const mockApi = {
      getLatestExperiment: vi.fn().mockRejectedValue(new Error('Failed to connect to backend')),
      startExperimentJob: vi.fn(),
      getJob: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ExperimentsView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to connect to backend/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Retry Loading/i })).toBeInTheDocument()
    })
  })

  it('renders gracefully when manifest has incomplete or missing fields without blanking', async () => {
    // Malformed manifest missing rolling_origin_cv, holdout_evaluation, etc.
    const malformedManifest = {
      manifest_version: '1.0.0',
      experiment_id: 'test_empty',
      timestamp_utc: '2026-10-28',
      random_seed: 42,
      software_versions: {},
      dataset_fingerprint_sha256: 'abc',
      training_seasons: [],
      holdout_seasons: [],
      feature_columns: [],
      // missing rolling_origin_cv, holdout_evaluation, ablation_report, verdict
    } as unknown as ExperimentManifest

    const mockApi = {
      getLatestExperiment: vi.fn().mockResolvedValue(malformedManifest),
      startExperimentJob: vi.fn(),
      getJob: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ExperimentsView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByText(/Model Evaluation & Scientific Benchmarks/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Run Experiment Suite/i })).toBeInTheDocument()
    })
  })

  it('allows clicking retry button to trigger a fresh load', async () => {
    const mockGet = vi.fn().mockRejectedValue(new Error('Temporary timeout'))
    const mockApi = {
      getLatestExperiment: mockGet,
      startExperimentJob: vi.fn(),
      getJob: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ExperimentsView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Retry Loading/i })).toBeInTheDocument()
    })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /Retry Loading/i }))

    expect(mockGet).toHaveBeenCalledTimes(2)
  })
})
