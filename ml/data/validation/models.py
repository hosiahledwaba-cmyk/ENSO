"""Data validation and provenance data structures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ValidationCheck(BaseModel):
    """Result of an individual integrity check."""

    name: str
    passed: bool
    detail: str = ""
    error_count: int = 0
    sample_errors: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Comprehensive validation report for an ingested dataset."""

    dataset_id: str
    source_version: str
    total_records: int
    is_valid: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def add_check(
        self,
        name: str,
        passed: bool,
        detail: str = "",
        error_count: int = 0,
        sample_errors: list[str] | None = None,
    ) -> None:
        check = ValidationCheck(
            name=name,
            passed=passed,
            detail=detail,
            error_count=error_count,
            sample_errors=sample_errors or [],
        )
        self.checks.append(check)
        if not passed:
            self.is_valid = False
            msg = f"Check '{name}' failed: {detail}"
            if error_count:
                msg += f" ({error_count} records affected)"
            self.errors.append(msg)

    def to_outcome_dict(self) -> dict[str, Any]:
        """Convert validation report into auditable outcome summary dictionary."""
        return {
            "is_valid": self.is_valid,
            "status": "PASSED" if self.is_valid else "FAILED",
            "total_records": self.total_records,
            "checks_count": len(self.checks),
            "passed_checks": [c.name for c in self.checks if c.passed],
            "failed_checks": [c.name for c in self.checks if not c.passed],
            "error_count": len(self.errors),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "timestamp_utc": datetime.now(UTC).isoformat(),
        }


class SpatialBounds(BaseModel):
    """Geographic bounding box coordinates in decimal degrees."""

    lat_min: float = Field(ge=-90.0, le=90.0)
    lat_max: float = Field(ge=-90.0, le=90.0)
    lon_min: float = Field(ge=-180.0, le=180.0)
    lon_max: float = Field(ge=-180.0, le=180.0)


class ProcessingStep(BaseModel):
    """Auditable transformation record in the climate artefact lifecycle."""

    step_name: str
    timestamp_utc: str
    operator: str
    input_digests: dict[str, str] = Field(default_factory=dict)
    output_digest: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProvenanceManifest(BaseModel):
    """Cryptographic provenance, authenticity, and attribution manifest."""

    manifest_version: str = "2.0"
    dataset_id: str
    source_identifier: str = ""
    source_name: str
    source_version: str
    dataset_version: str = ""
    source_url: str | None = None
    source_timestamp_utc: str | None = None
    licence: str
    citation: str
    ingestion_timestamp_utc: str
    content_digest: str = ""
    raw_sha256: str | None = None
    cleaned_sha256: str | None = None
    derived_sha256: str | None = None
    record_count: int
    date_range: dict[str, str]
    units: dict[str, str]
    spatial_bounds: SpatialBounds | None = None
    validation_status: Literal["PASSED", "FAILED"]
    validation_outcome: dict[str, Any] = Field(default_factory=dict)
    processing_history: list[ProcessingStep] = Field(default_factory=list)
    authenticity_status: Literal[
        "AUTHENTIC_CONTROLLED_PIPELINE",
        "UNSIGNED_THIRD_PARTY",
        "SIGNATURE_INVALID",
    ] = "UNSIGNED_THIRD_PARTY"
    signature: str | None = None
    signing_key_id: str | None = None
    staleness_threshold_days: int = 60
    is_archival_benchmark: bool = True
    pipeline_version: str = "0.1.0"
    additional_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("source_identifier"):
                data["source_identifier"] = data.get("dataset_id", "")
            if not data.get("dataset_version"):
                data["dataset_version"] = data.get("source_version", "")
            if not data.get("content_digest"):
                data["content_digest"] = (
                    data.get("cleaned_sha256")
                    or data.get("raw_sha256")
                    or data.get("derived_sha256")
                    or ""
                )
        return data
