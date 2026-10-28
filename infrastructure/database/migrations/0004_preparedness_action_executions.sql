-- Migration 0004: Persistent preparedness action states and audit logs
-- Strictly additive and idempotent: Never drops tables or deletes existing data.

-- 1. Persistent anticipatory action states table
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

-- 2. Audit log for tracking state machine transitions and execution dispatches
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

-- 3. Seed baseline operational actions
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

-- 4. Record migration 0004
INSERT INTO schema_migrations (version, description)
VALUES ('0004_preparedness_action_executions', 'Additive migration: persistent preparedness action states and audit logs.')
ON CONFLICT (version) DO NOTHING;
