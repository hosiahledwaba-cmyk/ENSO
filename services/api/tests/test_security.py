"""Security-boundary tests for the HTTP baseline."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import ALLOWED_ORIGIN


def test_security_headers_present(client: TestClient) -> None:
    headers = client.get("/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_security_headers_present_on_errors(client: TestClient) -> None:
    headers = client.get("/does-not-exist").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in headers


def test_untrusted_host_rejected(client: TestClient) -> None:
    response = client.get("/health", headers={"Host": "evil.example.com"})
    assert response.status_code == 400


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "access-control-allow-credentials" not in response.headers


def test_cors_ignores_unlisted_origin(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_preflight_rejects_unlisted_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400


def test_cors_preflight_rejects_unsafe_method(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "DELETE"},
    )
    assert response.status_code == 400


def test_unhandled_errors_do_not_leak_details(client: TestClient) -> None:
    app = client.app

    @app.get("/boom")  # type: ignore[attr-defined, untyped-decorator]
    def boom() -> None:
        raise RuntimeError("secret-internal-detail")

    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret-internal-detail" not in response.text


def test_docs_disabled_in_production(client_factory: Callable[..., TestClient]) -> None:
    prod = client_factory(env="production", api_cors_origins=["https://enso.example"])
    assert prod.get("/docs").status_code == 404
    assert prod.get("/openapi.json").status_code == 404


def test_docs_enabled_outside_production(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200
