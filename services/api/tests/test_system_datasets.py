"""Tests for system dataset discovery and health verification in services/api/routes/system.py."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from enso_api.routes.system import check_dataset_file


def test_system_status_operational_when_authoritative_files_present(client: TestClient) -> None:
    """Verify that get_system_status reports operational dataset pipeline when authoritative _monthly.csv exist."""
    res = client.get("/api/v1/system/status")
    assert res.status_code == 200
    data = res.json()
    assert "pipelines" in data
    assert "datasets" in data["pipelines"]
    datasets_pipeline = data["pipelines"]["datasets"]
    assert datasets_pipeline["status"] == "operational"
    assert datasets_pipeline["cleaned_ready"] is True

    # Details must cover all 4 climate series
    details = datasets_pipeline["dataset_details"]
    assert "chirps_rainfall" in details
    assert "noaa_oni" in details
    assert "noaa_nino34" in details
    assert "noaa_soi" in details
    assert details["chirps_rainfall"]["status"] == "HEALTHY"
    assert details["noaa_oni"]["status"] == "HEALTHY"
    assert details["noaa_nino34"]["status"] == "HEALTHY"
    assert details["noaa_soi"]["status"] == "HEALTHY"


def test_check_dataset_file_absent(tmp_path: Path) -> None:
    """Verify absent dataset file is accurately reported as MISSING."""
    result = check_dataset_file(tmp_path, "missing_dataset")
    assert result["status"] == "MISSING"
    assert result["is_valid"] is False
    assert result["size_bytes"] == 0
    assert "does not exist" in result["detail"]


def test_check_dataset_file_empty(tmp_path: Path) -> None:
    """Verify 0-byte empty file is accurately reported as EMPTY."""
    empty_file = tmp_path / "test_dataset_monthly.csv"
    empty_file.write_bytes(b"")

    result = check_dataset_file(tmp_path, "test_dataset")
    assert result["status"] == "EMPTY"
    assert result["is_valid"] is False
    assert result["size_bytes"] == 0
    assert "empty (0 bytes)" in result["detail"]


def test_check_dataset_file_header_only_no_rows(tmp_path: Path) -> None:
    """Verify file with header only but no rows is reported as EMPTY_OR_NO_ROWS."""
    header_only = tmp_path / "test_dataset_monthly.csv"
    header_only.write_text("year,month,date,val\n", encoding="utf-8")

    result = check_dataset_file(tmp_path, "test_dataset")
    assert result["status"] == "EMPTY_OR_NO_ROWS"
    assert result["is_valid"] is False


def test_check_dataset_file_healthy(tmp_path: Path) -> None:
    """Verify healthy file with header and data rows is reported as HEALTHY."""
    healthy_file = tmp_path / "test_dataset_monthly.csv"
    healthy_file.write_text("year,month,date,val\n1982,1,1982-01-01,1.5\n", encoding="utf-8")

    result = check_dataset_file(tmp_path, "test_dataset")
    assert result["status"] == "HEALTHY"
    assert result["is_valid"] is True
    assert result["size_bytes"] > 0
