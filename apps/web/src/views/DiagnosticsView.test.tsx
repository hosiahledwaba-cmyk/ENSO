import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DiagnosticsView } from './DiagnosticsView'
import type { createApiClient, SystemStatus, SimulationReportItem } from '../api/client'

const mockStatus: SystemStatus = {
  service: 'enso-shield-api',
  version: '0.1.0',
  environment: 'development',
  timestamp_utc: '2026-10-28T04:00:00Z',
  database: {
    status: 'connected',
    latency_ms: 1.2,
  },
  pipelines: {
    datasets_operational: true,
    features_operational: true,
    active_model_operational: true,
    latest_experiment_operational: true,
  },
  active_jobs: [],
}

const mockBenchmarks: SimulationReportItem = {
  timestamp_utc: '2026-10-28T02:00:00Z',
  random_seed: 42,
  total_scenarios_evaluated: 5,
  mean_attack_detection_rate: 0.85,
  mean_false_positive_rate: 0.0,
  mean_recovery_efficiency: 0.92,
  scenarios: [
    {
      scenario: 'ADVERSARIAL_FDI',
      seed: 42,
      target_feature: 'oni_aso_degc',
      total_samples: 7,
      injected_samples: 2,
      detected_samples: 2,
      clean_samples: 5,
      false_alarms: 0,
      attack_detection_rate: 1.0,
      false_positive_rate: 0.0,
      detection_delay_timesteps: 0.0,
      clean_brier_score: 0.1257,
      attack_brier_score: 0.1857,
      defended_brier_score: 0.1224,
      brier_score_degradation: 0.06,
      defensive_recovery_efficiency: 1.0,
      mean_probability_shift: 0.05,
      risk_category_flips: 0,
      ground_truth_labels: [1, 0, 0, 0, 0, 1, 0],
      detector_flags: [true, false, false, false, false, true, false],
      detector_classifications: ['POTENTIAL_ADVERSARIAL_PERTURBATION', 'CLEAN_BENCHMARK', 'CLEAN_BENCHMARK', 'CLEAN_BENCHMARK', 'CLEAN_BENCHMARK', 'POTENTIAL_ADVERSARIAL_PERTURBATION', 'CLEAN_BENCHMARK'],
      summary: 'ADVERSARIAL_FDI ADR=100%, FPR=0%',
    },
  ],
}

describe('DiagnosticsView', () => {
  it('renders defensive anomaly screening and simulation metrics by default', async () => {
    const mockApi = {
      getSystemStatus: vi.fn().mockResolvedValue(mockStatus),
      getJobs: vi.fn().mockResolvedValue({ jobs: [], count: 0 }),
      getDefenseScenarios: vi.fn().mockResolvedValue({
        scenarios: [
          {
            id: 'ADVERSARIAL_FDI',
            name: 'Stealthy False Data Injection (FDI)',
            category: 'Adversarial Cyber-Attack',
            description: 'Targeted perturbations',
            threat_model_ref: 'Protocol 4.1',
            default_magnitude: 1.0,
            default_ratio: 0.35,
          },
        ],
        protocol_reference: 'Protocol 4.1',
        total_scenarios: 1,
      }),
      getDefenseBenchmarks: vi.fn().mockResolvedValue(mockBenchmarks),
      simulateDefenseScenario: vi.fn().mockResolvedValue(mockBenchmarks.scenarios[0]),
      inspectDefenseTelemetry: vi.fn().mockResolvedValue({
        series_id: 'live_test_clean',
        total_records: 3,
        passed: true,
        anomaly_count: 0,
        anomalies: [],
        check_summaries: [],
        baseline_detector_score: null,
        overall_classification: 'CLEAN_BENCHMARK',
        summary: 'Defensive screening passed for stream.',
      }),
    } as unknown as ReturnType<typeof createApiClient>

    render(<DiagnosticsView api={mockApi} apiBaseUrl="http://localhost:8000" />)

    await waitFor(() => {
      expect(screen.getByText(/Defensive Telemetry Intelligence/i)).toBeInTheDocument()
      expect(screen.getByText(/Non-Malicious Epistemic Guardrail/i)).toBeInTheDocument()
    })

    // Verify benchmark stat cards rendered
    expect(screen.getByText('85.0%')).toBeInTheDocument() // Mean ADR
    expect(screen.getAllByText(/0\.0%/).length).toBeGreaterThanOrEqual(1) // Mean FPR
    expect(screen.getByText('92.0%')).toBeInTheDocument() // Mean RE

    // Verify transparent checks table
    expect(screen.getByText(/1. Impossible Values/i)).toBeInTheDocument()
    expect(screen.getByText(/6. Cross-Source Coherence/i)).toBeInTheDocument()
    expect(screen.getByText(/7. Baseline Multivariate Detector/i)).toBeInTheDocument()
  })

  it('switches between Defense and System tabs', async () => {
    const user = userEvent.setup()
    const mockApi = {
      getSystemStatus: vi.fn().mockResolvedValue(mockStatus),
      getJobs: vi.fn().mockResolvedValue({ jobs: [], count: 0 }),
      getDefenseScenarios: vi.fn().mockResolvedValue({ scenarios: [], total_scenarios: 0, protocol_reference: '' }),
      getDefenseBenchmarks: vi.fn().mockResolvedValue(null),
    } as unknown as ReturnType<typeof createApiClient>

    render(<DiagnosticsView api={mockApi} apiBaseUrl="http://localhost:8000" />)

    await waitFor(() => {
      expect(screen.getByText(/Container Telemetry & Jobs/i)).toBeInTheDocument()
    })

    // Click container telemetry tab
    await user.click(screen.getByText(/Container Telemetry & Jobs/i))

    expect(screen.getByText(/FastAPI Service Metadata/i)).toBeInTheDocument()
    expect(screen.getByText(/PostgreSQL Container State/i)).toBeInTheDocument()
    expect(screen.getByText(/Job Execution Audit History/i)).toBeInTheDocument()
  })
})
