"""Database connection pool management, schema migrations, and persistence using asyncpg."""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any

import asyncpg

from enso_api.config import Settings

logger = logging.getLogger("enso_api.db")

_pool: asyncpg.Pool | None = None

MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name VARCHAR(64) PRIMARY KEY,
    service_version VARCHAR(32) NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS provenance_ledger (
    artifact_id VARCHAR(128) PRIMARY KEY,
    artifact_name VARCHAR(255) NOT NULL,
    sha256_hash CHAR(64) NOT NULL,
    source_url TEXT,
    byte_size BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_provenance_hash ON provenance_ledger (sha256_hash);
CREATE INDEX IF NOT EXISTS idx_provenance_recorded_at ON provenance_ledger (recorded_at);

CREATE TABLE IF NOT EXISTS jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    job_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB DEFAULT NULL,
    error_detail TEXT DEFAULT NULL,
    logs TEXT DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs (job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_started_at ON jobs (started_at DESC);

CREATE TABLE IF NOT EXISTS forecast_audit_log (
    prediction_id VARCHAR(64) PRIMARY KEY,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    issue_year INT NOT NULL,
    features JSONB NOT NULL,
    predicted_probability DOUBLE PRECISION NOT NULL,
    risk_category VARCHAR(32) NOT NULL,
    is_scenario BOOLEAN NOT NULL DEFAULT FALSE,
    uncertainty_info JSONB DEFAULT NULL,
    client_ip VARCHAR(64) DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forecast_audit_created ON forecast_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_audit_year ON forecast_audit_log (issue_year);

CREATE TABLE IF NOT EXISTS climate_source_coverage (
    source_id VARCHAR(64) PRIMARY KEY,
    provider_name VARCHAR(128) NOT NULL,
    dataset_name VARCHAR(255) NOT NULL,
    dataset_version VARCHAR(64) NOT NULL,
    frequency VARCHAR(32) NOT NULL DEFAULT 'monthly',
    expected_units JSONB NOT NULL DEFAULT '{}'::jsonb,
    spatial_coverage TEXT DEFAULT NULL,
    earliest_observation DATE DEFAULT NULL,
    latest_observation DATE DEFAULT NULL,
    total_records INT NOT NULL DEFAULT 0,
    missing_periods JSONB NOT NULL DEFAULT '[]'::jsonb,
    publication_delay_days INT DEFAULT 15,
    last_checked_at TIMESTAMPTZ DEFAULT NULL,
    last_success_at TIMESTAMPTZ DEFAULT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'INITIALIZED',
    last_error TEXT DEFAULT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_climate_coverage_status ON climate_source_coverage (status);
CREATE INDEX IF NOT EXISTS idx_climate_coverage_checked ON climate_source_coverage (last_checked_at DESC);

CREATE TABLE IF NOT EXISTS climate_ingestion_log (
    id BIGSERIAL PRIMARY KEY,
    job_id VARCHAR(64) REFERENCES jobs(job_id) ON DELETE SET NULL,
    source_id VARCHAR(64) NOT NULL,
    lifecycle_stage VARCHAR(32) NOT NULL,
    records_inserted INT NOT NULL DEFAULT 0,
    records_updated INT NOT NULL DEFAULT 0,
    records_skipped INT NOT NULL DEFAULT 0,
    records_rejected INT NOT NULL DEFAULT 0,
    earliest_date_ingested DATE DEFAULT NULL,
    latest_date_ingested DATE DEFAULT NULL,
    raw_artifact_sha256 CHAR(64) DEFAULT NULL,
    cleaned_artifact_sha256 CHAR(64) DEFAULT NULL,
    validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT DEFAULT NULL,
    duration_ms INT DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_climate_ingest_source ON climate_ingestion_log (source_id);
CREATE INDEX IF NOT EXISTS idx_climate_ingest_created ON climate_ingestion_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_climate_ingest_stage ON climate_ingestion_log (lifecycle_stage);

CREATE TABLE IF NOT EXISTS preparedness_action_states (
    action_id VARCHAR(64) PRIMARY KEY,
    tier VARCHAR(32) NOT NULL,
    tier_label VARCHAR(64) NOT NULL,
    threshold_min_pct DOUBLE PRECISION NOT NULL,
    threshold_max_pct DOUBLE PRECISION NOT NULL,
    sector VARCHAR(64) NOT NULL,
    action_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    lead_agency VARCHAR(255) NOT NULL,
    target_subregions JSONB NOT NULL DEFAULT '[]'::jsonb,
    lead_time_days INT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'MONITORING',
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    operator_notes TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_preparedness_status ON preparedness_action_states (status);
CREATE INDEX IF NOT EXISTS idx_preparedness_tier ON preparedness_action_states (tier);

CREATE TABLE IF NOT EXISTS preparedness_action_audit_log (
    id BIGSERIAL PRIMARY KEY,
    action_id VARCHAR(64) NOT NULL REFERENCES preparedness_action_states(action_id) ON DELETE CASCADE,
    from_status VARCHAR(32) NOT NULL,
    to_status VARCHAR(32) NOT NULL,
    operator_name VARCHAR(128) NOT NULL,
    notes TEXT DEFAULT NULL,
    dispatch_type VARCHAR(64) NOT NULL DEFAULT 'RECORDED_WORKFLOW_STATE',
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    execution_error TEXT DEFAULT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preparedness_audit_action ON preparedness_action_audit_log (action_id);
CREATE INDEX IF NOT EXISTS idx_preparedness_audit_time ON preparedness_action_audit_log (recorded_at DESC);

INSERT INTO preparedness_action_states (
    action_id, tier, tier_label, threshold_min_pct, threshold_max_pct,
    sector, action_name, description, lead_agency, target_subregions,
    lead_time_days, status, last_updated_at, operator_notes
)
VALUES
    (
        'ACT_AGRI_01', 'ELEVATED', 'Elevated Risk (25% - 40%)', 25.0, 40.0,
        'AGRICULTURE', 'Agro-Ecological Advisory & Soil Moisture Conservation Alert',
        'Issue early advisory to agricultural extension officers across Limpopo and Western Maize belt promoting minimum tillage, mulching, and delayed dry planting.',
        'DALRRD Agricultural Extension Directorate', '["ZA_LIMPOPO", "ZA_MAIZE_WEST"]'::jsonb,
        14, 'TRIGGERED', '2026-10-28T02:00:00Z', 'Alert dispatched to district extension hubs ahead of November planting window.'
    ),
    (
        'ACT_AGRI_02', 'HIGH', 'High Risk (40% - 60%)', 40.0, 60.0,
        'AGRICULTURE', 'Drought-Tolerant Sorghum & Millet Seed Voucher Distribution',
        'Trigger anticipatory voucher distribution for short-season, drought-tolerant grain varieties (sorghum, cowpeas, pearl millet) to replace water-intensive maize.',
        'South African Grain Information Service (SAGIS) & Agricultural Research Council (ARC)', '["ZA_LIMPOPO", "ZA_MAIZE_WEST"]'::jsonb,
        21, 'TRIGGERED', '2026-10-28T02:30:00Z', 'Triggered by operational model forecast exceeding 40% threshold (42.8% estimated).'
    ),
    (
        'ACT_WATER_01', 'ELEVATED', 'Elevated Risk (25% - 40%)', 25.0, 40.0,
        'WATER_RESOURCES', 'Limpopo & Olifants Catchment Storage Audit & Loss Prevention',
        'Conduct structural audit of major irrigation canals and municipal bulk pipelines; inspect community boreholes and groundwater extraction sensors.',
        'Department of Water and Sanitation (DWS) & Limpopo Catchment Agency', '["ZA_LIMPOPO", "ZA_SRZ"]'::jsonb,
        30, 'READY', '2026-10-27T18:00:00Z', 'Maintenance teams on standby.'
    ),
    (
        'ACT_WATER_02', 'HIGH', 'High Risk (40% - 60%)', 40.0, 60.0,
        'WATER_RESOURCES', 'Anticipatory Irrigation Scheme Water Quota Adjustments',
        'Gazette voluntary 15% reduction in commercial irrigation abstractions; reserve upstream dam capacity for livestock and essential domestic potable supplies.',
        'Catchment Management Agencies (Limpopo & Inkomati-Usuthu)', '["ZA_LIMPOPO", "ZA_MAIZE_WEST"]'::jsonb,
        15, 'TRIGGERED', '2026-10-28T02:45:00Z', 'Advisory sent to Irrigation Boards for December implementation.'
    ),
    (
        'ACT_LIVESTOCK_01', 'HIGH', 'High Risk (40% - 60%)', 40.0, 60.0,
        'LIVESTOCK', 'Pastoral Fodder Banking & Destocking Assistance Setup',
        'Establish community fodder storage depots in communal grazing areas; register commercial abattoir transport subsidies for proactive herd destocking.',
        'National Agricultural Marketing Council (NAMC) & Red Meat Producers Organisation', '["ZA_LIMPOPO", "ZA_MAIZE_WEST"]'::jsonb,
        25, 'TRIGGERED', '2026-10-28T03:00:00Z', 'Feed reserves mobilized in Vhembe and Capricorn districts.'
    ),
    (
        'ACT_DISASTER_01', 'HIGH', 'High Risk (40% - 60%)', 40.0, 60.0,
        'DISASTER_RELIEF', 'Anticipatory Action Contingency Fund Release Notice',
        'Notify Provincial Disaster Management Centres (PDMCs) in Limpopo, Free State, and North West to unlock anticipatory resilience financing ahead of peak summer deficit.',
        'National Disaster Management Centre (NDMC)', '["ZA_SRZ", "ZA_LIMPOPO", "ZA_MAIZE_WEST", "ZA_MAIZE_EAST"]'::jsonb,
        10, 'READY', '2026-10-28T01:15:00Z', 'Contingency allocation staged for release upon SADC SARCOF confirmation.'
    ),
    (
        'ACT_DISASTER_02', 'CRITICAL', 'Critical Risk (> 60%)', 60.0, 100.0,
        'DISASTER_RELIEF', 'Emergency Food Security Safety Net & Bulk Water Trucking Mobilization',
        'Deploy emergency social grant top-ups for subsistence farming households; preposition high-capacity mobile water tankers in rural municipal wards.',
        'Department of Social Development & South African National Defence Force (SANDF)', '["ZA_LIMPOPO", "ZA_MAIZE_WEST"]'::jsonb,
        7, 'MONITORING', '2026-10-27T12:00:00Z', 'On standby. Requires regional forecast probability >= 60%.'
    )
ON CONFLICT (action_id) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES
    ('0001_initial_baseline', 'Initial database baseline: tracking and heartbeats.'),
    ('0002_jobs_and_forecast_audit', 'Additive migration: jobs and forecast audit log.'),
    ('0003_climate_sources_and_daily_ingestion', 'Additive migration: climate source coverage and daily ingestion tracking.'),
    ('0004_preparedness_action_executions', 'Additive migration: persistent preparedness action states and audit logs.')
ON CONFLICT (version) DO NOTHING;
"""


async def apply_migrations(pool: asyncpg.Pool) -> None:
    """Apply idempotent database schema migrations."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(MIGRATIONS_DDL)
        logger.info("Database schema migrations verified and applied successfully.")
    except Exception as exc:
        logger.error("Failed to apply database migrations: %s", exc)


async def init_db(settings: Settings) -> asyncpg.Pool | None:
    """Initialize connection pool and apply schema migrations if database is configured."""
    global _pool
    dsn = settings.effective_database_dsn
    if not dsn:
        logger.info("Database host not configured; database integration disabled.")
        return None

    try:
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            timeout=settings.db_connect_timeout,
            command_timeout=settings.db_connect_timeout,
        )
        logger.info("Database connection pool initialized successfully.")
        await apply_migrations(_pool)
        return _pool
    except Exception as exc:
        logger.warning("Database connection pool failed to initialize: %s", exc)
        _pool = None
        return None


async def close_db() -> None:
    """Close connection pool on application shutdown."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
            logger.info("Database connection pool closed.")
        except Exception as exc:
            logger.warning("Error closing database connection pool: %s", exc)
        finally:
            _pool = None


def get_pool() -> asyncpg.Pool | None:
    """Return active connection pool."""
    return _pool


async def check_database_readiness(settings: Settings) -> dict[str, Any]:
    """Execute a lightweight probe to verify database connectivity and response."""
    dsn = settings.effective_database_dsn
    if not dsn:
        return {"status": "disabled", "latency_ms": None}

    pool = get_pool()
    start_time = time.perf_counter()

    try:
        if pool is not None:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        else:
            conn = await asyncpg.connect(dsn=dsn, timeout=settings.db_connect_timeout)
            try:
                await conn.fetchval("SELECT 1")
            finally:
                await conn.close()

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {"status": "connected", "latency_ms": latency_ms}
    except Exception as exc:
        logger.warning("Database readiness probe failed: %s", exc)
        return {
            "status": "unreachable",
            "latency_ms": None,
            "detail": "Database connection refused or timed out",
        }


# ---------------------------------------------------------------------------
# Job Orchestration Persistence
# ---------------------------------------------------------------------------


async def db_save_job(job_id: str, job_type: str, parameters: dict[str, Any]) -> None:
    """Insert initial job record into database if pool is active."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO jobs (job_id, job_type, status, parameters, logs, started_at)
                VALUES ($1, $2, 'running', $3::jsonb, '', NOW())
                ON CONFLICT (job_id) DO NOTHING
                """,
                job_id,
                job_type,
                json.dumps(parameters),
            )
    except Exception as exc:
        logger.warning("Failed to persist job record %s: %s", job_id, exc)


async def db_update_job(
    job_id: str,
    status: str,
    result: dict[str, Any] | None,
    error_detail: str | None,
    logs: str,
) -> None:
    """Update job status, result, error, and logs upon completion or failure."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE jobs
                SET status = $2,
                    result = $3::jsonb,
                    error_detail = $4,
                    logs = $5,
                    completed_at = NOW()
                WHERE job_id = $1
                """,
                job_id,
                status,
                json.dumps(result) if result is not None else None,
                error_detail,
                logs,
            )
    except Exception as exc:
        logger.warning("Failed to update job record %s: %s", job_id, exc)


async def db_get_job(job_id: str) -> dict[str, Any] | None:
    """Retrieve job record by ID."""
    pool = get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT job_id, job_type, status, parameters, result, error_detail, logs,
                       started_at, completed_at
                FROM jobs
                WHERE job_id = $1
                """,
                job_id,
            )
            if row is None:
                return None
            return {
                "job_id": row["job_id"],
                "job_type": row["job_type"],
                "status": row["status"],
                "parameters": json.loads(row["parameters"]) if row["parameters"] else {},
                "result": json.loads(row["result"]) if row["result"] else None,
                "error_detail": row["error_detail"],
                "logs": row["logs"] or "",
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            }
    except Exception as exc:
        logger.warning("Failed to fetch job record %s: %s", job_id, exc)
        return None


async def db_list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent job records ordered by start timestamp."""
    pool = get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT job_id, job_type, status, parameters, result, error_detail, logs,
                       started_at, completed_at
                FROM jobs
                ORDER BY started_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "job_id": r["job_id"],
                    "job_type": r["job_type"],
                    "status": r["status"],
                    "parameters": json.loads(r["parameters"]) if r["parameters"] else {},
                    "result": json.loads(r["result"]) if r["result"] else None,
                    "error_detail": r["error_detail"],
                    "logs": r["logs"] or "",
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to list jobs: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Forecast Audit Logging
# ---------------------------------------------------------------------------


async def db_save_forecast_audit(
    prediction_id: str,
    model_name: str,
    model_version: str,
    issue_year: int,
    features: dict[str, Any],
    predicted_probability: float,
    risk_category: str,
    is_scenario: bool,
    uncertainty_info: dict[str, Any] | None,
    client_ip: str | None,
) -> None:
    """Log an inference forecast request for cyber-resilience monitoring."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO forecast_audit_log (
                    prediction_id, model_name, model_version, issue_year, features,
                    predicted_probability, risk_category, is_scenario, uncertainty_info, client_ip
                )
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9::jsonb, $10)
                ON CONFLICT (prediction_id) DO NOTHING
                """,
                prediction_id,
                model_name,
                model_version,
                issue_year,
                json.dumps(features),
                predicted_probability,
                risk_category,
                is_scenario,
                json.dumps(uncertainty_info) if uncertainty_info is not None else None,
                client_ip,
            )
    except Exception as exc:
        logger.warning("Failed to log forecast audit record %s: %s", prediction_id, exc)


async def db_list_forecast_audits(limit: int = 50) -> list[dict[str, Any]]:
    """List recent forecast audit records."""
    pool = get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT prediction_id, model_name, model_version, issue_year, features,
                       predicted_probability, risk_category, is_scenario, uncertainty_info,
                       client_ip, created_at
                FROM forecast_audit_log
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "prediction_id": r["prediction_id"],
                    "model_name": r["model_name"],
                    "model_version": r["model_version"],
                    "issue_year": r["issue_year"],
                    "features": json.loads(r["features"]) if r["features"] else {},
                    "predicted_probability": r["predicted_probability"],
                    "risk_category": r["risk_category"],
                    "is_scenario": r["is_scenario"],
                    "uncertainty_info": json.loads(r["uncertainty_info"])
                    if r["uncertainty_info"]
                    else None,
                    "client_ip": r["client_ip"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to list forecast audits: %s", exc)
        return []


async def db_get_table_counts() -> dict[str, int]:
    """Retrieve row counts for database diagnostics."""
    pool = get_pool()
    if pool is None:
        return {}
    counts: dict[str, int] = {}
    tables = [
        "schema_migrations",
        "service_heartbeats",
        "provenance_ledger",
        "jobs",
        "forecast_audit_log",
        "climate_source_coverage",
        "climate_ingestion_log",
        "preparedness_action_states",
        "preparedness_action_audit_log",
    ]
    try:
        async with pool.acquire() as conn:
            for table in tables:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                counts[table] = int(count or 0)
    except Exception as exc:
        logger.warning("Failed to fetch table counts: %s", exc)
    return counts


# ---------------------------------------------------------------------------
# Cryptographic Provenance Ledger Persistence
# ---------------------------------------------------------------------------


async def db_save_provenance_record(
    artifact_id: str,
    artifact_name: str,
    sha256_hash: str,
    source_url: str | None,
    byte_size: int,
    metadata: dict[str, Any],
) -> None:
    """Insert or update a cryptographic provenance manifest in the ledger."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO provenance_ledger (
                    artifact_id, artifact_name, sha256_hash,
                    source_url, byte_size, metadata, recorded_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
                ON CONFLICT (artifact_id) DO UPDATE
                SET artifact_name = EXCLUDED.artifact_name,
                    sha256_hash = EXCLUDED.sha256_hash,
                    source_url = EXCLUDED.source_url,
                    byte_size = EXCLUDED.byte_size,
                    metadata = EXCLUDED.metadata,
                    recorded_at = NOW()
                """,
                artifact_id,
                artifact_name,
                sha256_hash,
                source_url,
                byte_size,
                json.dumps(metadata),
            )
    except Exception as exc:
        logger.warning("Failed to persist provenance record %s: %s", artifact_id, exc)


async def db_list_provenance_records() -> list[dict[str, Any]]:
    """Retrieve all recorded cryptographic provenance entries ordered by timestamp."""
    pool = get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT artifact_id, artifact_name, sha256_hash,
                       source_url, byte_size, recorded_at, metadata
                FROM provenance_ledger
                ORDER BY recorded_at DESC
                """
            )
            return [
                {
                    "artifact_id": r["artifact_id"],
                    "artifact_name": r["artifact_name"],
                    "sha256_hash": r["sha256_hash"],
                    "source_url": r["source_url"],
                    "byte_size": r["byte_size"],
                    "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to list provenance records from DB: %s", exc)
        return []


def _parse_date(val: str | None) -> date | None:
    """Safely convert ISO date/month string to datetime.date for asyncpg."""
    if not val:
        return None
    try:
        parts = str(val).strip().split("-")
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        elif len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2].split("T")[0]))
    except (ValueError, TypeError, IndexError):
        pass
    return None


async def db_upsert_climate_coverage(
    source_id: str,
    provider_name: str,
    dataset_name: str,
    dataset_version: str,
    frequency: str = "monthly",
    expected_units: dict[str, str] | None = None,
    spatial_coverage: str | None = None,
    earliest_observation: str | None = None,
    latest_observation: str | None = None,
    total_records: int = 0,
    missing_periods: list[str] | None = None,
    publication_delay_days: int = 15,
    status: str = "INITIALIZED",
    last_error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Upsert climate source coverage and tracking metadata."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO climate_source_coverage (
                    source_id, provider_name, dataset_name, dataset_version,
                    frequency, expected_units, spatial_coverage,
                    earliest_observation, latest_observation, total_records,
                    missing_periods, publication_delay_days, last_checked_at,
                    last_success_at, status, last_error, metadata, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6::jsonb, $7,
                    $8, $9, $10,
                    $11::jsonb, $12, NOW(),
                    CASE WHEN $13 = 'ERROR' THEN NULL ELSE NOW() END,
                    $13, $14, $15::jsonb, NOW()
                )
                ON CONFLICT (source_id) DO UPDATE
                SET provider_name = EXCLUDED.provider_name,
                    dataset_name = EXCLUDED.dataset_name,
                    dataset_version = EXCLUDED.dataset_version,
                    frequency = EXCLUDED.frequency,
                    expected_units = EXCLUDED.expected_units,
                    spatial_coverage = EXCLUDED.spatial_coverage,
                    earliest_observation = COALESCE(EXCLUDED.earliest_observation, climate_source_coverage.earliest_observation),
                    latest_observation = COALESCE(EXCLUDED.latest_observation, climate_source_coverage.latest_observation),
                    total_records = EXCLUDED.total_records,
                    missing_periods = EXCLUDED.missing_periods,
                    publication_delay_days = EXCLUDED.publication_delay_days,
                    last_checked_at = NOW(),
                    last_success_at = CASE WHEN EXCLUDED.status = 'ERROR' THEN climate_source_coverage.last_success_at ELSE NOW() END,
                    status = EXCLUDED.status,
                    last_error = EXCLUDED.last_error,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                source_id,
                provider_name,
                dataset_name,
                dataset_version,
                frequency,
                json.dumps(expected_units or {}),
                spatial_coverage,
                _parse_date(earliest_observation),
                _parse_date(latest_observation),
                total_records,
                json.dumps(missing_periods or []),
                publication_delay_days,
                status,
                last_error,
                json.dumps(metadata or {}),
            )
    except Exception as exc:
        logger.warning("Failed to upsert climate source coverage for %s: %s", source_id, exc)


async def db_get_climate_coverage(source_id: str | None = None) -> list[dict[str, Any]]:
    """Retrieve coverage records for all or a specific climate source."""
    pool = get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            if source_id:
                rows = await conn.fetch(
                    "SELECT * FROM climate_source_coverage WHERE source_id = $1 ORDER BY source_id",
                    source_id,
                )
            else:
                rows = await conn.fetch("SELECT * FROM climate_source_coverage ORDER BY source_id")

            return [
                {
                    "source_id": r["source_id"],
                    "provider_name": r["provider_name"],
                    "dataset_name": r["dataset_name"],
                    "dataset_version": r["dataset_version"],
                    "frequency": r["frequency"],
                    "expected_units": json.loads(r["expected_units"])
                    if r["expected_units"]
                    else {},
                    "spatial_coverage": r["spatial_coverage"],
                    "earliest_observation": r["earliest_observation"].isoformat()
                    if r["earliest_observation"]
                    else None,
                    "latest_observation": r["latest_observation"].isoformat()
                    if r["latest_observation"]
                    else None,
                    "total_records": r["total_records"],
                    "missing_periods": json.loads(r["missing_periods"])
                    if r["missing_periods"]
                    else [],
                    "publication_delay_days": r["publication_delay_days"],
                    "last_checked_at": r["last_checked_at"].isoformat()
                    if r["last_checked_at"]
                    else None,
                    "last_success_at": r["last_success_at"].isoformat()
                    if r["last_success_at"]
                    else None,
                    "status": r["status"],
                    "last_error": r["last_error"],
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to fetch climate source coverage: %s", exc)
        return []


async def db_record_ingestion_log(
    source_id: str,
    lifecycle_stage: str,
    job_id: str | None = None,
    records_inserted: int = 0,
    records_updated: int = 0,
    records_skipped: int = 0,
    records_rejected: int = 0,
    earliest_date_ingested: str | None = None,
    latest_date_ingested: str | None = None,
    raw_artifact_sha256: str | None = None,
    cleaned_artifact_sha256: str | None = None,
    validation_warnings: list[str] | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Record a lifecycle transition or completed run in climate_ingestion_log."""
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO climate_ingestion_log (
                    job_id, source_id, lifecycle_stage,
                    records_inserted, records_updated, records_skipped, records_rejected,
                    earliest_date_ingested, latest_date_ingested,
                    raw_artifact_sha256, cleaned_artifact_sha256,
                    validation_warnings, error_message, duration_ms, created_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9,
                    $10, $11, $12::jsonb, $13, $14, NOW()
                )
                """,
                job_id,
                source_id,
                lifecycle_stage,
                records_inserted,
                records_updated,
                records_skipped,
                records_rejected,
                _parse_date(earliest_date_ingested),
                _parse_date(latest_date_ingested),
                raw_artifact_sha256,
                cleaned_artifact_sha256,
                json.dumps(validation_warnings or []),
                error_message,
                duration_ms,
            )
    except Exception as exc:
        logger.warning("Failed to record climate ingestion log for %s: %s", source_id, exc)


async def db_list_ingestion_logs(
    limit: int = 50,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical ingestion execution logs."""
    pool = get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            if source_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM climate_ingestion_log
                    WHERE source_id = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    source_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM climate_ingestion_log
                    ORDER BY created_at DESC LIMIT $1
                    """,
                    limit,
                )

            return [
                {
                    "id": r["id"],
                    "job_id": r["job_id"],
                    "source_id": r["source_id"],
                    "lifecycle_stage": r["lifecycle_stage"],
                    "records_inserted": r["records_inserted"],
                    "records_updated": r["records_updated"],
                    "records_skipped": r["records_skipped"],
                    "records_rejected": r["records_rejected"],
                    "earliest_date_ingested": r["earliest_date_ingested"].isoformat()
                    if r["earliest_date_ingested"]
                    else None,
                    "latest_date_ingested": r["latest_date_ingested"].isoformat()
                    if r["latest_date_ingested"]
                    else None,
                    "raw_artifact_sha256": r["raw_artifact_sha256"],
                    "cleaned_artifact_sha256": r["cleaned_artifact_sha256"],
                    "validation_warnings": json.loads(r["validation_warnings"])
                    if r["validation_warnings"]
                    else [],
                    "error_message": r["error_message"],
                    "duration_ms": r["duration_ms"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to list climate ingestion logs: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Preparedness Action States & Audit Persistence
# ---------------------------------------------------------------------------


class PreparednessTransitionError(Exception):
    """Raised when an illegal or unsupported preparedness status transition is attempted."""


class PreparednessActionNotFoundError(Exception):
    """Raised when the requested preparedness action ID does not exist."""


VALID_ACTION_STATUSES = {"MONITORING", "READY", "TRIGGERED", "EXECUTED"}

# Allowed status transitions
PERMITTED_TRANSITIONS: dict[str, set[str]] = {
    "MONITORING": {"MONITORING", "READY", "TRIGGERED"},
    "READY": {"READY", "TRIGGERED", "EXECUTED", "MONITORING"},
    "TRIGGERED": {"TRIGGERED", "EXECUTED", "READY", "MONITORING"},
    "EXECUTED": {"EXECUTED", "MONITORING", "READY"},
}


async def db_get_preparedness_actions() -> list[dict[str, Any]]:
    """Retrieve all preparedness action definitions with persisted state from PostgreSQL."""
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    action_id, tier, tier_label, threshold_min_pct, threshold_max_pct,
                    sector, action_name, description, lead_agency, target_subregions,
                    lead_time_days, status, last_updated_at, operator_notes
                FROM preparedness_action_states
                ORDER BY threshold_min_pct ASC, action_id ASC
                """
            )
            return [
                {
                    "id": r["action_id"],
                    "tier": r["tier"],
                    "tier_label": r["tier_label"],
                    "threshold_min_pct": float(r["threshold_min_pct"]),
                    "threshold_max_pct": float(r["threshold_max_pct"]),
                    "sector": r["sector"],
                    "action_name": r["action_name"],
                    "description": r["description"],
                    "lead_agency": r["lead_agency"],
                    "target_subregions": json.loads(r["target_subregions"])
                    if isinstance(r["target_subregions"], str)
                    else list(r["target_subregions"]),
                    "lead_time_days": int(r["lead_time_days"]),
                    "status": r["status"],
                    "last_updated_at": r["last_updated_at"].isoformat()
                    if r["last_updated_at"]
                    else None,
                    "operator_notes": r["operator_notes"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to retrieve preparedness actions from database: %s", exc)
        return []


async def db_update_preparedness_action_state(
    action_id: str,
    target_status: str,
    operator_name: str,
    notes: str,
    dispatch_type: str = "RECORDED_WORKFLOW_STATE",
    is_simulated: bool = False,
) -> dict[str, Any]:
    """Atomically update action status in PostgreSQL with concurrency protection and audit log.

    Uses SELECT ... FOR UPDATE within a transaction to prevent race conditions or conflicting updates.
    Validates that target_status is permitted and follows state machine transitions.
    """
    target_status = target_status.upper()
    if target_status not in VALID_ACTION_STATUSES:
        raise PreparednessTransitionError(
            f"Invalid target status '{target_status}'. Permitted: {sorted(VALID_ACTION_STATUSES)}"
        )

    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database connection pool is not initialized.")

    async with pool.acquire() as conn, conn.transaction():
        # Concurrency control: acquire exclusive row lock
        row = await conn.fetchrow(
            """
                SELECT * FROM preparedness_action_states
                WHERE action_id = $1 OR UPPER(action_id) = UPPER($1)
                FOR UPDATE
                """,
            action_id,
        )
        if not row:
            raise PreparednessActionNotFoundError(
                f"Preparedness action '{action_id}' not found in database registry."
            )

        current_status = row["status"]
        matched_id = row["action_id"]

        # Validate permitted transition
        allowed = PERMITTED_TRANSITIONS.get(current_status, VALID_ACTION_STATUSES)
        if target_status not in allowed:
            raise PreparednessTransitionError(
                f"Illegal transition from '{current_status}' to '{target_status}'. "
                f"Permitted next states: {sorted(allowed)}"
            )

        formatted_notes = f"[{operator_name}] {notes}"

        # Update action state
        updated_row = await conn.fetchrow(
            """
                UPDATE preparedness_action_states
                SET status = $2,
                    last_updated_at = NOW(),
                    operator_notes = $3
                WHERE action_id = $1
                RETURNING *
                """,
            matched_id,
            target_status,
            formatted_notes,
        )

        # Record audit log entry
        await conn.execute(
            """
                INSERT INTO preparedness_action_audit_log (
                    action_id, from_status, to_status, operator_name,
                    notes, dispatch_type, is_simulated, recorded_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                """,
            matched_id,
            current_status,
            target_status,
            operator_name,
            notes,
            dispatch_type,
            is_simulated,
        )

        return {
            "id": updated_row["action_id"],
            "tier": updated_row["tier"],
            "tier_label": updated_row["tier_label"],
            "threshold_min_pct": float(updated_row["threshold_min_pct"]),
            "threshold_max_pct": float(updated_row["threshold_max_pct"]),
            "sector": updated_row["sector"],
            "action_name": updated_row["action_name"],
            "description": updated_row["description"],
            "lead_agency": updated_row["lead_agency"],
            "target_subregions": json.loads(updated_row["target_subregions"])
            if isinstance(updated_row["target_subregions"], str)
            else list(updated_row["target_subregions"]),
            "lead_time_days": int(updated_row["lead_time_days"]),
            "status": updated_row["status"],
            "last_updated_at": updated_row["last_updated_at"].isoformat()
            if updated_row["last_updated_at"]
            else None,
            "operator_notes": updated_row["operator_notes"],
            "dispatch_type": dispatch_type,
            "is_simulated": is_simulated,
        }


async def db_get_preparedness_audit_log(
    action_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve historical execution and status transition audit log for preparedness actions."""
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            if action_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM preparedness_action_audit_log
                    WHERE action_id = $1 OR UPPER(action_id) = UPPER($1)
                    ORDER BY recorded_at DESC LIMIT $2
                    """,
                    action_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM preparedness_action_audit_log
                    ORDER BY recorded_at DESC LIMIT $1
                    """,
                    limit,
                )

            return [
                {
                    "id": r["id"],
                    "action_id": r["action_id"],
                    "from_status": r["from_status"],
                    "to_status": r["to_status"],
                    "operator_name": r["operator_name"],
                    "notes": r["notes"],
                    "dispatch_type": r["dispatch_type"],
                    "is_simulated": r["is_simulated"],
                    "execution_error": r["execution_error"],
                    "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning("Failed to retrieve preparedness audit log: %s", exc)
        return []
