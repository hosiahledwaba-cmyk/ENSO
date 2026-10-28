import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ForecastsView } from './ForecastsView'
import type { createApiClient, PredictionResponse } from '../api/client'

describe('ForecastsView Scientific Integrity & Factor Audit', () => {
  const mockApi = {
    predictForecast: vi.fn(),
    getForecastHistory: vi.fn().mockResolvedValue({ audits: [], count: 0 }),
  } as unknown as ReturnType<typeof createApiClient>

  it('renders input form with clear temporal alignment and issue date badge', () => {
    render(<ForecastsView api={mockApi} />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Probabilistic Drought Risk Inference & Factor Decomposition',
    )
    expect(screen.getByText('Forecast Issue Date: Nov 1, 2025')).toBeInTheDocument()
    expect(screen.getByLabelText(/Convective Summer Season Year/i)).toHaveValue(2026)
  })

  it('executes inference and renders factor contribution audit ledger and risk ratio', async () => {
    const mockPrediction: PredictionResponse = {
      prediction_id: 'pred_audit123456',
      model_name: 'regularized_logistic_regression',
      model_version: 'enso_logistic_test',
      issue_year: 2026,
      forecast_target: 'severe_drought_p20_djf',
      forecast_issue_date: '2025-11-01',
      predicted_probability: 0.4284,
      decision_threshold: 0.50,
      risk_category: 'Elevated Drought Risk',
      is_severe_drought: false,
      data_origin_type: 'user_scenario',
      disclaimer: 'SCENARIO EXPLORATION: Physically consistent antecedent rainfall.',
      inputs_validated: {
        oni_aso_degc: 1.45,
        precip_oct_zscore: -0.82,
        precip_oct_mm_resolved: 33.15,
        precip_antecedent_spring_mm_resolved: 48.65,
        nino34_aso_anom_degc: 1.20,
        nino34_aso_sst_degc_resolved: 27.98,
      },
      uncertainty: {
        climatological_base_rate: 0.20,
        risk_ratio: 2.14,
        holdout_brier_skill_score: 0.057,
        base_logit_intercept: -2.4719,
        total_logit: -0.2884,
        factor_contributions: {
          oni_aso_degc: 0.4678,
          nino34_aso_sst_degc: 0.4069,
          nino34_aso_anom_degc: 0.3911,
          precip_oct_zscore: 0.2306,
          precip_oct_mm: 0.1996,
          precip_antecedent_spring_mm: 0.1596,
        },
        feature_details: [
          {
            feature_name: 'oni_aso_degc',
            raw_value: 1.45,
            scaler_mean: 0.04,
            scaler_scale: 0.79,
            standardized_z: 1.793,
            coefficient_weight: 0.2609,
            logit_contribution: 0.4678,
            impact_direction: 'increases_drought_odds',
          },
          {
            feature_name: 'precip_oct_zscore',
            raw_value: -0.82,
            scaler_mean: 0.15,
            scaler_scale: 1.02,
            standardized_z: -0.948,
            coefficient_weight: -0.2434,
            logit_contribution: 0.2306,
            impact_direction: 'increases_drought_odds',
          },
        ],
      },
      created_at: new Date().toISOString(),
    }

    vi.mocked(mockApi.predictForecast).mockResolvedValueOnce(mockPrediction)

    render(<ForecastsView api={mockApi} />)

    const submitBtn = screen.getByRole('button', { name: /Run Risk Inference/i })
    await userEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText('42.8%')).toBeInTheDocument()
      expect(screen.getByText('Elevated Drought Risk')).toBeInTheDocument()
      expect(screen.getByText(/2.14×/)).toBeInTheDocument()
      expect(screen.getByText('Factor Contribution & Scientific Integrity Audit Ledger')).toBeInTheDocument()
      expect(screen.getByText('oni_aso_degc')).toBeInTheDocument()
      expect(screen.getByText('precip_oct_zscore')).toBeInTheDocument()
      expect(screen.getAllByText('↑ Raises Drought Odds').length).toBeGreaterThan(0)
    })
  })

  it('blocks submission and displays validation error when spring rainfall is less than October rainfall', async () => {
    vi.mocked(mockApi.predictForecast).mockClear()

    render(<ForecastsView api={mockApi} />)

    const octInput = screen.getByLabelText(/Oct Rainfall Depth/i)
    const springInput = screen.getByLabelText(/Spring Total/i)

    await userEvent.clear(octInput)
    await userEvent.type(octInput, '60.00')

    await userEvent.clear(springInput)
    await userEvent.type(springInput, '20.00')

    const submitBtn = screen.getByRole('button', { name: /Run Risk Inference/i })
    await userEvent.click(submitBtn)

    expect(
      screen.getByText(/Physically inconsistent scenario: Antecedent spring rainfall/i),
    ).toBeInTheDocument()
    expect(mockApi.predictForecast).not.toHaveBeenCalled()
  })

  it('loads preset parameters when historical preset button is clicked', async () => {
    render(<ForecastsView api={mockApi} />)

    const presetBtn = screen.getByRole('button', { name: /1982\/83 Extreme Drought/i })
    await userEvent.click(presetBtn)

    expect(screen.getByLabelText(/Antecedent ONI Anomaly/i)).toHaveValue(2.15)
    expect(screen.getByLabelText(/Antecedent October Rainfall Anomaly/i)).toHaveValue(-1.25)
    expect(screen.getByLabelText(/Niño 3.4 SST Anomaly/i)).toHaveValue(1.85)
    expect(screen.getByLabelText(/Oct Rainfall Depth/i)).toHaveValue(29.67)
    expect(screen.getByLabelText(/Spring Total/i)).toHaveValue(40.5)
    expect(screen.getByLabelText(/Convective Summer Season Year/i)).toHaveValue(1983)
  })

  it('displays statistical limitation notice when provided in prediction response', async () => {
    const mockPrediction: PredictionResponse = {
      prediction_id: 'pred_limitation_test',
      model_name: 'regularized_logistic_regression',
      model_version: 'enso_logistic_test',
      issue_year: 2026,
      forecast_target: 'severe_drought_p20_djf',
      forecast_issue_date: '2025-11-01',
      predicted_probability: 0.35,
      decision_threshold: 0.50,
      risk_category: 'Normal Risk',
      is_severe_drought: false,
      data_origin_type: 'user_scenario',
      disclaimer: 'EXPLORATORY TEST',
      inputs_validated: {},
      uncertainty: {
        statistical_notice: 'Parameter confidence intervals are heuristic sensitivity bounds (N=5 training seasons).',
        is_statistically_rigorous_ci: false,
      },
      created_at: new Date().toISOString(),
    }

    vi.mocked(mockApi.predictForecast).mockResolvedValueOnce(mockPrediction)

    render(<ForecastsView api={mockApi} />)

    const submitBtn = screen.getByRole('button', { name: /Run Risk Inference/i })
    await userEvent.click(submitBtn)

    await waitFor(() => {
      expect(
        screen.getByText(/Parameter confidence intervals are heuristic sensitivity bounds/i),
      ).toBeInTheDocument()
    })
  })
})

