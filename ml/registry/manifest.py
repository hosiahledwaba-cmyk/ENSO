"""Reproducible model manifest schemas, cryptographic integrity, and metadata persistence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ml.evaluation.models import ProbabilisticMetrics

ModelApprovalStatus = Literal[
    "APPROVED",
    "EXPERIMENTAL",
    "DEPRECATED",
    "QUARANTINED",
    "REVOKED",
]


class FeatureSchemaEntry(BaseModel):
    """Specification of an expected input feature."""

    name: str
    dtype: str = "float"
    unit: str = "dimensionless"
    required: bool = True
    mean_training: float | None = None
    scale_training: float | None = None


class ModelManifest(BaseModel):
    """Immutable audit record and serialization manifest of a trained climate model."""

    manifest_version: str = "2.0"
    model_id: str
    model_version: str = "1.0.0"
    model_type: str = "regularized_logistic_regression"
    approval_status: ModelApprovalStatus = "APPROVED"
    created_at_utc: str
    training_config: dict[str, Any]

    # Dataset & Provenance
    dataset_id: str
    dataset_version: str
    dataset_sha256: str = ""
    training_data_fingerprint: str = ""
    training_seasons: list[int]
    holdout_seasons: list[int]
    target_variable: str

    # Artefact Digest & Integrity
    artefact_digest: str = ""
    artefact_relpath: str = "logistic_regression.json"

    # Feature Schema & Preprocessing
    feature_schema: list[FeatureSchemaEntry]
    scaler_means: dict[str, float] = Field(default_factory=dict)
    scaler_scales: dict[str, float] = Field(default_factory=dict)

    # Model Parameters
    intercept: float
    coefficients: dict[str, float]
    fallback_base_rate: float | None = None

    # Evaluation Results
    rolling_origin_metrics: ProbabilisticMetrics | None = None
    holdout_metrics: ProbabilisticMetrics | None = None
    baseline_holdout_metrics: ProbabilisticMetrics | None = None
    beats_baseline_on_holdout: bool = False
    holdout_bss: float | None = None
    evaluation_report: dict[str, Any] = Field(default_factory=dict)

    scientific_notice: str = Field(
        default="Evaluated using chronological rolling-origin and an untouched holdout period."
    )

    @model_validator(mode="before")
    @classmethod
    def _backfill_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Sync dataset_sha256 and training_data_fingerprint
            d_sha = values.get("dataset_sha256", "")
            t_fp = values.get("training_data_fingerprint", "")
            if not t_fp and d_sha:
                values["training_data_fingerprint"] = d_sha
            elif not d_sha and t_fp:
                values["dataset_sha256"] = t_fp

            # Populate evaluation_report if missing
            if "evaluation_report" not in values or not values["evaluation_report"]:
                eval_rep: dict[str, Any] = {}
                if "holdout_metrics" in values and isinstance(values["holdout_metrics"], dict):
                    eval_rep["holdout"] = values["holdout_metrics"]
                if "rolling_origin_metrics" in values and isinstance(
                    values["rolling_origin_metrics"], dict
                ):
                    eval_rep["rolling_origin"] = values["rolling_origin_metrics"]
                if "holdout_bss" in values:
                    eval_rep["holdout_bss"] = values["holdout_bss"]
                values["evaluation_report"] = eval_rep
        return values

    def compute_artefact_digest(self, model_dir: Path | str) -> str:
        """Compute streaming SHA-256 digest of the serialized model weights file."""
        artefact_path = Path(model_dir) / self.artefact_relpath
        if not artefact_path.is_file():
            raise FileNotFoundError(f"Model artefact file not found at: {artefact_path}")

        hasher = hashlib.sha256()
        with open(artefact_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def verify_artefact_integrity(self, model_dir: Path | str) -> tuple[bool, str, str]:
        """Verify model weights file integrity against manifest digest.

        Returns
        -------
        tuple[bool, str, str]
            (is_valid, expected_digest, observed_digest)
        """
        observed_digest = self.compute_artefact_digest(model_dir)
        if not self.artefact_digest:
            # If manifest has no digest recorded, return False
            return False, "", observed_digest
        is_valid = observed_digest.lower() == self.artefact_digest.lower()
        return is_valid, self.artefact_digest, observed_digest

    def validate_feature_compatibility(
        self, candidate_features: list[str]
    ) -> tuple[bool, list[str]]:
        """Verify candidate feature list against required feature schema entries.

        Returns
        -------
        tuple[bool, list[str]]
            (is_compatible, missing_features)
        """
        required = [f.name for f in self.feature_schema if f.required]
        missing = [f for f in required if f not in candidate_features]
        return len(missing) == 0, missing

    def is_approved(self, allowed_versions: set[str] | None = None) -> bool:
        """Check if model version is approved and in active non-quarantined status."""
        if self.approval_status != "APPROVED":
            return False
        return not (allowed_versions is not None and self.model_version not in allowed_versions)

    def to_json(self, filepath: Path | str) -> None:
        """Persist manifest to JSON file."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    @classmethod
    def from_json(cls, filepath: Path | str) -> ModelManifest:
        """Load manifest from JSON file."""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
