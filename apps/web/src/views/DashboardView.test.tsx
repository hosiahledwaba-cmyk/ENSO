import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DashboardView } from './DashboardView'
import type {
  createApiClient,
  RegionalForecastDashboardResponse,
  HistoricalComparisonsResponse,
} from '../api/client'

const mockRegionalForecast = (): RegionalForecastDashboardResponse => ({
  status: 'operational',
  issue_year: 2026,
  convective_season: 'DJF 2025/26',
  forecast_issue_date: '2025-11-01',
  model_id: 'enso_logistic_baseline_v1',
  model_architecture: 'LogisticRegressionPredictor',
  macro_enso_state: {
    oni_aso_degc: 1.45,
    classification: 'El Niño (+1.45°C Strong Pacific Warm Anomaly)',
    nino34_aso_anom_degc: 1.2,
  },
  epistemic_notice:
    'EPISTEMIC SEPARATION: Operational estimates are derived strictly from the verified logistic model manifest.',
  subregions: [
    {
      region_id: 'ZA_LIMPOPO',
      region_name: 'Northern Limpopo River Basin (Semi-Arid Pastoral & Irrigation)',
      lat_bounds: [-25.0, -22.0],
      lon_bounds: [27.0, 32.0],
      centroid: [-23.5, 29.5],
      climatological_scaling_factor: 0.88,
      climatological_normal_djf_mm: 294.8,
      rainfall_anomaly: {
        october_zscore: -0.82,
        october_observed_mm: 31.2,
        october_normal_mm: 35.0,
        departure_pct: -21.6,
        metric_label: 'Antecedent Spring Deficit',
      },
      forecast: {
        probability: 0.456,
        decision_threshold: 0.5,
        risk_category: 'High',
        risk_ratio: 2.28,
        is_severe_drought: false,
      },
      uncertainty: {
        ci_90_lower: 0.324,
        ci_90_upper: 0.598,
        margin_of_error: 0.137,
        confidence_level_pct: 90,
        method: 'Logistic Logit Standard Error Propagation',
      },
      validity_period: {
        forecast_issue_date: '2025-11-01',
        convective_season: 'DJF 2025/26',
        target_start_date: '2025-12-01',
        target_end_date: '2026-02-28',
        lead_time_days: 30,
        status: 'OPERATIONAL_VALID',
      },
      provenance: {
        source_datasets: ['CHIRPS v2.0', 'NOAA CPC ONI', 'NOAA ERSSTv5 Niño 3.4'],
        training_data_fingerprint: '967ee97e8d4ad2be292a5d5b02afcfa7ed1f096cb983d289f2d5313464990e83',
        model_artefact_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
        verification_status: 'VERIFIED_INTEGRITY',
      },
      data_trust: {
        status: 'VERIFIED',
        trust_score: 98,
        tamper_check: 'PASSED',
        signature: 'AUTHENTICATED_HMAC',
      },
      epistemic_triad: {
        historical_observation: {
          classification: 'HISTORICAL_OBSERVATION',
          label: 'Historical Observed Normal: 294.8 mm',
          details: 'CHIRPS v2.0 satellite-station archive (1981-1988 baseline)',
          observed_value: 294.8,
          unit: 'mm',
        },
        model_estimate: {
          classification: 'MODEL_ESTIMATE',
          label: 'ENSO Shield Estimate: 45.6% Drought Risk',
          details: 'L2-regularized logistic regression (High Risk, 2.28x base rate)',
          probability: 0.456,
        },
        official_external_forecast: {
          classification: 'OFFICIAL_EXTERNAL_FORECAST',
          label: 'SARCOF-28 Consensus: Below-Normal Rainfall',
          details: 'SADC-CSC Regional Climate Outlook Forum (45% Below, 35% Normal, 20% Above)',
          tercile: 'Below-Normal',
        },
      },
    },
    {
      region_id: 'ZA_MAIZE_WEST',
      region_name: 'Western Free State & North West (Dryland Commercial Maize)',
      lat_bounds: [-28.0, -25.0],
      lon_bounds: [25.0, 27.5],
      centroid: [-26.5, 26.25],
      climatological_scaling_factor: 0.92,
      climatological_normal_djf_mm: 308.2,
      rainfall_anomaly: {
        october_zscore: -0.82,
        october_observed_mm: 32.5,
        october_normal_mm: 36.6,
        departure_pct: -11.2,
        metric_label: 'Antecedent Spring Deficit',
      },
      forecast: {
        probability: 0.438,
        decision_threshold: 0.5,
        risk_category: 'High',
        risk_ratio: 2.19,
        is_severe_drought: false,
      },
      uncertainty: {
        ci_90_lower: 0.31,
        ci_90_upper: 0.578,
        margin_of_error: 0.134,
        confidence_level_pct: 90,
        method: 'Logistic Logit Standard Error Propagation',
      },
      validity_period: {
        forecast_issue_date: '2025-11-01',
        convective_season: 'DJF 2025/26',
        target_start_date: '2025-12-01',
        target_end_date: '2026-02-28',
        lead_time_days: 30,
        status: 'OPERATIONAL_VALID',
      },
      provenance: {
        source_datasets: ['CHIRPS v2.0', 'NOAA CPC ONI'],
        training_data_fingerprint: '967ee97e8d4ad2be292a5d5b02afcfa7ed1f096cb983d289f2d5313464990e83',
        model_artefact_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
        verification_status: 'VERIFIED_INTEGRITY',
      },
      data_trust: {
        status: 'VERIFIED',
        trust_score: 98,
        tamper_check: 'PASSED',
        signature: 'AUTHENTICATED_HMAC',
      },
      epistemic_triad: {
        historical_observation: {
          classification: 'HISTORICAL_OBSERVATION',
          label: 'Historical Observed Normal: 308.2 mm',
          details: 'CHIRPS v2.0 archive',
          observed_value: 308.2,
          unit: 'mm',
        },
        model_estimate: {
          classification: 'MODEL_ESTIMATE',
          label: 'ENSO Shield Estimate: 43.8% Drought Risk',
          details: 'L2-regularized logistic regression',
          probability: 0.438,
        },
        official_external_forecast: {
          classification: 'OFFICIAL_EXTERNAL_FORECAST',
          label: 'SARCOF-28 Consensus: Below-Normal Rainfall',
          details: 'SADC-CSC consensus',
          tercile: 'Below-Normal',
        },
      },
    },
  ],
  total_subregions: 2,
  data_trust_summary: {
    overall_posture: 'HEALTHY',
    active_model_verified: true,
    training_data_fingerprint: '967ee97e8d4ad2be292a5d5b02afcfa7ed1f096cb983d289f2d5313464990e83',
    artefact_digest: 'b1a11d44ac764aaa85f738f28df0e42f46f2fe95622ce4792a4efe0315da1645',
    quarantined_models_count: 0,
  },
})

const mockHistoricalComparisons = (): HistoricalComparisonsResponse => ({
  status: 'operational',
  comparisons: [
    {
      season_year: 1983,
      convective_season: 'DJF 1982/83',
      forecast_issue_date: '1982-11-01',
      historical_observation: {
        djf_rainfall_mm: 225.7,
        target_drought_observed: 1,
        drought_label: 'Severe Drought (p20 Deficit)',
        october_zscore: -1.72,
        oni_aso_degc: 1.6,
        epistemic_tag: 'HISTORICAL_OBSERVATION',
      },
      model_estimate: {
        drought_probability: 0.88,
        predicted_binary: 1,
        risk_category: 'Critical',
        climatology_baseline_prob: 0.2,
        skill_advantage: 0.6256,
        epistemic_tag: 'MODEL_ESTIMATE',
      },
      official_external_forecast: {
        official_tercile: 'Below-Normal',
        consensus_statement: 'Severe Drought Advisory Issued (El Niño)',
        source: 'SARCOF Archive',
        epistemic_tag: 'OFFICIAL_EXTERNAL_FORECAST',
      },
      diagnostic_verdict: 'True Positive (Drought Correctly Flagged)',
      split: 'train',
    },
  ],
  count: 1,
  epistemic_disclaimer: 'HISTORICAL RECORD',
})

describe('DashboardView Regional Risk Map & Epistemic Triad', () => {
  it('renders regional map, subregion metrics, uncertainty, and tripartite comparison', async () => {
    const mockApi = {
      getRegionalForecast: vi.fn().mockResolvedValue(mockRegionalForecast()),
      getHistoricalComparisons: vi.fn().mockResolvedValue(mockHistoricalComparisons()),
    } as unknown as ReturnType<typeof createApiClient>

    render(<DashboardView api={mockApi} />)

    // Wait for subregion data to render
    await waitFor(() => {
      expect(
        screen.getByText('Regional Climate-Risk Operational Dashboard'),
      ).toBeInTheDocument()
    })

    // Check macro ENSO anomaly
    expect(screen.getByText('+1.45°C')).toBeInTheDocument()

    // Check regional map polygon rendered
    expect(screen.getByTestId('region-poly-za_limpopo')).toBeInTheDocument()
    expect(screen.getByTestId('subregion-detail-panel')).toBeInTheDocument()

    // Verify subregion name & probability
    expect(
      screen.getByText('Northern Limpopo River Basin (Semi-Arid Pastoral & Irrigation)'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('46%').length).toBeGreaterThan(0)

    // Verify uncertainty indicators
    expect(screen.getByText(/Calibrated Uncertainty Interval \(90% CI\)/)).toBeInTheDocument()
    expect(screen.getByText(/Lower 90% CI: 32%/)).toBeInTheDocument()
    expect(screen.getByText(/Upper 90% CI: 60%/)).toBeInTheDocument()

    // Verify Tripartite Epistemic Comparison
    expect(screen.getByText('Tripartite Epistemic Comparison')).toBeInTheDocument()
    expect(screen.getByText('Historical Observed Normal: 294.8 mm')).toBeInTheDocument()
    expect(screen.getByText('ENSO Shield Estimate: 45.6% Drought Risk')).toBeInTheDocument()
    expect(screen.getByText('SARCOF-28 Consensus: Below-Normal Rainfall')).toBeInTheDocument()

    // Verify Historical Seasons Comparison Ledger Table
    expect(screen.getByText(/Historical Season Verification Ledger/)).toBeInTheDocument()
    expect(screen.getByText('DJF 1982/83 (1983)')).toBeInTheDocument()
    expect(screen.getByText('225.7 mm')).toBeInTheDocument()
    expect(screen.getByText('True Positive (Drought Correctly Flagged)')).toBeInTheDocument()
  })

  it('switches subregion on button click', async () => {
    const mockApi = {
      getRegionalForecast: vi.fn().mockResolvedValue(mockRegionalForecast()),
      getHistoricalComparisons: vi.fn().mockResolvedValue(mockHistoricalComparisons()),
    } as unknown as ReturnType<typeof createApiClient>

    render(<DashboardView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByTestId('select-region-za_maize_west')).toBeInTheDocument()
    })

    await userEvent.click(screen.getByTestId('select-region-za_maize_west'))

    await waitFor(() => {
      expect(
        screen.getByText('Western Free State & North West (Dryland Commercial Maize)'),
      ).toBeInTheDocument()
      expect(screen.getByText('Historical Observed Normal: 308.2 mm')).toBeInTheDocument()
    })
  })
})
