-- Migration 0003: Public climate sources coverage and automated daily ingestion tracking
-- Strictly additive and idempotent: Never drops tables or deletes existing data.

-- 1. Persistent climate source coverage and tracking registry
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

-- 2. Daily ingestion lifecycle execution and validation audit log
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

-- Record migration 0003
INSERT INTO schema_migrations (version, description)
VALUES ('0003_climate_sources_and_daily_ingestion', 'Additive migration: climate source coverage registry and automated daily ingestion lifecycle logs.')
ON CONFLICT (version) DO NOTHING;
