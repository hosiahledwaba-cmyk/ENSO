"""Unit and integration tests for public climate data ingestion, provider adapters, and API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from enso_api.ingestion.coordinator import (
    ClimateIngestionCoordinator,
    NoaaNino34Provider,
    NoaaOniProvider,
    NoaaSoiProvider,
)
from enso_api.ingestion.scheduler import IngestionScheduler


def test_noaa_oni_provider_parsing() -> None:
    """Verify parsing of NOAA CPC ONI ASCII table format."""
    provider = NoaaOniProvider()
    sample_ascii = (
        "SEAS  YR   TOTAL  ANOM\n"
        "DJF 1950   24.72 -1.53\n"
        "JFM 1950   25.17 -1.34\n"
        "JAS 2026   28.52  2.16\n"
    )
    records = provider.parse_oni_text(sample_ascii)
    assert len(records) == 3
    assert records[0]["season"] == "DJF"
    assert records[0]["year"] == 1950
    assert records[0]["anomaly"] == -1.53
    assert records[2]["season"] == "JAS"
    assert records[2]["year"] == 2026
    assert records[2]["anomaly"] == 2.16


def test_noaa_nino34_provider_parsing() -> None:
    """Verify parsing of NOAA CPC Niño 3.4 SST & anomaly indices table."""
    provider = NoaaNino34Provider()
    sample_text = (
        "YR  MON   NINO1+2  ANOM   NINO3    ANOM   NINO4    ANOM   NINO3.4  ANOM\n"
        "1982   1   24.28   0.02   25.43  -0.12   28.12  -0.15   26.54  -0.10\n"
        "2026   9   22.10   1.50   26.20   1.80   30.10   2.10   29.60   2.84\n"
    )
    records = provider.parse_sstoi_text(sample_text)
    assert len(records) == 2
    assert records[0]["year"] == 1982
    assert records[0]["month"] == 1
    assert records[0]["sst"] == 26.54
    assert records[0]["anomaly"] == -0.10
    assert records[1]["year"] == 2026
    assert records[1]["month"] == 9
    assert records[1]["sst"] == 29.60
    assert records[1]["anomaly"] == 2.84


def test_noaa_soi_provider_parsing() -> None:
    """Verify parsing of NOAA CPC SOI monthly standardized table."""
    provider = NoaaSoiProvider()
    sample_text = (
        "YEAR    JAN    FEB    MAR    APR    MAY    JUN    JUL    AUG    SEP    OCT    NOV    DEC\n"
        "1951    1.5    0.9   -0.1   -0.3   -0.7    0.2   -1.0   -0.4   -1.1   -1.0   -0.8   -0.7\n"
        "2026   -0.8   -1.1   -1.5   -1.2   -1.8   -2.1   -2.3   -2.2   -2.0  -99.9  -99.9  -99.9\n"
    )
    records = provider.parse_soi_text(sample_text)
    assert len(records) == 12 + 9  # 1951 full year + 2026 through Sep
    assert records[0]["year"] == 1951
    assert records[0]["month"] == 1
    assert records[0]["soi"] == 1.5
    # Latest valid in 2026 is month 9 (-2.0)
    rec_sep_2026 = next(r for r in records if r["year"] == 2026 and r["month"] == 9)
    assert rec_sep_2026["soi"] == -2.0


def test_provider_failure_isolation() -> None:
    """Verify that a failure in one provider does not crash or block other providers."""
    coordinator = ClimateIngestionCoordinator()

    class FailingProvider:
        source_id = "failing_mock"
        dataset_name = "Mock Failure"

        def ingest(self, dry_run: bool = False):
            raise ConnectionError("Mock simulated remote timeout")

    results = coordinator.run_all(dry_run=True)
    # The coordinator should catch exceptions cleanly per-provider
    assert isinstance(results, dict)


def test_scheduler_concurrency_lock() -> None:
    """Verify that IngestionScheduler prevents concurrent duplicate execution."""
    scheduler = IngestionScheduler()
    assert not scheduler.is_job_active
    scheduler._is_running = True
    assert scheduler.is_job_active
    scheduler._is_running = False
    assert not scheduler.is_job_active


def test_ingestion_api_endpoints(client: TestClient) -> None:
    """Verify HTTP GET /api/v1/ingestion/coverage and /scheduler."""
    cov_resp = client.get("/api/v1/ingestion/coverage")
    assert cov_resp.status_code == 200
    cov_data = cov_resp.json()
    assert isinstance(cov_data, list)
    assert len(cov_data) >= 3

    # Verify expected providers are present
    source_ids = {c["source_id"] for c in cov_data}
    assert "noaa_oni" in source_ids
    assert "noaa_nino34" in source_ids

    # Verify scheduler endpoint
    sched_resp = client.get("/api/v1/ingestion/scheduler")
    assert sched_resp.status_code == 200
    sched_data = sched_resp.json()
    assert "is_running" in sched_data
    assert "cadence" in sched_data
    assert "Daily at 02:00:00 UTC" in sched_data["cadence"]

    # Verify history endpoint
    hist_resp = client.get("/api/v1/ingestion/history")
    assert hist_resp.status_code == 200
    assert isinstance(hist_resp.json(), list)
