import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import App from './App'

const config = { apiBaseUrl: 'http://api.test' }

function stubFetch(impl: typeof fetch) {
  const spy = vi.fn<typeof fetch>(impl)
  vi.stubGlobal('fetch', spy)
  return spy
}

const mockSystemStatus = () => ({
  service: 'enso-shield-api',
  version: '0.1.0',
  environment: 'test',
  timestamp_utc: '2026-10-27T22:00:00Z',
  database: {
    status: 'connected',
    latency_ms: 1.5,
    table_counts: { jobs: 3, forecast_audit_log: 2, schema_migrations: 2 },
  },
  pipelines: {
    datasets_operational: true,
    features_operational: true,
    active_model_operational: true,
    latest_experiment_operational: true,
  },
  active_jobs: [],
})

const mockDatasets = () => ({
  datasets: [
    {
      source: 'chirps_rainfall',
      tier: 'cleaned',
      file_name: 'chirps_rainfall_monthly.csv',
      file_path: 'data/cleaned/chirps_rainfall_monthly.csv',
      exists: true,
      file_size_bytes: 1024,
      record_count: 500,
      sha256: 'abcdef1234567890',
      is_fixture: true,
      modified_at_utc: '2026-10-27T20:00:00Z',
    },
  ],
  total_datasets: 1,
  cleaned_operational: true,
})

describe('ENSO Shield Workbench App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders brand header and 8 workflow tabs', async () => {
    stubFetch(async (url) => {
      const u = String(url)
      if (u.includes('/api/v1/system/status')) {
        return new Response(JSON.stringify(mockSystemStatus()), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<App config={config} />)
    expect(screen.getByText('ENSO Shield')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Research Workbench Overview',
    )

    // Check all 11 workflow tabs
    expect(screen.getByTestId('tab-dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('tab-overview')).toBeInTheDocument()
    expect(screen.getByTestId('tab-forecasts')).toBeInTheDocument()
    expect(screen.getByTestId('tab-preparedness')).toBeInTheDocument()
    expect(screen.getByTestId('tab-security')).toBeInTheDocument()
    expect(screen.getByTestId('tab-models')).toBeInTheDocument()
    expect(screen.getByTestId('tab-experiments')).toBeInTheDocument()
    expect(screen.getByTestId('tab-features')).toBeInTheDocument()
    expect(screen.getByTestId('tab-data')).toBeInTheDocument()
    expect(screen.getByTestId('tab-provenance')).toBeInTheDocument()
    expect(screen.getByTestId('tab-diagnostics')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('API Ready')).toBeInTheDocument()
    })
  })

  it('navigates to Data view on tab click', async () => {
    stubFetch(async (url) => {
      const u = String(url)
      if (u.includes('/api/v1/system/status')) {
        return new Response(JSON.stringify(mockSystemStatus()), { status: 200 })
      }
      if (u.includes('/api/v1/datasets')) {
        return new Response(JSON.stringify(mockDatasets()), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<App config={config} />)
    const dataTab = screen.getByTestId('tab-data')
    await userEvent.click(dataTab)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
        'Climate Datasets & Ingestion Engine',
      )
    })
  })

  it('navigates to Forecasts view on tab click', async () => {
    stubFetch(async (url) => {
      const u = String(url)
      if (u.includes('/api/v1/system/status')) {
        return new Response(JSON.stringify(mockSystemStatus()), { status: 200 })
      }
      if (u.includes('/api/v1/forecast/history')) {
        return new Response(JSON.stringify({ audits: [], count: 0 }), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<App config={config} />)
    const forecastTab = screen.getByTestId('tab-forecasts')
    await userEvent.click(forecastTab)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
        'Probabilistic Drought Risk Inference',
      )
    })
  })

  it('navigates into Experiments view and back to Overview without blanking', async () => {
    stubFetch(async (url) => {
      const u = String(url)
      if (u.includes('/api/v1/system/status')) {
        return new Response(JSON.stringify(mockSystemStatus()), { status: 200 })
      }
      if (u.includes('/api/v1/experiments/latest')) {
        return new Response(JSON.stringify({ detail: 'No manifest' }), { status: 404 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    })

    render(<App config={config} />)

    // Navigate to Experiments
    const expTab = screen.getByTestId('tab-experiments')
    await userEvent.click(expTab)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
        'Model Evaluation & Scientific Benchmarks',
      )
    })

    // Navigate back to Overview
    const overviewTab = screen.getByTestId('tab-overview')
    await userEvent.click(overviewTab)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
        'Research Workbench Overview',
      )
    })
  })
})

