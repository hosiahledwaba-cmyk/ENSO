"""Integration tests for model artefact verification, quarantine, and poisoning resilience APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_models_audit_endpoint(client: TestClient) -> None:
    """Verify endpoint auditing all models in registry against cryptographic manifests."""
    res = client.get("/api/v1/models/audit")
    assert res.status_code == 200
    data = res.json()
    assert "posture" in data
    assert "total_scanned" in data
    assert "passed_count" in data
    assert "models" in data
    assert isinstance(data["models"], list)


def test_models_verify_endpoint(client: TestClient) -> None:
    """Verify cryptographic SHA-256 integrity verification for operational baseline model."""
    payload = {"model_dir": "models/logistic_regression_baseline"}
    res = client.post("/api/v1/models/verify", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["verified"] is True
    assert data["audit"]["digest_matches"] is True
    assert data["audit"]["approval_status"] == "APPROVED"


def test_models_poisoning_scenarios_endpoint(client: TestClient) -> None:
    """Verify poisoning scenarios catalog and explicit threat documentation."""
    res = client.get("/api/v1/models/poisoning/scenarios")
    assert res.status_code == 200
    data = res.json()
    assert "scenarios" in data
    assert len(data["scenarios"]) >= 4
    scenario_classes = [s["attack_class"] for s in data["scenarios"]]
    assert "LABEL_FLIPPING" in scenario_classes
    assert "SUBPOPULATION_FEATURE_POISONING" in scenario_classes
    assert "EXTREME_LEVERAGE_OUTLIER" in scenario_classes
    assert "TARGETED_BACKDOOR" in scenario_classes

    # Verify explicit scientific and threat boundaries
    assert "threat_limitations" in data
    assert len(data["threat_limitations"]) >= 3
    assert "recovery_protocol" in data
    assert len(data["recovery_protocol"]) >= 5


def test_models_poisoning_evaluate_endpoint(client: TestClient) -> None:
    """Verify isolated poisoning experiment execution and comparative reporting."""
    payload = {
        "attack_class": "LABEL_FLIPPING",
        "attack_params": {"flip_fraction": 0.20},
        "holdout_count": 2,
    }
    res = client.post("/api/v1/models/poisoning/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    report = data["report"]
    assert report["attack_class"] == "LABEL_FLIPPING"
    assert "clean_training_fingerprint" in report
    assert "poisoned_training_fingerprint" in report
    assert report["clean_training_fingerprint"] != report["poisoned_training_fingerprint"]
    assert "brier_score_degradation" in report
    assert "l2_weight_displacement" in report
    assert "threat_limitations" in report
    assert "recovery_process" in report
    assert "remaining_risks" in report


def test_models_quarantine_listing_endpoint(client: TestClient) -> None:
    """Verify retrieval of quarantined model audit dossiers."""
    res = client.get("/api/v1/models/quarantine")
    assert res.status_code == 200
    data = res.json()
    assert "quarantined_models" in data
    assert isinstance(data["quarantined_models"], list)
