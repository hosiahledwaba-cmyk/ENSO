import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProvenanceView } from './ProvenanceView'
import type { createApiClient, ProvenanceRecord, ProvenanceAuditReport } from '../api/client'

const mockRecords: ProvenanceRecord[] = [
  {
    manifest_version: '2.0',
    dataset_id: 'chirps_rainfall',
    source_identifier: 'chirps_rainfall',
    source_name: 'CHIRPS-2.0',
    source_version: 'CHIRPS-v2.0',
    dataset_version: 'CHIRPS-v2.0',
    source_url: 'https://data.chc.ucsb.edu/products/CHIRPS-2.0/',
    source_timestamp_utc: '2026-10-27T19:38:27Z',
    licence: 'Public Domain',
    citation: 'Funk et al. (2015)',
    ingestion_timestamp_utc: '2026-10-28T01:39:15Z',
    content_digest: 'c482499ed8cbed3452a3330125a949d4c58f8f15f6db6ad1fd6a2e33e6939924',
    raw_sha256: '329bd595f543156cf16c85c5e6613d3bb619102251acc746433a42d00482fe9c',
    cleaned_sha256: 'c482499ed8cbed3452a3330125a949d4c58f8f15f6db6ad1fd6a2e33e6939924',
    derived_sha256: null,
    record_count: 96,
    date_range: { start: '1981-01', end: '1988-12' },
    units: { precip_mm: 'mm/month' },
    validation_status: 'PASSED',
    authenticity_status: 'AUTHENTIC_CONTROLLED_PIPELINE',
    signature: 'f735e6b57df464b6368d5fefa1b4e1d9ceaa492e257d2bfcc225ea024db2bd7d',
    signing_key_id: 'enso-pipeline-hmac-v1',
    processing_history: [
      {
        step_name: 'raw_acquisition',
        timestamp_utc: '2026-10-27T19:38:27Z',
        operator: 'chirps_adapter:v2.0',
        input_digests: {},
        output_digest: '329bd595f543156cf16c85c5e6613d3bb619102251acc746433a42d00482fe9c',
        parameters: { note: 'Unsigned third-party data' },
      },
      {
        step_name: 'validation_and_cleaning',
        timestamp_utc: '2026-10-28T01:39:15Z',
        operator: 'chirps_adapter:v2.0',
        input_digests: { raw_artefact: '329bd595f543156cf16c85c5e6613d3bb619102251acc746433a42d00482fe9c' },
        output_digest: 'c482499ed8cbed3452a3330125a949d4c58f8f15f6db6ad1fd6a2e33e6939924',
        parameters: { records: 96 },
      },
    ],
  },
  {
    manifest_version: '2.0',
    dataset_id: 'noaa_raw_sample',
    source_identifier: 'noaa_oni',
    source_name: 'NOAA CPC ONI Raw',
    source_version: 'v5.0',
    dataset_version: 'v5.0',
    source_url: 'https://psl.noaa.gov/',
    source_timestamp_utc: '2026-10-27T19:38:27Z',
    licence: 'Public Domain',
    citation: 'NOAA (2026)',
    ingestion_timestamp_utc: '2026-10-28T01:39:15Z',
    content_digest: 'aac0b4ad125e',
    raw_sha256: 'aac0b4ad125e',
    cleaned_sha256: null,
    derived_sha256: null,
    record_count: 96,
    date_range: { start: '1981-01', end: '1988-12' },
    units: { oni: 'degC' },
    validation_status: 'PASSED',
    authenticity_status: 'UNSIGNED_THIRD_PARTY',
    signature: null,
    signing_key_id: null,
    processing_history: [],
  },
]

const mockAuditReport: ProvenanceAuditReport = {
  audit_timestamp_utc: '2026-10-28T02:00:00Z',
  overall_status: 'PASSED',
  total_artefacts: 2,
  verified_count: 2,
  tampered_count: 0,
  missing_files_count: 0,
  signed_pipeline_count: 1,
  unsigned_third_party_count: 1,
  invalid_signature_count: 0,
  valid_scientific_count: 2,
  fresh_count: 0,
  stale_count: 0,
  archival_benchmark_count: 2,
  untracked_files_count: 0,
  violations_count: 0,
  violations: [],
  artefacts: [],
}

describe('ProvenanceView Subsystem', () => {
  it('renders the 4-pillar integrity dashboard and distinguishes unsigned third-party data', async () => {
    const mockApi = {
      getProvenance: vi.fn().mockResolvedValue({ records: mockRecords, count: 2 }),
      getProvenanceAudit: vi.fn().mockResolvedValue(mockAuditReport),
      verifyArtefact: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ProvenanceView api={mockApi} />)

    expect(screen.getByText(/Climate Data Provenance & Cryptographic Integrity Subsystem/i)).toBeInTheDocument()

    await waitFor(() => {
      // 4 Pillar metrics
      expect(screen.getByText(/1\. Content Integrity/i)).toBeInTheDocument()
      expect(screen.getByText(/2\. Source Authenticity/i)).toBeInTheDocument()
      expect(screen.getByText(/3\. Scientific Validity/i)).toBeInTheDocument()
      expect(screen.getByText(/4\. Freshness & Baseline/i)).toBeInTheDocument()

      // Distinction between authentic pipeline and unsigned third party
      expect(screen.getByText(/AUTHENTIC \(SIGNED\)/i)).toBeInTheDocument()
      expect(screen.getByText(/UNSIGNED \(3RD-PARTY\)/i)).toBeInTheDocument()
    })
  })

  it('toggles transformation lineage drawer and displays processing stages', async () => {
    const user = userEvent.setup()
    const mockApi = {
      getProvenance: vi.fn().mockResolvedValue({ records: mockRecords, count: 2 }),
      getProvenanceAudit: vi.fn().mockResolvedValue(mockAuditReport),
      verifyArtefact: vi.fn(),
    } as unknown as ReturnType<typeof createApiClient>

    render(<ProvenanceView api={mockApi} />)

    await waitFor(() => {
      expect(screen.getAllByText('chirps_rainfall')[0]).toBeInTheDocument()
    })

    const lineageButtons = screen.getAllByRole('button', { name: /Lineage/i })
    await user.click(lineageButtons[0])

    // Should display transformation lineage drawer
    expect(screen.getByText(/Transformation Lineage & Security Assertions/i)).toBeInTheDocument()
    expect(screen.getByText(/Stage 1:/i)).toBeInTheDocument()
    expect(screen.getByText('raw_acquisition')).toBeInTheDocument()
    expect(screen.getByText(/Stage 2:/i)).toBeInTheDocument()
    expect(screen.getByText('validation_and_cleaning')).toBeInTheDocument()
  })
})
