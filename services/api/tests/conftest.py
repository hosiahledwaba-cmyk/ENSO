from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

# Ensure repo root and api src are on sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
API_SRC = REPO_ROOT / "services" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

import pytest
from fastapi.testclient import TestClient

from enso_api.config import Settings
from enso_api.main import create_app

ALLOWED_ORIGIN = "http://localhost:5173"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "test",
        "api_cors_origins": [ALLOWED_ORIGIN],
        "api_allowed_hosts": ["testserver"],
    }
    base.update(overrides)
    return Settings.model_validate(base)


@pytest.fixture
def client_factory() -> Callable[..., TestClient]:
    def _factory(**overrides: object) -> TestClient:
        return TestClient(create_app(make_settings(**overrides)), raise_server_exceptions=False)

    return _factory


@pytest.fixture
def client(client_factory: Callable[..., TestClient]) -> TestClient:
    return client_factory()
