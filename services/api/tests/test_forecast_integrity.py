"""Scientific integrity regression tests for the forecast prediction pipeline.

Verifies:
1. Reproduction of historical anomaly with hardcoded deluge rainfall.
2. Rejection of unverified synthetic spring rainfall derivation (HTTP 422 when omitted).
3. Retrieval of ground truth observed features for historical operational seasons (is_scenario=false).
4. Physical consistency constraint: spring rainfall (Sep+Oct) cannot be less than October rainfall alone.
5. Additive logit decomposition invariant: intercept + sum(contributions) == total_logit.
6. Directional alignment of physical drought risk factors (dry rainfall and warm SST increase risk).
7. Transparent disclosure of heuristic confidence bounds (is_statistically_rigorous_ci=false).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from ml.inference.predictor import EnsoRiskPredictor


@pytest.fixture
def active_predictor() -> EnsoRiskPredictor:
    model_dir = Path("models/logistic_regression_baseline")
    return EnsoRiskPredictor(model_dir)


def test_reproduction_of_historical_suspicious_prediction(
    active_predictor: EnsoRiskPredictor,
) -> None:
    """Verify exact reproduction of pred_f9fb9b6d2b89 when hardcoded dummy features were used."""
    features = {
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "nino34_aso_anom_degc": 1.2,
        "oni_trend_aso_jas_degc": 0.0,
        "oni_trend_aso_jja_degc": 0.0,
        "nino34_aso_sst_degc": 28.2,
        "nino34_oct_anom_degc": 1.2,
        "nino34_trend_oct_aug_degc": 0.0,
        "precip_oct_mm": 50.0,
        "precip_antecedent_spring_mm": 100.0,
    }

    result = active_predictor.predict_risk(features, decision_threshold=0.5)

    assert result["drought_probability"] == 0.1237
    assert result["climatological_base_rate"] == 0.2000
    assert result["risk_ratio"] == 0.618
    assert result["risk_category"] == "Normal / Low Drought Risk"

    contribs = result["factor_contributions"]
    assert contribs["precip_antecedent_spring_mm"] == -1.0771
    assert contribs["nino34_aso_sst_degc"] == 0.4814
    assert contribs["oni_aso_degc"] == 0.4678


def test_missing_spring_rainfall_scenario_rejected(client: TestClient) -> None:
    """Verify that omitting precip_antecedent_spring_mm in a scenario returns HTTP 422."""
    payload = {
        "issue_year": 2026,
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "nino34_aso_anom_degc": 1.20,
        "threshold": 0.50,
        "is_scenario": True,
        # precip_antecedent_spring_mm omitted
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 422
    assert (
        "Missing required scenario input 'precip_antecedent_spring_mm'" in response.json()["detail"]
    )


def test_physically_inconsistent_spring_rainfall_rejected(client: TestClient) -> None:
    """Verify that spring rainfall < October rainfall (negative September rainfall) is rejected."""
    payload = {
        "issue_year": 2026,
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": 0.0,
        "precip_oct_mm": 50.0,
        "precip_antecedent_spring_mm": 30.0,  # Physically impossible: Sep = 30 - 50 = -20 mm
        "nino34_aso_anom_degc": 1.20,
        "threshold": 0.50,
        "is_scenario": True,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 422
    assert "Physical inconsistency" in response.json()["detail"]


def test_explicit_scenario_prediction_with_full_features(client: TestClient) -> None:
    """Verify scenario prediction with explicitly supplied antecedent spring rainfall."""
    payload = {
        "issue_year": 2026,
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "precip_oct_mm": 33.15,
        "precip_antecedent_spring_mm": 48.65,
        "nino34_aso_anom_degc": 1.20,
        "threshold": 0.50,
        "is_scenario": True,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["issue_year"] == 2026
    assert data["forecast_issue_date"] == "2025-11-01"
    assert data["forecast_target"] == "severe_drought_p20_djf"

    inputs = data["inputs_validated"]
    assert inputs["oni_aso_degc"] == 1.45
    assert inputs["precip_oct_zscore"] == -0.82
    assert inputs["precip_oct_mm_resolved"] == 33.15
    assert inputs["precip_antecedent_spring_mm_resolved"] == 48.65

    # Elevated risk should be around 42.8%
    prob = data["predicted_probability"]
    assert 0.420 <= prob <= 0.435
    assert data["risk_category"] == "Elevated Drought Risk"

    # Disclosure of statistical limitation
    assert data["uncertainty"]["is_statistically_rigorous_ci"] is False
    assert "UNRESOLVED STATISTICAL LIMITATION" in data["uncertainty"]["statistical_notice"]


def test_operational_prediction_retrieves_ground_truth_for_historical_season(
    client: TestClient,
) -> None:
    """Verify that is_scenario=false retrieves genuine observed features from labelled store."""
    payload = {
        "issue_year": 1983,  # Historical season in labelled features
        "threshold": 0.50,
        "is_scenario": False,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["issue_year"] == 1983
    assert data["data_origin_type"] == "operational_pipeline"
    assert "EXPERIMENTAL BASELINE FORECAST" in data["disclaimer"]

    # Ground truth values for 1983 from enso_rainfall_features_labelled.csv:
    inputs = data["inputs_validated"]
    assert inputs["oni_aso_degc"] == 1.6
    assert inputs["precip_oct_mm_resolved"] == 25.0
    assert inputs["precip_antecedent_spring_mm_resolved"] == 37.4


def test_operational_prediction_unobserved_year_rejected(client: TestClient) -> None:
    """Verify that is_scenario=false for unobserved season (e.g. 2026 without CHIRPS backfill) returns 422."""
    payload = {
        "issue_year": 2026,
        "threshold": 0.50,
        "is_scenario": False,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 422
    assert (
        "Operational feature vector for season year 2026 is not available"
        in response.json()["detail"]
    )


def test_logit_decomposition_invariant(client: TestClient) -> None:
    """Verify mathematical invariant: intercept + sum(contributions) == total_logit -> sigmoid."""
    payload = {
        "issue_year": 2026,
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "precip_oct_mm": 33.15,
        "precip_antecedent_spring_mm": 48.65,
        "nino34_aso_anom_degc": 1.20,
        "threshold": 0.50,
        "is_scenario": True,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    uncertainty = data["uncertainty"]

    base_intercept = uncertainty["base_logit_intercept"]
    total_logit = uncertainty["total_logit"]
    contributions = uncertainty["factor_contributions"]

    sum_contribs = sum(contributions.values())
    expected_logit = round(base_intercept + sum_contribs, 4)

    assert abs(total_logit - expected_logit) < 1e-3

    expected_prob = 1.0 / (1.0 + np.exp(-total_logit))
    assert abs(data["predicted_probability"] - expected_prob) < 1e-3


def test_directional_impact_of_drought_factors(client: TestClient) -> None:
    """Verify all drought-indicating features have positive contribution to drought log-odds."""
    payload = {
        "issue_year": 2026,
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "precip_oct_mm": 33.15,
        "precip_antecedent_spring_mm": 48.65,
        "nino34_aso_anom_degc": 1.20,
        "threshold": 0.50,
        "is_scenario": True,
    }

    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    details = data["uncertainty"]["feature_details"]

    factor_map = {d["feature_name"]: d for d in details}

    assert factor_map["oni_aso_degc"]["logit_contribution"] > 0
    assert factor_map["oni_aso_degc"]["impact_direction"] == "increases_drought_odds"

    assert factor_map["precip_oct_zscore"]["logit_contribution"] > 0
    assert factor_map["precip_oct_zscore"]["impact_direction"] == "increases_drought_odds"

    assert factor_map["precip_oct_mm"]["logit_contribution"] > 0
    assert factor_map["precip_oct_mm"]["impact_direction"] == "increases_drought_odds"

    assert factor_map["precip_antecedent_spring_mm"]["logit_contribution"] > 0
    assert factor_map["precip_antecedent_spring_mm"]["impact_direction"] == "increases_drought_odds"
