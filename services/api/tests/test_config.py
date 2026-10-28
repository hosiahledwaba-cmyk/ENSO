from __future__ import annotations

import pytest
from pydantic import ValidationError

from enso_api.config import Settings


def test_csv_env_values_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENSO_API_CORS_ORIGINS", "http://a.test, https://b.test")
    monkeypatch.setenv("ENSO_API_ALLOWED_HOSTS", "a.test,b.test")
    settings = Settings()
    assert settings.api_cors_origins == ["http://a.test", "https://b.test"]
    assert settings.api_allowed_hosts == ["a.test", "b.test"]


def test_empty_env_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENSO_API_DOCS_ENABLED", "")
    monkeypatch.setenv("ENSO_ENV", "")
    settings = Settings()
    assert settings.api_docs_enabled is None
    assert settings.env == "development"
    assert settings.docs_enabled


@pytest.mark.parametrize(
    "origin",
    ["*", "https://*.example.com", "example.com", "https://example.com/"],
)
def test_invalid_cors_origins_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(api_cors_origins=[origin])


def test_wildcard_allowed_host_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(api_allowed_hosts=["*"])


def test_empty_allowed_hosts_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(api_allowed_hosts=[])


def test_production_requires_https_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(env="production", api_cors_origins=["http://enso.example"])


def test_invalid_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(env="staging")


def test_docs_flag_override() -> None:
    settings = Settings(
        env="production",
        api_cors_origins=[],
        api_docs_enabled=True,
        db_password="prod_safe_password",
    )
    assert settings.docs_enabled
    assert not Settings(env="development", api_docs_enabled=False).docs_enabled


def test_database_dsn_construction() -> None:
    settings = Settings(
        db_host="postgres-host",
        db_port=5432,
        db_user="testuser",
        db_password="secretpassword",
        db_name="testdb",
    )
    assert (
        settings.effective_database_dsn
        == "postgresql://testuser:secretpassword@postgres-host:5432/testdb"
    )


def test_database_url_override() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@remote:5433/somedb",
        db_host="ignored-host",
    )
    assert settings.effective_database_dsn == "postgresql://user:pass@remote:5433/somedb"


def test_database_dsn_none_when_unconfigured() -> None:
    settings = Settings(db_host=None, database_url=None)
    assert settings.effective_database_dsn is None


def test_production_rejects_default_dev_password() -> None:
    with pytest.raises(ValidationError, match="default development password"):
        Settings(
            env="production",
            api_cors_origins=["https://secure.example.com"],
            db_host="db.internal",
            db_password="enso_dev_password",
        )


def test_production_accepts_custom_db_password() -> None:
    settings = Settings(
        env="production",
        api_cors_origins=["https://secure.example.com"],
        db_host="db.internal",
        db_password="strong_custom_password_123",
    )
    assert (
        settings.effective_database_dsn
        == "postgresql://enso:strong_custom_password_123@db.internal:5432/enso_shield"
    )
