from __future__ import annotations

import pytest
from enso_api import __version__
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "enso-shield-api",
        "version": __version__,
    }


def test_health_is_not_cached(client: TestClient) -> None:
    assert client.get("/health").headers["Cache-Control"] == "no-store"


def test_health_rejects_non_get_methods(client: TestClient) -> None:
    assert client.post("/health").status_code == 405
    assert client.delete("/health").status_code == 405


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/predictions").status_code == 404


def test_health_ready_disabled_returns_ok(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "enso-shield-api"
    assert data["version"] == __version__
    assert data["database"]["status"] == "disabled"
    assert response.headers["Cache-Control"] == "no-store"


def test_health_ready_connected(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    async def mock_check(settings: object) -> dict[str, object]:
        return {"status": "connected", "latency_ms": 1.42}

    monkeypatch.setattr("enso_api.routes.health.check_database_readiness", mock_check)
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"]["status"] == "connected"
    assert data["database"]["latency_ms"] == 1.42


def test_health_ready_unreachable_returns_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    async def mock_check(settings: object) -> dict[str, object]:
        return {"status": "unreachable", "latency_ms": None, "detail": "Connection refused"}

    monkeypatch.setattr("enso_api.routes.health.check_database_readiness", mock_check)
    response = client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"]["status"] == "unreachable"
    assert data["database"]["detail"] == "Connection refused"


def test_health_ready_rejects_non_get(client: TestClient) -> None:
    assert client.post("/health/ready").status_code == 405
    assert client.put("/health/ready").status_code == 405
