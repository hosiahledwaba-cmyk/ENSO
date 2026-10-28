/**
 * Platform capabilities categorized by genuine implementation and verification status.
 *
 * Operational modules have working code, automated test verification, and CLI workflows.
 * In-progress modules have partial integration (e.g. health probes without inference routers).
 * Planned modules represent future milestones (sensors, attack simulation).
 */

export type ModuleStatus = 'verified' | 'in_progress' | 'planned'

export interface PlatformModule {
  id: string
  title: string
  status: ModuleStatus
  statusLabel: string
  description: string
  verificationEvidence?: string
  command?: string
}

export const PLATFORM_MODULES: readonly PlatformModule[] = [
  // Operational (Verified via CLI & Test Suite)
  {
    id: 'data-ingestion',
    title: 'Climate data ingestion',
    status: 'verified',
    statusLabel: 'Operational (CLI)',
    description:
      'Validated ingestion of CHIRPS precipitation, NOAA ONI, and Niño 3.4 SST with bounds validation, zero silent imputation, and SHA-256 provenance tracking.',
    verificationEvidence: 'Verified offline with 18 automated tests (test_data_ingestion.py).',
    command: 'make ingest USE_FIXTURES=1',
  },
  {
    id: 'feature-pipeline',
    title: 'Target & feature pipeline',
    status: 'verified',
    statusLabel: 'Operational (CLI)',
    description:
      'Zero-lookahead feature extraction (Nov 1 issue date), training-only seasonal reference distribution (μ, σ, τ₂₀, τ₃₃), and severe drought target labelling.',
    verificationEvidence: 'Verified offline with 21 automated tests (test_features.py).',
    command: 'make features USE_FIXTURES=1',
  },
  {
    id: 'model-evaluation',
    title: 'Baseline & nonlinear modeling',
    status: 'verified',
    statusLabel: 'Operational (CLI)',
    description:
      'Seasonal climatology, L2 logistic regression, and CPU-friendly XGBoost evaluated via walk-forward CV, holdout testing, and Murphy/ECE calibration diagnostics.',
    verificationEvidence:
      'Verified offline with 27 automated tests (test_training_and_evaluation.py, test_experiment_comparison.py).',
    command: 'make experiment-compare USE_FIXTURES=1',
  },
  {
    id: 'research-protocol',
    title: 'Living research manuscript',
    status: 'verified',
    statusLabel: 'Operational (Maintained)',
    description:
      'Pre-registered research protocol, claims-and-evidence matrix, empirical experiment log, and evolving Springer LNCS manuscript.',
    verificationEvidence:
      'Continuously maintained with verified empirical metrics and decision records (RD-001–RD-009).',
    command: 'research/paper/manuscript.md',
  },
  // In Progress (Integration Pending)
  {
    id: 'api-service',
    title: 'Web API & model serving',
    status: 'in_progress',
    statusLabel: 'In Progress (Partial)',
    description:
      'FastAPI service currently exposes /health and /health/ready probes. Prediction (/forecast/predict) and dataset catalog routers are scheduled for the next API milestone.',
    verificationEvidence:
      'Verified health & readiness probes; Swagger UI exposes active routes.',
    command: 'http://localhost:8000/docs',
  },
  {
    id: 'database-storage',
    title: 'PostgreSQL database ledger',
    status: 'in_progress',
    statusLabel: 'In Progress (Partial)',
    description:
      'Baseline schemas created (schema_migrations, service_heartbeats, provenance_ledger) and asyncpg connectivity verified; business persistence awaits API router integration.',
    verificationEvidence: 'Active connection and readiness probes verified.',
    command: 'infrastructure/database/init.sql',
  },
  // Planned (Future Milestones)
  {
    id: 'sensor-network',
    title: 'Field sensor network',
    status: 'planned',
    statusLabel: 'Planned (Milestone 3)',
    description:
      'Simulated and physical field sensor telemetry streams for localized agrometeorological monitoring.',
    verificationEvidence:
      'Architecture defined in protocol; implementation scheduled for Milestone 3.',
  },
  {
    id: 'threat-simulation',
    title: 'Cyber threat & defense suite',
    status: 'planned',
    statusLabel: 'Planned (Milestone 4)',
    description:
      'Adversarial False Data Injection (FDI) simulation, sensor replay attacks, and dynamic defensive screening.',
    verificationEvidence:
      'Threat model pre-registered in research protocol; implementation scheduled for Milestone 4.',
  },
]

// Backwards-compatibility aliases
export const PLANNED_MODULES = PLATFORM_MODULES
export type PlannedModule = PlatformModule

