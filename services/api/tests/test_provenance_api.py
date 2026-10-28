"""Automated API integration tests for climate data provenance and integrity endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_provenance_datasets_endpoint(client: TestClient) -> None:
    """Verify listing of provenance records returns enriched v2.0 schema."""
    res = client.get("/api/v1/provenance/datasets")
    assert res.status_code == 200
    data = res.json()
    assert "records" in data
    assert "count" in data
    assert data["count"] >= 3

    # Check chirps manifest fields
    chirps = next((r for r in data["records"] if r["dataset_id"] == "chirps_rainfall"), None)
    assert chirps is not None
    assert "content_digest" in chirps
    assert "processing_history" in chirps
    assert len(chirps["processing_history"]) >= 2
    assert "validation_outcome" in chirps
    assert chirps["authenticity_status"] in (
        "AUTHENTIC_CONTROLLED_PIPELINE",
        "UNSIGNED_THIRD_PARTY",
    )


def test_provenance_audit_endpoint(client: TestClient) -> None:
    """Verify live audit endpoint reports full integrity across operational artefacts."""
    res = client.get("/api/v1/provenance/audit")
    assert res.status_code == 200
    report = res.json()
    assert report["overall_status"] == "PASSED"
    assert report["total_artefacts"] >= 3
    assert report["tampered_count"] == 0
    assert report["verified_count"] >= 3
    assert "artefacts" in report
    assert len(report["artefacts"]) == report["total_artefacts"]


def test_provenance_verify_endpoint_success(client: TestClient) -> None:
    """Verify on-demand integrity audit for specific dataset."""
    res = client.post("/api/v1/provenance/verify", json={"dataset_id": "chirps_rainfall"})
    assert res.status_code == 200
    detail = res.json()
    assert detail["artefact_id"] == "chirps_rainfall"
    assert detail["content_integrity"] == "VERIFIED"
    assert detail["digest_matches"] is True
    assert detail["scientific_validity"] == "VALID"


def test_provenance_verify_endpoint_validation_errors(client: TestClient) -> None:
    """Verify validation errors for bad verify requests."""
    # Empty request -> 400
    res_empty = client.post("/api/v1/provenance/verify", json={})
    assert res_empty.status_code == 400

    # Non-existent dataset -> 404
    res_missing = client.post(
        "/api/v1/provenance/verify", json={"dataset_id": "non_existent_dataset_999"}
    )
    assert res_missing.status_code == 404
