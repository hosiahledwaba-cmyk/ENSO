"""Integration tests for regional climate-risk dashboard and historical comparisons APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_regional_forecast_dashboard_endpoint(client: TestClient) -> None:
    """Verify regional dashboard returns subregions with anomalies, probabilities, uncertainty, and provenance."""
    res = client.get("/api/v1/forecast/regional")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "operational"
    assert data["issue_year"] == 2026
    assert data["convective_season"] == "DJF 2025/26"
    assert "macro_enso_state" in data
    assert "subregions" in data
    assert len(data["subregions"]) == 4

    # Check Limpopo subregion item
    limpopo = next((s for s in data["subregions"] if s["region_id"] == "ZA_LIMPOPO"), None)
    assert limpopo is not None
    assert "Northern Limpopo River Basin" in limpopo["region_name"]
    assert limpopo["lat_bounds"] == [-25.0, -22.0]
    assert limpopo["lon_bounds"] == [27.0, 32.0]
    assert limpopo["centroid"] == [-23.5, 29.5]

    # Verify rainfall anomalies
    anomaly = limpopo["rainfall_anomaly"]
    assert "october_zscore" in anomaly
    assert "october_observed_mm" in anomaly
    assert "departure_pct" in anomaly

    # Verify probabilistic forecast and uncertainty indicators
    fc = limpopo["forecast"]
    assert 0.0 <= fc["probability"] <= 1.0
    assert fc["risk_category"] in {"Normal", "Elevated", "High", "Critical"}
    assert fc["risk_ratio"] > 0.0

    uncertainty = limpopo["uncertainty"]
    assert uncertainty["ci_90_lower"] <= fc["probability"] <= uncertainty["ci_90_upper"]
    assert uncertainty["confidence_level_pct"] == 90
    assert uncertainty["margin_of_error"] > 0.0

    # Verify validity period
    validity = limpopo["validity_period"]
    assert validity["forecast_issue_date"] == "2025-11-01"
    assert validity["convective_season"] == "DJF 2025/26"
    assert validity["lead_time_days"] == 30

    # Verify provenance and data trust status
    prov = limpopo["provenance"]
    assert len(prov["source_datasets"]) >= 3
    assert prov["verification_status"] == "VERIFIED_INTEGRITY"
    assert len(prov["model_artefact_digest"]) == 64

    trust = limpopo["data_trust"]
    assert trust["status"] == "VERIFIED"
    assert trust["trust_score"] >= 90

    # Verify strict tripartite epistemic triad
    triad = limpopo["epistemic_triad"]
    assert triad["historical_observation"]["classification"] == "HISTORICAL_OBSERVATION"
    assert triad["model_estimate"]["classification"] == "MODEL_ESTIMATE"
    assert triad["official_external_forecast"]["classification"] == "OFFICIAL_EXTERNAL_FORECAST"


def test_regional_forecast_epistemic_separation_notice(client: TestClient) -> None:
    """Verify explicit notice that simulated perturbation results are never displayed as live forecasts."""
    res = client.get("/api/v1/forecast/regional")
    assert res.status_code == 200
    data = res.json()
    assert "EPISTEMIC SEPARATION" in data["epistemic_notice"]
    assert "Simulated perturbation results" in data["epistemic_notice"]
    assert "never displayed as live forecasts" in data["epistemic_notice"]


def test_historical_comparisons_endpoint(client: TestClient) -> None:
    """Verify multi-year historical comparison records between observations, models, and official forecasts."""
    res = client.get("/api/v1/forecast/historical-comparisons")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "operational"
    assert "comparisons" in data
    assert len(data["comparisons"]) >= 5

    # Check 1983 severe drought season (super El Niño)
    s83 = next((c for c in data["comparisons"] if c["season_year"] == 1983), None)
    assert s83 is not None
    assert s83["historical_observation"]["target_drought_observed"] == 1
    assert s83["historical_observation"]["djf_rainfall_mm"] < 250.0
    assert s83["historical_observation"]["epistemic_tag"] == "HISTORICAL_OBSERVATION"

    # Verify model estimate separation
    assert s83["model_estimate"]["epistemic_tag"] == "MODEL_ESTIMATE"
    assert s83["model_estimate"]["drought_probability"] > 0.30

    # Verify official external forecast separation
    assert s83["official_external_forecast"]["epistemic_tag"] == "OFFICIAL_EXTERNAL_FORECAST"
    assert "Below-Normal" in s83["official_external_forecast"]["official_tercile"]

    # Verify diagnostic verdict
    assert "True Positive" in s83["diagnostic_verdict"] or "False" in s83["diagnostic_verdict"]
