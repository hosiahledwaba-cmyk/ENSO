-- ENSO Shield Database Baseline Initialization Schema
-- Additive and Idempotent: Never drops tables or deletes existing data.

-- 1. Schema migration and version tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Record baseline migration
INSERT INTO schema_migrations (version, description)
VALUES ('0001_initial_baseline', 'Initial database baseline: migration tracking, heartbeats, and provenance log.')
ON CONFLICT (version) DO NOTHING;

-- 2. Service heartbeats and readiness log
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name VARCHAR(64) PRIMARY KEY,
    service_version VARCHAR(32) NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 3. Cryptographic provenance records (ledger for immutable raw and feature files)
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

-- 4. Asynchronous job orchestration records
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

-- 5. Forecast inference audit log
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

-- Record migration 0002
INSERT INTO schema_migrations (version, description)
VALUES ('0002_jobs_and_forecast_audit', 'Additive migration: background job tracking and forecast inference audit logging.')
ON CONFLICT (version) DO NOTHING;

-- 6. Climate source coverage registry
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

-- 7. Automated daily ingestion lifecycle execution log
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

-- 8. Persistent Preparedness Action State and Execution Audit Log
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

-- Seed default standardized anticipatory actions idempotently
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

-- Record migration 0004
INSERT INTO schema_migrations (version, description)
VALUES ('0004_preparedness_action_executions', 'Additive migration: persistent preparedness action states and audit logs.')
ON CONFLICT (version) DO NOTHING;



