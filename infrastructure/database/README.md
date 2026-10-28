# ENSO Shield Database Infrastructure

PostgreSQL 16 relational database for operational telemetry, service readiness, and cryptographic provenance logging.

## Database Guidelines
- **Additive migrations only:** Never drop tables or delete existing data in migrations or tests.
- **Idempotent scripts:** All SQL statements must be safe to run multiple times (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
- **PostGIS Extension:** Deferred until spatial polygon operations or complex spatial intersections are justified (see `RD-005`).

## Connection Settings
Settings are supplied exclusively via environment variables:
- `ENSO_DB_HOST` (default: `127.0.0.1` locally, `db` in Docker)
- `ENSO_DB_PORT` (default: `5432`)
- `ENSO_DB_USER` (default: `enso`)
- `ENSO_DB_PASSWORD` (default: `enso_dev_password`)
- `ENSO_DB_NAME` (default: `enso_shield`)
