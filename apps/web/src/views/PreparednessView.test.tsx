import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PreparednessView } from './PreparednessView'
import type { createApiClient, PreparednessMatrixResponse } from '../api/client'

const mockMatrix = (): PreparednessMatrixResponse => ({
  status: 'operational',
  operational_context: {
    issue_date: '2026-11-01',
    convective_season: 'DJF 2026/27',
    forecast_probability_pct: 42.8,
    active_risk_tier: 'HIGH',
    active_risk_label: 'High Severe Drought Risk (40% - 60%)',
    climatological_base_rate_pct: 20.0,
    risk_ratio: 2.14,
    decision_rule:
      'Under Anticipatory Action Protocol §6, High Risk Agricultural and Water Resource triggers are automatically activated.',
  },
  trigger_tiers: [
    {
      tier: 'NORMAL',
      label: 'Baseline / Normal Risk',
      range: '< 25%',
      status: 'CLEARED',
      description: 'Routine seasonal monitoring.',
    },
    {
      tier: 'ELEVATED',
      label: 'Elevated Risk',
      range: '25% - 40%',
      status: 'ACTIVE_SURPASS',
      description: 'Advisory alerts to agricultural extension networks.',
    },
    {
      tier: 'HIGH',
      label: 'High Severe Drought Risk',
      range: '40% - 60%',
      status: 'CURRENTLY_TRIGGERED',
      description: 'Anticipatory action execution: drought-tolerant seeds, irrigation rationing.',
    },
    {
      tier: 'CRITICAL',
      label: 'Critical Emergency Drought Risk',
      range: '>= 60%',
      status: 'STANDBY',
      description: 'Emergency humanitarian mitigation.',
    },
  ],
  actions_summary: {
    total_actions: 2,
    triggered: 1,
    executed: 0,
    ready: 1,
    monitoring: 0,
  },
  actions: [
    {
      id: 'ACT_AGRI_02',
      tier: 'HIGH',
      tier_label: 'High Risk (40% - 60%)',
      threshold_min_pct: 40.0,
      threshold_max_pct: 60.0,
      sector: 'AGRICULTURE',
      action_name: 'Drought-Tolerant Sorghum & Millet Seed Voucher Distribution',
      description: 'Trigger anticipatory voucher distribution for short-season grain varieties.',
      lead_agency: 'SAGIS & ARC',
      target_subregions: ['ZA_LIMPOPO', 'ZA_MAIZE_WEST'],
      lead_time_days: 21,
      status: 'TRIGGERED',
      last_updated_at: '2026-10-28T02:30:00Z',
      operator_notes: 'Triggered by operational forecast.',
    },
    {
      id: 'ACT_WATER_01',
      tier: 'ELEVATED',
      tier_label: 'Elevated Risk (25% - 40%)',
      threshold_min_pct: 25.0,
      threshold_max_pct: 40.0,
      sector: 'WATER_RESOURCES',
      action_name: 'Limpopo & Olifants Catchment Storage Audit',
      description: 'Conduct structural audit of major irrigation canals.',
      lead_agency: 'DWS',
      target_subregions: ['ZA_LIMPOPO'],
      lead_time_days: 30,
      status: 'READY',
      last_updated_at: '2026-10-27T18:00:00Z',
      operator_notes: 'Maintenance on standby.',
    },
  ],
})

describe('PreparednessView Anticipatory Action Workflow', () => {
  it('renders active risk tier, trigger progression, and sector actions', async () => {
    const mockApi = {
      getPreparednessMatrix: vi.fn().mockResolvedValue(mockMatrix()),
    } as unknown as ReturnType<typeof createApiClient>

    render(<PreparednessView api={mockApi} />)

    await waitFor(() => {
      expect(
        screen.getByText('Drought Preparedness & Anticipatory Action Workflow'),
      ).toBeInTheDocument()
    })

    // Verify Active Risk Tier Banner
    expect(screen.getByText(/ACTIVE OPERATIONAL TRIGGER: HIGH RISK/)).toBeInTheDocument()
    expect(screen.getByText('42.8%')).toBeInTheDocument()
    expect(screen.getByText('2.14x')).toBeInTheDocument()

    // Verify action card
    expect(
      screen.getByText('Drought-Tolerant Sorghum & Millet Seed Voucher Distribution'),
    ).toBeInTheDocument()
    expect(screen.getByText('SAGIS & ARC')).toBeInTheDocument()
  })

  it('filters actions by sector and opens execution modal', async () => {
    const mockApi = {
      getPreparednessMatrix: vi.fn().mockResolvedValue(mockMatrix()),
      triggerPreparednessAction: vi.fn().mockResolvedValue({
        status: 'updated',
        action: { ...mockMatrix().actions[0], status: 'EXECUTED' },
        message: 'Action ACT_AGRI_02 successfully transitioned to EXECUTED.',
      }),
    } as unknown as ReturnType<typeof createApiClient>

    render(<PreparednessView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getByTestId('filter-sector-agriculture')).toBeInTheDocument()
    })

    // Filter to agriculture
    await userEvent.click(screen.getByTestId('filter-sector-agriculture'))
    expect(
      screen.getByText('Drought-Tolerant Sorghum & Millet Seed Voucher Distribution'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Limpopo & Olifants Catchment Storage Audit'),
    ).not.toBeInTheDocument()

    // Open execution modal
    const confirmBtn = screen.getByTestId('btn-action-trigger-act_agri_02')
    await userEvent.click(confirmBtn)

    expect(screen.getByText('Dispatch Anticipatory Action')).toBeInTheDocument()
    expect(screen.getByTestId('btn-modal-submit-execution')).toBeInTheDocument()

    // Submit execution
    await userEvent.click(screen.getByTestId('btn-modal-submit-execution'))
    await waitFor(() => {
      expect(mockApi.triggerPreparednessAction).toHaveBeenCalledWith(
        'ACT_AGRI_02',
        expect.objectContaining({ status: 'EXECUTED' }),
      )
    })
  })
})
