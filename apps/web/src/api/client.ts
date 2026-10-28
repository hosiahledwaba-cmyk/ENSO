/**
 * ENSO Shield Workbench Typed API Client
 * Orchestrates calls to all backend system, data, features, model, experiment,
 * inference, and job orchestration endpoints.
 */

export interface DatabaseStatus {
  status: 'connected' | 'unreachable' | 'disabled'
  latency_ms: number | null
  detail?: string | null
  table_counts?: Record<string, number>
}

export interface PipelineHealth {
  datasets_operational: boolean
  features_operational: boolean
  active_model_operational: boolean
  latest_experiment_operational: boolean
}

export interface JobRecord {
  job_id: string
  job_type: 'ingestion' | 'features' | 'training' | 'experiment'
  status: 'pending' | 'running' | 'completed' | 'failed'
  created_at: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
  parameters: Record<string, unknown>
  result: Record<string, unknown> | null
  error_message: string | null
  logs: string
}

export interface SystemStatus {
  service: string
  version: string
  environment: string
  timestamp_utc: string
  database: DatabaseStatus
  pipelines: PipelineHealth
  active_jobs: JobRecord[]
}

export interface DatasetItem {
  source: string
  tier: 'raw' | 'cleaned' | 'derived'
  file_name: string
  file_path: string
  exists: boolean
  file_size_bytes: number | null
  record_count: number | null
  sha256: string | null
  is_fixture: boolean
  modified_at_utc: string | null
}

export interface DatasetListResponse {
  datasets: DatasetItem[]
  total_datasets: number
  cleaned_operational: boolean
}

export interface ProcessingStep {
  step_name: string
  timestamp_utc: string
  operator: string
  input_digests: Record<string, string>
  output_digest: string
  parameters: Record<string, unknown>
}

export interface ValidationOutcome {
  is_valid: boolean
  status: 'PASSED' | 'FAILED'
  total_records: number
  checks_count: number
  passed_checks: string[]
  failed_checks: string[]
  error_count: number
  errors: string[]
  warnings: string[]
  timestamp_utc: string
}

export interface ProvenanceRecord {
  manifest_version: string
  dataset_id: string
  source_identifier?: string
  source_name: string
  source_version: string
  dataset_version?: string
  source_url: string | null
  source_timestamp_utc?: string | null
  licence: string
  citation: string
  ingestion_timestamp_utc: string
  content_digest?: string
  raw_sha256: string
  cleaned_sha256: string | null
  derived_sha256: string | null
  record_count: number
  date_range: Record<string, string>
  units: Record<string, string>
  validation_status: string
  validation_outcome?: ValidationOutcome
  processing_history?: ProcessingStep[]
  authenticity_status?: 'AUTHENTIC_CONTROLLED_PIPELINE' | 'UNSIGNED_THIRD_PARTY' | 'SIGNATURE_INVALID'
  signature?: string | null
  signing_key_id?: string | null
  staleness_threshold_days?: number
  is_archival_benchmark?: boolean
  pipeline_version?: string
}

export interface ArtefactAuditResult {
  artefact_id: string
  file_name: string
  tier: string
  file_path: string
  exists: boolean
  byte_size: number
  content_integrity: 'VERIFIED' | 'TAMPERED' | 'MISSING_FILE'
  source_authenticity: 'AUTHENTIC_CONTROLLED_PIPELINE' | 'UNSIGNED_THIRD_PARTY' | 'SIGNATURE_INVALID'
  scientific_validity: 'VALID' | 'INVALID' | 'UNCHECKED'
  freshness_status: 'FRESH' | 'STALE_RECORD' | 'ARCHIVAL_BENCHMARK'
  expected_digest: string | null
  actual_digest: string | null
  digest_matches: boolean
  is_signed: boolean
  signing_key_id: string | null
  processing_steps_count: number
  authenticity_detail: string
  violations: Array<{
    violation_type: string
    severity: string
    artefact_id: string
    description: string
    enforced_action: string
    timestamp_utc: string
  }>
}

export interface ProvenanceAuditReport {
  audit_timestamp_utc: string
  overall_status: 'PASSED' | 'DEGRADED' | 'FAILED'
  total_artefacts: number
  verified_count: number
  tampered_count: number
  missing_files_count: number
  signed_pipeline_count: number
  unsigned_third_party_count: number
  invalid_signature_count: number
  valid_scientific_count: number
  fresh_count: number
  stale_count: number
  archival_benchmark_count: number
  untracked_files_count: number
  violations_count: number
  violations: Array<{
    violation_type: string
    severity: string
    artefact_id: string
    description: string
    enforced_action: string
    timestamp_utc: string
  }>
  artefacts: ArtefactAuditResult[]
}

export interface DatasetTimeseriesResponse {
  region_id: string
  region_name: string
  rainfall_monthly: Array<{ date: string; precip_mm: number }>
  oni_monthly: Array<{ date: string; oni_anomaly_degc: number }>
  seasonal_history: Array<{
    season_year: number
    seasonal_precip_djf_mm?: number
    oni_aso_degc?: number
    target_drought_p20?: number
    precip_oct_zscore?: number
  }>
  reference_distribution: {
    mean_seasonal_precip_mm?: number
    std_seasonal_precip_mm?: number
    tau_drought_p20_mm?: number
    tau_below_normal_p33_mm?: number
  }
  coverage: {
    rainfall_months: number
    oni_months: number
    seasonal_seasons: number
    start_year: number
    end_year: number
    missing_periods: string[]
    is_fixture_coverage: boolean
  }
}

export interface ProvenanceListResponse {
  records: ProvenanceRecord[]
  count: number
  provenance_dir: string
}

export interface AnomalyDetectionItem {
  timestamp?: string | null
  feature_name: string
  observed_value: unknown
  expected_range: string
  anomaly_type:
    | 'IMPOSSIBLE_VALUE'
    | 'SUDDEN_CHANGE'
    | 'MISSING_DATA'
    | 'TIMESTAMP_IRREGULARITY'
    | 'REPLAY_OBSERVATION'
    | 'CROSS_SOURCE_INCONSISTENCY'
    | 'MULTIVARIATE_OUTLIER'
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
  classification:
    | 'MEASUREMENT_NOISE'
    | 'DATA_QUALITY_ANOMALY'
    | 'SUSPICIOUS_ANOMALY'
    | 'POTENTIAL_ADVERSARIAL_PERTURBATION'
    | 'CLEAN_BENCHMARK'
  suspicion_score: number
  detail: string
  is_confirmed_malicious: boolean
}

export interface DefenseCheckResultItem {
  check_name: string
  passed: boolean
  anomaly_count: number
  anomalies: AnomalyDetectionItem[]
}

export interface DefensiveInspectionReportItem {
  series_id: string
  total_records: number
  passed: boolean
  anomaly_count: number
  anomalies: AnomalyDetectionItem[]
  check_summaries: DefenseCheckResultItem[]
  baseline_detector_score: number | null
  overall_classification: string
  summary: string
}

export interface SimulationScenarioMetadata {
  id: string
  name: string
  category: string
  description: string
  threat_model_ref: string
  default_magnitude: number
  default_ratio: number
}

export interface SimulationConfigItem {
  scenario:
    | 'DATA_CORRUPTION'
    | 'REPLAY_ATTACK'
    | 'MEASUREMENT_NOISE'
    | 'MISSING_DATA'
    | 'ADVERSARIAL_FDI'
  seed?: number
  target_feature?: string
  perturbation_magnitude?: number
  injection_ratio?: number
  description?: string
}

export interface SimulationScenarioResultItem {
  scenario: string
  seed: number
  target_feature: string
  total_samples: number
  injected_samples: number
  detected_samples: number
  clean_samples: number
  false_alarms: number
  attack_detection_rate: number
  false_positive_rate: number
  detection_delay_timesteps: number
  clean_brier_score: number
  attack_brier_score: number
  defended_brier_score: number
  brier_score_degradation: number
  defensive_recovery_efficiency: number
  mean_probability_shift: number
  risk_category_flips: number
  ground_truth_labels: number[]
  detector_flags: boolean[]
  detector_classifications: string[]
  summary: string
}

export interface SimulationReportItem {
  timestamp_utc: string
  random_seed: number
  total_scenarios_evaluated: number
  mean_attack_detection_rate: number
  mean_false_positive_rate: number
  mean_recovery_efficiency: number
  scenarios: SimulationScenarioResultItem[]
}

export interface FeaturesStatusResponse {
  status: 'operational' | 'unconfigured' | 'missing'
  exists: boolean
  features_csv: string
  row_count: number | null
  feature_count: number | null
  features: string[]
  seasons: number[]
  sha256: string | null
  reference_distribution: {
    mean?: number
    std?: number
    p20?: number
    p33?: number
  } | null
}

export interface ActiveModelResponse {
  model_id: string
  model_architecture: string
  model_version: string
  target_variable: string
  dataset_fingerprint: string
  training_seasons: number[]
  holdout_seasons: number[]
  feature_columns: string[]
  coefficients: Record<string, number>
  intercept: number
  baseline_metrics: Record<string, number>
  logistic_metrics: Record<string, number>
  holdout_superiority_confirmed: boolean
  scientific_notice: string
  approval_status?: string
  artefact_digest?: string
  training_data_fingerprint?: string
  audit?: ModelAuditItem
}

export interface ModelAuditItem {
  model_id: string
  model_dir: string
  manifest_found: boolean
  manifest_version?: string
  model_version?: string
  approval_status: string
  is_approved: boolean
  artefact_found: boolean
  expected_digest: string
  observed_digest: string
  digest_matches: boolean
  feature_count: number
  quarantined: boolean
  quarantine_dossier_id?: string | null
  audit_passed: boolean
  issues: string[]
}

export interface ModelsAuditResponse {
  audit_timestamp_utc: boolean
  total_scanned: number
  passed_count: number
  compromised_count: number
  quarantined_count: number
  posture: string
  models: ModelAuditItem[]
  quarantined_dossiers: QuarantineDossierItem[]
}

export interface QuarantineDossierItem {
  dossier_id: string
  model_id: string
  model_version: string
  original_model_path: string
  quarantine_store_path: string
  quarantined_at_utc: string
  reason: string
  details: string
  expected_digest: string
  observed_digest: string
  investigation_status: 'PENDING_REVIEW' | 'CONFIRMED_COMPROMISED' | 'CLEARED' | 'REPLACED'
  reviewer_notes?: string
  resolved_at_utc?: string | null
  replacement_model_id?: string | null
}

export interface PoisoningScenarioItem {
  attack_class: string
  name: string
  description: string
  parameters: Record<string, { type: string; default: number | string; min?: number; max?: number }>
  tested_threat: string
}

export interface PoisoningReportItem {
  experiment_id: string
  attack_class: string
  attack_description: string
  records_modified: number
  fraction_poisoned: number
  clean_training_fingerprint: string
  poisoned_training_fingerprint: string
  clean_holdout_brier_score: number
  poisoned_holdout_brier_score: number
  brier_score_degradation: number
  clean_holdout_bss: number | null
  poisoned_holdout_bss: number | null
  bss_degradation: number | null
  intercept_shift: number
  clean_intercept: number
  poisoned_intercept: number
  coefficient_shifts: Record<string, number>
  l2_weight_displacement: number
  flipped_holdout_predictions_count: number
  flipped_holdout_seasons: Array<{
    season_year: number
    ground_truth: number
    clean_probability: number
    poisoned_probability: number
    clean_prediction: number
    poisoned_prediction: number
    clean_category: string
    poisoned_category: string
  }>
  max_probability_drift: number
  tested_attack_class: string
  threat_limitations: string[]
  recovery_process: string[]
  remaining_risks: string[]
}

export interface ScientificComplexityVerdict {
  is_nonlinear_complexity_justified: boolean
  cv_bss_delta_xgboost_vs_logistic: number
  holdout_bss_delta_xgboost_vs_logistic: number
  best_holdout_model: string
  primary_failure_modes: string[]
  features_improving_performance: string[]
  justification_rationale: string
}

export interface ExperimentManifest {
  manifest_version: string
  experiment_id: string
  timestamp_utc: string
  random_seed: number
  software_versions: Record<string, string>
  dataset_fingerprint_sha256: string
  training_seasons: number[]
  holdout_seasons: number[]
  feature_columns: string[]
  rolling_origin_cv: Record<string, Record<string, number>>
  holdout_evaluation: Record<string, Record<string, number>>
  calibration_reports: Record<string, unknown>
  ablation_report: {
    target_column: string
    baseline_brier_skill_score: number
    ablations: Array<{
      ablated_feature: string
      cv_brier_score: number
      cv_brier_skill_score: number
      bss_delta: number
      feature_importance_rank: number
    }>
  }
  threshold_report: {
    primary_target_column: string
    primary_brier_skill_score: number
    alternative_targets: Array<{
      target_name: string
      quantile_threshold: number
      event_count: number
      event_frequency: number
      cv_brier_score: number
      cv_brier_skill_score: number
      holdout_brier_score: number
      holdout_brier_skill_score: number
    }>
  }
  verdict: ScientificComplexityVerdict
  location_report?: unknown
}

export interface FeatureDetail {
  feature_name: string
  raw_value: number
  scaler_mean: number
  scaler_scale: number
  standardized_z: number
  coefficient_weight: number
  logit_contribution: number
  marginal_prob_shift?: number
  impact_direction: string
}

export interface PredictionRequest {
  oni_aso_degc: number
  precip_oct_zscore: number
  nino34_aso_anom_degc: number
  precip_oct_mm?: number
  precip_antecedent_spring_mm?: number
  issue_year: number
  threshold: number
  is_scenario: boolean
}

export interface PredictionResponse {
  prediction_id: string
  model_name: string
  model_version: string
  issue_year: number
  forecast_target: string
  forecast_issue_date: string
  target_season_label?: string
  target_season_window?: string
  predicted_probability: number
  decision_threshold: number
  risk_category: string
  is_severe_drought: boolean
  data_origin_type: string
  disclaimer: string
  inputs_validated: Record<string, number>
  uncertainty: {
    climatological_base_rate?: number
    climatological_base_rate_ci_95?: [number, number]
    prediction_parameter_ci_95?: [number, number]
    is_calibrated?: boolean
    calibration_status?: string
    holdout_brier_skill_score?: number | null
    risk_ratio?: number
    base_logit_intercept?: number
    total_logit?: number
    logit_standard_error?: number
    factor_contributions?: Record<string, number>
    top_contributing_factors?: Record<string, number>
    feature_details?: FeatureDetail[]
    training_sample_seasons?: number
    holdout_sample_seasons?: number
    target_season_label?: string
    target_season_window?: string
    method?: string
    statistical_notice?: string
    is_statistically_rigorous_ci?: boolean
  }
  created_at: string
}

export interface IngestionCoverageItem {
  source_id: string
  provider_name: string
  dataset_name: string
  dataset_version: string
  temporal_frequency: string
  units: string
  spatial_coverage: string
  earliest_observation: string | null
  latest_observation: string | null
  latest_observation_date: string | null
  last_retrieval_timestamp: string | null
  last_checked_timestamp: string | null
  update_status: string
  record_count: number
  provenance_url: string | null
  checksum_sha256: string | null
  notes: string | null
}

export interface IngestionHistoryItem {
  log_id: string
  job_id: string
  source_id: string
  status: string
  start_time: string
  end_time: string | null
  records_added: number
  records_updated: number
  latest_observation: string | null
  validation_status: string | null
  warnings: string[]
  error_message: string | null
  checksum_sha256: string | null
}

export interface IngestionSchedulerStatus {
  is_running: boolean
  is_job_active: boolean
  next_run_time_utc: string | null
  cadence: string
  timezone: string
}

export interface IngestionTriggerResponse {
  status: string
  message: string
  job_id: string | null
}

export interface ForecastAuditItem {
  id?: number
  prediction_id: string
  model_name: string
  model_version: string
  issue_year: number
  features: Record<string, number>
  predicted_probability: number
  risk_category: string
  is_scenario: boolean
  uncertainty_info?: {
    wilson_ci_low?: number
    wilson_ci_high?: number
    [key: string]: unknown
  } | null
  client_ip?: string
  created_at: string
}

export interface SubregionRainfallAnomaly {
  october_zscore: number
  october_observed_mm: number
  october_normal_mm: number
  departure_pct: number
  metric_label: string
}

export interface SubregionForecast {
  probability: number
  decision_threshold: number
  risk_category: 'Normal' | 'Elevated' | 'High' | 'Critical'
  risk_ratio: number
  is_severe_drought: boolean
}

export interface SubregionUncertainty {
  ci_90_lower: number
  ci_90_upper: number
  margin_of_error: number
  confidence_level_pct: number
  method: string
}

export interface SubregionValidityPeriod {
  forecast_issue_date: string
  convective_season: string
  target_start_date: string
  target_end_date: string
  lead_time_days: number
  status: string
}

export interface SubregionProvenance {
  source_datasets: string[]
  training_data_fingerprint: string
  model_artefact_digest: string
  verification_status: string
}

export interface SubregionDataTrust {
  status: 'VERIFIED' | 'COMPROMISED' | 'UNVERIFIED'
  trust_score: number
  tamper_check: string
  signature: string
}

export interface EpistemicTriad {
  historical_observation: {
    classification: 'HISTORICAL_OBSERVATION'
    label: string
    details: string
    observed_value: number
    unit: string
  }
  model_estimate: {
    classification: 'MODEL_ESTIMATE'
    label: string
    details: string
    probability: number
  }
  official_external_forecast: {
    classification: 'OFFICIAL_EXTERNAL_FORECAST'
    label: string
    details: string
    tercile: string
  }
}

export interface SubregionForecastItem {
  region_id: string
  region_name: string
  lat_bounds: [number, number]
  lon_bounds: [number, number]
  centroid: [number, number]
  climatological_scaling_factor: number
  climatological_normal_djf_mm: number
  rainfall_anomaly: SubregionRainfallAnomaly
  forecast: SubregionForecast
  uncertainty: SubregionUncertainty
  validity_period: SubregionValidityPeriod
  provenance: SubregionProvenance
  data_trust: SubregionDataTrust
  epistemic_triad: EpistemicTriad
}

export interface RegionalForecastDashboardResponse {
  status: string
  issue_year: number
  convective_season: string
  forecast_issue_date: string
  model_id: string
  model_architecture: string
  macro_enso_state: {
    oni_aso_degc: number
    classification: string
    nino34_aso_anom_degc: number
  }
  epistemic_notice: string
  subregions: SubregionForecastItem[]
  total_subregions: number
  data_trust_summary: {
    overall_posture: string
    active_model_verified: boolean
    training_data_fingerprint: string
    artefact_digest: string
    quarantined_models_count: number
  }
}

export interface HistoricalComparisonRecord {
  season_year: number
  convective_season: string
  forecast_issue_date: string
  historical_observation: {
    djf_rainfall_mm: number
    target_drought_observed: number
    drought_label: string
    october_zscore: number
    oni_aso_degc: number
    epistemic_tag: 'HISTORICAL_OBSERVATION'
  }
  model_estimate: {
    drought_probability: number
    predicted_binary: number
    risk_category: string
    climatology_baseline_prob: number
    skill_advantage: number
    epistemic_tag: 'MODEL_ESTIMATE'
  }
  official_external_forecast: {
    official_tercile: string
    consensus_statement: string
    source: string
    epistemic_tag: 'OFFICIAL_EXTERNAL_FORECAST'
  }
  diagnostic_verdict: string
  split: string
}

export interface HistoricalComparisonsResponse {
  status: string
  comparisons: HistoricalComparisonRecord[]
  count: number
  epistemic_disclaimer: string
}

export interface PreparednessActionItem {
  id: string
  tier: 'NORMAL' | 'ELEVATED' | 'HIGH' | 'CRITICAL'
  tier_label: string
  threshold_min_pct: number
  threshold_max_pct: number
  sector: 'AGRICULTURE' | 'WATER_RESOURCES' | 'LIVESTOCK' | 'DISASTER_RELIEF'
  action_name: string
  description: string
  lead_agency: string
  target_subregions: string[]
  lead_time_days: number
  status: 'MONITORING' | 'READY' | 'TRIGGERED' | 'EXECUTED'
  last_updated_at: string
  operator_notes?: string | null
}

export interface PreparednessTriggerTier {
  tier: string
  label: string
  range: string
  status: string
  description: string
}

export interface PreparednessMatrixResponse {
  status: string
  operational_context: {
    issue_date: string
    convective_season: string
    forecast_probability_pct: number
    active_risk_tier: string
    active_risk_label: string
    climatological_base_rate_pct: number
    risk_ratio: number
    decision_rule: string
  }
  trigger_tiers: PreparednessTriggerTier[]
  actions_summary: {
    total_actions: number
    triggered: number
    executed: number
    ready: number
    monitoring: number
  }
  actions: PreparednessActionItem[]
}

export interface SecurityIncidentItem {
  id: string
  timestamp: string
  severity: 'CRITICAL' | 'WARNING' | 'INFO'
  subsystem: 'MODEL_ARTEFACT' | 'DATA_PROVENANCE' | 'DEFENSE_SCREENING' | 'SIMULATION'
  title: string
  description: string
  detection_rule: string
  affected_asset: string
  remediation_status: string
  epistemic_classification: 'OPERATIONAL_TELEMETRY' | 'SIMULATED_EXPERIMENT'
  technical_details: Record<string, unknown>
}

export interface SecurityIncidentsResponse {
  status: string
  incidents: SecurityIncidentItem[]
  total_count: number
  epistemic_notice: string
}

export interface SecuritySubsystemGate {
  subsystem: string
  gate_type: string
  status: string
  [key: string]: unknown
}

export interface SecuritySummaryResponse {
  overall_posture: 'HEALTHY' | 'DEGRADED' | 'COMPROMISED'
  data_trust_index: number
  active_quarantined_models: number
  subsystem_gates: SecuritySubsystemGate[]
  epistemic_rules_enforced: string[]
  last_audit_timestamp_utc: string
}

export interface ApiClientConfig {
  baseUrl: string
  fetchImpl?: typeof fetch
}

function cleanUrl(baseUrl: string, path: string): string {
  const normBase = baseUrl.replace(/\/+$/, '')
  const normPath = path.startsWith('/') ? path : `/${path}`
  return `${normBase}${normPath}`
}

export class ApiError extends Error {
  status: number
  body?: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function requestJson<T>(
  baseUrl: string,
  path: string,
  options: RequestInit = {},
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const url = cleanUrl(baseUrl, path)
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  if (options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetchImpl(url, { ...options, headers })
  if (!res.ok) {
    let errBody: unknown
    try {
      errBody = await res.json()
    } catch {
      errBody = await res.text()
    }
    const detail =
      errBody && typeof errBody === 'object' && 'detail' in errBody
        ? String((errBody as { detail: unknown }).detail)
        : `Request to ${path} failed with HTTP ${res.status}`
    throw new ApiError(res.status, detail, errBody)
  }

  return (await res.json()) as T
}

export function createApiClient(config: ApiClientConfig) {
  const { baseUrl, fetchImpl = fetch } = config

  return {
    async getSystemStatus(): Promise<SystemStatus> {
      return requestJson<SystemStatus>(baseUrl, '/api/v1/system/status', {}, fetchImpl)
    },

    async getDatasets(): Promise<DatasetListResponse> {
      return requestJson<DatasetListResponse>(baseUrl, '/api/v1/datasets', {}, fetchImpl)
    },

    async getDatasetTimeseries(): Promise<DatasetTimeseriesResponse> {
      return requestJson<DatasetTimeseriesResponse>(baseUrl, '/api/v1/datasets/timeseries', {}, fetchImpl)
    },

    async getProvenance(): Promise<ProvenanceListResponse> {
      return requestJson<ProvenanceListResponse>(baseUrl, '/api/v1/provenance/datasets', {}, fetchImpl)
    },

    async getProvenanceAudit(): Promise<ProvenanceAuditReport> {
      return requestJson<ProvenanceAuditReport>(baseUrl, '/api/v1/provenance/audit', {}, fetchImpl)
    },

    async verifyArtefact(params: { dataset_id?: string; file_path?: string }): Promise<ArtefactAuditResult> {
      return requestJson<ArtefactAuditResult>(
        baseUrl,
        '/api/v1/provenance/verify',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async startIngestionJob(params: { use_fixtures: boolean; source?: string }): Promise<{ job_id: string; message: string }> {
      return requestJson<{ job_id: string; message: string }>(
        baseUrl,
        '/api/v1/ingestion/jobs',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async getFeaturesStatus(): Promise<FeaturesStatusResponse> {
      return requestJson<FeaturesStatusResponse>(baseUrl, '/api/v1/features/status', {}, fetchImpl)
    },

    async startFeaturesJob(params: { include_lag1: boolean }): Promise<{ job_id: string; message: string }> {
      return requestJson<{ job_id: string; message: string }>(
        baseUrl,
        '/api/v1/features/jobs',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async getActiveModel(): Promise<ActiveModelResponse> {
      return requestJson<ActiveModelResponse>(baseUrl, '/api/v1/models/active', {}, fetchImpl)
    },

    async auditModels(): Promise<ModelsAuditResponse> {
      return requestJson<ModelsAuditResponse>(baseUrl, '/api/v1/models/audit', {}, fetchImpl)
    },

    async verifyModelIntegrity(modelDir: string): Promise<{ model_dir: string; audit: ModelAuditItem; verified: boolean }> {
      return requestJson<{ model_dir: string; audit: ModelAuditItem; verified: boolean }>(
        baseUrl,
        '/api/v1/models/verify',
        { method: 'POST', body: JSON.stringify({ model_dir: modelDir }) },
        fetchImpl,
      )
    },

    async quarantineModel(params: { model_dir: string; reason: string; details: string }): Promise<{ status: string; message: string; dossier: QuarantineDossierItem }> {
      return requestJson<{ status: string; message: string; dossier: QuarantineDossierItem }>(
        baseUrl,
        '/api/v1/models/quarantine',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async listQuarantinedModels(): Promise<{ quarantined_models: QuarantineDossierItem[]; count: number }> {
      return requestJson<{ quarantined_models: QuarantineDossierItem[]; count: number }>(
        baseUrl,
        '/api/v1/models/quarantine',
        {},
        fetchImpl,
      )
    },

    async reviewQuarantinedModel(params: { dossier_id: string; new_status: string; notes: string }): Promise<{ status: string; dossier: QuarantineDossierItem }> {
      return requestJson<{ status: string; dossier: QuarantineDossierItem }>(
        baseUrl,
        '/api/v1/models/quarantine/review',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async replaceQuarantinedModel(params: { target_model_dir: string; replacement_source_dir: string; approved_by?: string }): Promise<{ status: string; message: string; manifest: Record<string, unknown> }> {
      return requestJson<{ status: string; message: string; manifest: Record<string, unknown> }>(
        baseUrl,
        '/api/v1/models/replace',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async getPoisoningScenarios(): Promise<{ scenarios: PoisoningScenarioItem[]; threat_limitations: string[]; recovery_protocol: string[] }> {
      return requestJson<{ scenarios: PoisoningScenarioItem[]; threat_limitations: string[]; recovery_protocol: string[] }>(
        baseUrl,
        '/api/v1/models/poisoning/scenarios',
        {},
        fetchImpl,
      )
    },

    async evaluatePoisoningExperiment(params: { attack_class: string; attack_params?: Record<string, unknown>; holdout_count?: number }): Promise<{ status: string; report: PoisoningReportItem }> {
      return requestJson<{ status: string; report: PoisoningReportItem }>(
        baseUrl,
        '/api/v1/models/poisoning/evaluate',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async startTrainingJob(params: { holdout_count: number; seed: number }): Promise<{ job_id: string; message: string }> {
      return requestJson<{ job_id: string; message: string }>(
        baseUrl,
        '/api/v1/training/jobs',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async getLatestExperiment(): Promise<ExperimentManifest> {
      const res = await requestJson<Record<string, unknown>>(baseUrl, '/api/v1/experiments/latest', {}, fetchImpl)
      if (res && typeof res === 'object' && res.manifest && typeof res.manifest === 'object') {
        const manifestObj = res.manifest as Record<string, unknown>
        return {
          ...manifestObj,
          ablation_report: res.ablation_report ?? manifestObj.ablation_report,
          threshold_report: res.threshold_report ?? manifestObj.threshold_report,
          location_report: res.location_report ?? manifestObj.location_report,
        } as unknown as ExperimentManifest
      }
      return res as unknown as ExperimentManifest
    },

    async startExperimentJob(params: { holdout_count: number; seed: number }): Promise<{ job_id: string; message: string }> {
      return requestJson<{ job_id: string; message: string }>(
        baseUrl,
        '/api/v1/experiments/jobs',
        { method: 'POST', body: JSON.stringify(params) },
        fetchImpl,
      )
    },

    async predictForecast(payload: PredictionRequest): Promise<PredictionResponse> {
      return requestJson<PredictionResponse>(
        baseUrl,
        '/api/v1/forecast/predict',
        { method: 'POST', body: JSON.stringify(payload) },
        fetchImpl,
      )
    },

    async getForecastHistory(): Promise<{ audits: ForecastAuditItem[]; count: number }> {
      return requestJson<{ audits: ForecastAuditItem[]; count: number }>(
        baseUrl,
        '/api/v1/forecast/history',
        {},
        fetchImpl,
      )
    },

    async getJob(jobId: string): Promise<JobRecord> {
      return requestJson<JobRecord>(baseUrl, `/api/v1/jobs/${jobId}`, {}, fetchImpl)
    },

    async getJobs(): Promise<{ jobs: JobRecord[]; count: number }> {
      return requestJson<{ jobs: JobRecord[]; count: number }>(baseUrl, '/api/v1/jobs', {}, fetchImpl)
    },

    async getDefenseScenarios(): Promise<{
      scenarios: SimulationScenarioMetadata[]
      protocol_reference: string
      total_scenarios: number
    }> {
      return requestJson(baseUrl, '/api/v1/defense/scenarios', {}, fetchImpl)
    },

    async getDefenseBenchmarks(): Promise<SimulationReportItem> {
      return requestJson(baseUrl, '/api/v1/defense/benchmarks', {}, fetchImpl)
    },

    async simulateDefenseScenario(
      config: SimulationConfigItem,
    ): Promise<SimulationScenarioResultItem> {
      return requestJson(
        baseUrl,
        '/api/v1/defense/simulate',
        { method: 'POST', body: JSON.stringify(config) },
        fetchImpl,
      )
    },

    async inspectDefenseTelemetry(
      seriesId: string,
      records: Array<Record<string, unknown>>,
    ): Promise<DefensiveInspectionReportItem> {
      return requestJson(
        baseUrl,
        '/api/v1/defense/inspect',
        {
          method: 'POST',
          body: JSON.stringify({ series_id: seriesId, records }),
        },
        fetchImpl,
      )
    },

    async getRegionalForecast(params?: {
      oni_aso_degc?: number
      precip_oct_zscore?: number
      nino34_aso_anom_degc?: number
      issue_year?: number
    }): Promise<RegionalForecastDashboardResponse> {
      const q = new URLSearchParams()
      if (params?.oni_aso_degc !== undefined) q.set('oni_aso_degc', String(params.oni_aso_degc))
      if (params?.precip_oct_zscore !== undefined) q.set('precip_oct_zscore', String(params.precip_oct_zscore))
      if (params?.nino34_aso_anom_degc !== undefined) q.set('nino34_aso_anom_degc', String(params.nino34_aso_anom_degc))
      if (params?.issue_year !== undefined) q.set('issue_year', String(params.issue_year))
      const qs = q.toString() ? `?${q.toString()}` : ''
      return requestJson(baseUrl, `/api/v1/forecast/regional${qs}`, {}, fetchImpl)
    },

    async getHistoricalComparisons(): Promise<HistoricalComparisonsResponse> {
      return requestJson(baseUrl, '/api/v1/forecast/historical-comparisons', {}, fetchImpl)
    },

    async getPreparednessMatrix(): Promise<PreparednessMatrixResponse> {
      return requestJson(baseUrl, '/api/v1/preparedness/matrix', {}, fetchImpl)
    },

    async listPreparednessActions(params?: {
      tier?: string
      sector?: string
      status_filter?: string
    }): Promise<{ actions: PreparednessActionItem[]; count: number }> {
      const q = new URLSearchParams()
      if (params?.tier) q.set('tier', params.tier)
      if (params?.sector) q.set('sector', params.sector)
      if (params?.status_filter) q.set('status_filter', params.status_filter)
      const qs = q.toString() ? `?${q.toString()}` : ''
      return requestJson(baseUrl, `/api/v1/preparedness/actions${qs}`, {}, fetchImpl)
    },

    async triggerPreparednessAction(
      actionId: string,
      payload: { status: string; operator_name?: string; notes?: string },
    ): Promise<{ status: string; action: PreparednessActionItem; message: string }> {
      return requestJson(
        baseUrl,
        `/api/v1/preparedness/actions/${encodeURIComponent(actionId)}/trigger`,
        {
          method: 'POST',
          body: JSON.stringify({ action_id: actionId, ...payload }),
        },
        fetchImpl,
      )
    },

    async getSecurityIncidents(params?: {
      severity?: string
      subsystem?: string
      classification?: string
    }): Promise<SecurityIncidentsResponse> {
      const q = new URLSearchParams()
      if (params?.severity) q.set('severity', params.severity)
      if (params?.subsystem) q.set('subsystem', params.subsystem)
      if (params?.classification) q.set('classification', params.classification)
      const qs = q.toString() ? `?${q.toString()}` : ''
      return requestJson(baseUrl, `/api/v1/security/incidents${qs}`, {}, fetchImpl)
    },

    async getSecuritySummary(): Promise<SecuritySummaryResponse> {
      return requestJson(baseUrl, '/api/v1/security/summary', {}, fetchImpl)
    },

    async getClimateCoverage(): Promise<IngestionCoverageItem[]> {
      return requestJson(baseUrl, '/api/v1/ingestion/coverage', {}, fetchImpl)
    },

    async getIngestionHistory(limit = 50, sourceId?: string): Promise<IngestionHistoryItem[]> {
      const q = new URLSearchParams()
      q.set('limit', String(limit))
      if (sourceId) q.set('source_id', sourceId)
      return requestJson(baseUrl, `/api/v1/ingestion/history?${q.toString()}`, {}, fetchImpl)
    },

    async getIngestionSchedulerStatus(): Promise<IngestionSchedulerStatus> {
      return requestJson(baseUrl, '/api/v1/ingestion/scheduler', {}, fetchImpl)
    },

    async runIngestionNow(sourceId?: string): Promise<IngestionTriggerResponse> {
      const q = sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ''
      return requestJson(baseUrl, `/api/v1/ingestion/run-now${q}`, { method: 'POST' }, fetchImpl)
    },

    async refreshClimateCoverage(): Promise<{ status: string; coverage_sources: number; sources: unknown[] }> {
      return requestJson(baseUrl, '/api/v1/ingestion/refresh-coverage', { method: 'POST' }, fetchImpl)
    },
  }
}

