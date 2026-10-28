"""Integration tests for defensive data-anomaly detection and FDI simulation API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_defense_scenarios_catalog(client: TestClient) -> None:
    """Verify endpoint listing all defensive simulation scenarios."""
    res = client.get("/api/v1/defense/scenarios")
    assert res.status_code == 200
    data = res.json()
    assert "scenarios" in data
    assert data["total_scenarios"] == 5
    scenario_ids = [s["id"] for s in data["scenarios"]]
    assert "DATA_CORRUPTION" in scenario_ids
    assert "REPLAY_ATTACK" in scenario_ids
    assert "MEASUREMENT_NOISE" in scenario_ids
    assert "MISSING_DATA" in scenario_ids
    assert "ADVERSARIAL_FDI" in scenario_ids


def test_defense_benchmarks_endpoint(client: TestClient) -> None:
    """Verify precomputed or live defensive benchmarks report."""
    res = client.get("/api/v1/defense/benchmarks")
    assert res.status_code == 200
    report = res.json()
    assert "total_scenarios_evaluated" in report
    assert report["total_scenarios_evaluated"] == 5
    assert 0.0 <= report["mean_attack_detection_rate"] <= 1.0
    assert 0.0 <= report["mean_false_positive_rate"] <= 1.0
    assert 0.0 <= report["mean_recovery_efficiency"] <= 1.0
    assert len(report["scenarios"]) == 5


def test_defense_simulate_endpoint(client: TestClient) -> None:
    """Verify on-demand execution of isolated simulation scenario."""
    payload = {
        "scenario": "DATA_CORRUPTION",
        "seed": 42,
        "target_feature": "oni_aso_degc",
        "perturbation_magnitude": 1.0,
        "injection_ratio": 0.35,
    }
    res = client.post("/api/v1/defense/simulate", json=payload)
    assert res.status_code == 200
    result = res.json()
    assert result["scenario"] == "DATA_CORRUPTION"
    assert result["seed"] == 42
    assert 0.0 <= result["attack_detection_rate"] <= 1.0
    assert 0.0 <= result["false_positive_rate"] <= 1.0
    assert "detector_flags" in result
    assert "detector_classifications" in result


def test_defense_inspect_endpoint(client: TestClient) -> None:
    """Verify inspection of telemetry records against transparent statistical checks."""
    payload = {
        "series_id": "test_stream_01",
        "records": [
            {"date": "2024-01", "oni_anomaly_degc": 0.4, "sst_degc": 26.5, "precip_mm": 80.0},
            {"date": "2024-02", "oni_anomaly_degc": -999.0, "sst_degc": 45.0, "precip_mm": -10.0},
        ],
    }
    res = client.post("/api/v1/defense/inspect", json=payload)
    assert res.status_code == 200
    report = res.json()
    assert report["series_id"] == "test_stream_01"
    assert report["passed"] is False
    assert report["anomaly_count"] >= 3
    # Invariant: Never marked confirmed malicious
    for anom in report["anomalies"]:
        assert anom["is_confirmed_malicious"] is False
