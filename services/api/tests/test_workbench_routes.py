from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_system_status_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "enso-shield-api"
    assert "database" in data
    assert "pipelines" in data
    assert "active_jobs" in data


def test_datasets_endpoints(client: TestClient) -> None:
    res = client.get("/api/v1/datasets")
    assert res.status_code == 200
    data = res.json()
    assert "datasets" in data
    assert isinstance(data["datasets"], list)
    assert len(data["datasets"]) >= 3

    res_prov = client.get("/api/v1/provenance/datasets")
    assert res_prov.status_code == 200
    assert "records" in res_prov.json()


def test_features_status_endpoint(client: TestClient) -> None:
    res = client.get("/api/v1/features/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "exists" in data


def test_models_endpoints(client: TestClient) -> None:
    res = client.get("/api/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert isinstance(data["models"], list)

    res_active = client.get("/api/v1/models/active")
    assert res_active.status_code == 200
    active = res_active.json()
    assert "model_id" in active


def test_experiments_endpoints(client: TestClient) -> None:
    res = client.get("/api/v1/experiments")
    assert res.status_code == 200
    data = res.json()
    assert "experiments" in data
    assert isinstance(data["experiments"], list)

    res_latest = client.get("/api/v1/experiments/latest")
    assert res_latest.status_code == 200


def test_forecast_predict_valid_scenario(client: TestClient) -> None:
    payload = {
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "nino34_aso_anom_degc": 1.20,
        "precip_oct_mm": 33.15,
        "precip_antecedent_spring_mm": 48.65,
        "issue_year": 2026,
        "threshold": 0.5,
        "is_scenario": True,
    }
    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "prediction_id" in data
    assert "predicted_probability" in data
    assert 0.0 <= data["predicted_probability"] <= 1.0
    assert data["data_origin_type"] == "user_scenario"
    assert "SCENARIO EXPLORATION" in data["disclaimer"]
    assert "uncertainty" in data
    assert data["uncertainty"]["climatological_base_rate"] is not None


def test_forecast_predict_invalid_threshold(client: TestClient) -> None:
    payload = {
        "oni_aso_degc": 1.45,
        "precip_oct_zscore": -0.82,
        "nino34_aso_anom_degc": 1.20,
        "issue_year": 2026,
        "threshold": 1.5,  # Invalid: must be <= 1.0
        "is_scenario": True,
    }
    response = client.post("/api/v1/forecast/predict", json=payload)
    assert response.status_code == 422


def test_job_submission_and_retrieval(client: TestClient) -> None:
    res = client.post("/api/v1/ingestion/jobs", json={"use_fixtures": True})
    assert res.status_code == 202
    job_info = res.json()
    assert "job_id" in job_info
    job_id = job_info["job_id"]

    # Poll status
    res_status = client.get(f"/api/v1/jobs/{job_id}")
    assert res_status.status_code == 200
    job_record = res_status.json()
    assert job_record["job_type"] == "ingestion"
    assert job_record["status"] in ("pending", "running", "completed")


def test_job_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/jobs/job_nonexistent_xyz")
    assert res.status_code == 404
