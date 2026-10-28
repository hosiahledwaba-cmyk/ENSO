"""Runtime configuration loaded exclusively from environment variables.

No secrets or deployment-specific values are hardcoded here; defaults are
safe, local-development values only. See the repository `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _split_csv(value: object) -> object:
    """Allow list settings to be supplied as comma-separated strings."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Validated API settings. All fields map to `ENSO_*` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="ENSO_",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    env: Environment = "development"
    log_level: LogLevel = "INFO"
    api_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    api_allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    api_docs_enabled: bool | None = None

    # Database settings
    db_host: str | None = None
    db_port: int = 5432
    db_user: str = "enso"
    db_password: str = "enso_dev_password"  # noqa: S105
    db_name: str = "enso_shield"
    database_url: str | None = None
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_connect_timeout: float = 3.0

    @field_validator("api_cors_origins", "api_allowed_hosts", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("api_cors_origins")
    @classmethod
    def _validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if "*" in origin:
                raise ValueError(
                    "Wildcard CORS origins are not permitted; list origins explicitly."
                )
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"CORS origin must include an http(s) scheme: {origin!r}")
            if origin.endswith("/"):
                raise ValueError(f"CORS origin must not have a trailing slash: {origin!r}")
        return origins

    @field_validator("api_allowed_hosts")
    @classmethod
    def _validate_hosts(cls, hosts: list[str]) -> list[str]:
        if not hosts:
            raise ValueError("At least one allowed host must be configured.")
        if "*" in hosts:
            raise ValueError("Wildcard allowed hosts are not permitted; list hosts explicitly.")
        return hosts

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production":
            insecure = [o for o in self.api_cors_origins if o.startswith("http://")]
            if insecure:
                raise ValueError(f"Production CORS origins must use https: {insecure}")
            if self.db_password == "enso_dev_password" and (  # noqa: S105
                self.db_host or self.database_url
            ):
                raise ValueError(
                    "Production database must not use the default development password."
                )
        return self

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs default to off in production unless explicitly enabled."""
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return self.env != "production"

    @property
    def effective_database_dsn(self) -> str | None:
        """Construct standard PostgreSQL connection DSN for asyncpg."""
        if self.database_url:
            # Convert standard postgresql+asyncpg:// if provided
            url = self.database_url
            if url.startswith("postgresql+asyncpg://"):
                url = "postgresql://" + url[len("postgresql+asyncpg://") :]
            return url
        if self.db_host:
            return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
