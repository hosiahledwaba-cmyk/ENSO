"""Data structures and types for defensive anomaly detection and simulation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnomalyType = Literal[
    "IMPOSSIBLE_VALUE",
    "SUDDEN_CHANGE",
    "MISSING_DATA",
    "TIMESTAMP_IRREGULARITY",
    "REPLAY_OBSERVATION",
    "CROSS_SOURCE_INCONSISTENCY",
    "MULTIVARIATE_OUTLIER",
]

AnomalySeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

AnomalyClassification = Literal[
    "MEASUREMENT_NOISE",
    "DATA_QUALITY_ANOMALY",
    "SUSPICIOUS_ANOMALY",
    "POTENTIAL_ADVERSARIAL_PERTURBATION",
    "CLEAN_BENCHMARK",
]

PerturbationScenario = Literal[
    "DATA_CORRUPTION",
    "REPLAY_ATTACK",
    "MEASUREMENT_NOISE",
    "MISSING_DATA",
    "ADVERSARIAL_FDI",
]


class AnomalyDetection(BaseModel):
    """Individual anomaly detection record with calibrated suspicion score.

    INVARIANT: Ordinary statistical anomalies are NEVER marked as confirmed malicious activity.
    They are classified into evidence-based categories (measurement noise, data quality,
    suspicious telemetry, potential adversarial perturbation) with an explicit suspicion score.
    """

    timestamp: str | None = None
    feature_name: str
    observed_value: Any
    expected_range: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    classification: AnomalyClassification
    suspicion_score: float = Field(ge=0.0, le=1.0)
    detail: str
    is_confirmed_malicious: bool = False


class DefenseCheckResult(BaseModel):
    """Summary of a specific transparent statistical check."""

    check_name: str
    passed: bool
    anomaly_count: int
    anomalies: list[AnomalyDetection] = Field(default_factory=list)


class DefensiveInspectionReport(BaseModel):
    """Comprehensive inspection report across statistical checks and baseline detector."""

    series_id: str
    total_records: int
    passed: bool
    anomaly_count: int
    anomalies: list[AnomalyDetection] = Field(default_factory=list)
    check_summaries: list[DefenseCheckResult] = Field(default_factory=list)
    baseline_detector_score: float | None = None
    overall_classification: AnomalyClassification
    summary: str


class SimulationConfig(BaseModel):
    """Configuration for controlled, isolated perturbation experiments."""

    scenario: PerturbationScenario
    seed: int = 42
    target_feature: str = "oni_aso_degc"
    perturbation_magnitude: float = 1.0
    injection_ratio: float = 0.3
    description: str = ""


class SimulationScenarioResult(BaseModel):
    """Empirical outcomes of a controlled perturbation and defensive evaluation run."""

    scenario: str
    seed: int
    target_feature: str
    total_samples: int
    injected_samples: int
    detected_samples: int
    clean_samples: int
    false_alarms: int
    attack_detection_rate: float
    false_positive_rate: float
    detection_delay_timesteps: float
    clean_brier_score: float
    attack_brier_score: float
    defended_brier_score: float
    brier_score_degradation: float
    defensive_recovery_efficiency: float
    mean_probability_shift: float
    risk_category_flips: int
    ground_truth_labels: list[int] = Field(default_factory=list)
    detector_flags: list[bool] = Field(default_factory=list)
    detector_classifications: list[str] = Field(default_factory=list)
    summary: str = ""


class SimulationReport(BaseModel):
    """Aggregated benchmark report across all standard security test scenarios."""

    timestamp_utc: str
    random_seed: int
    total_scenarios_evaluated: int
    mean_attack_detection_rate: float
    mean_false_positive_rate: float
    mean_recovery_efficiency: float
    scenarios: list[SimulationScenarioResult] = Field(default_factory=list)
