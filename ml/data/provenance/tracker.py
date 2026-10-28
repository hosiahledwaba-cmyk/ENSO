"""Cryptographic provenance tracking and ledger integration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.data.provenance.crypto import (
    compute_bytes_sha256,
    compute_sha256,
    sign_provenance_manifest,
)
from ml.data.validation.models import (
    ProcessingStep,
    ProvenanceManifest,
    SpatialBounds,
)


class ProvenanceTracker:
    """Records, signs, and verifies dataset provenance and cryptographic hashes."""

    @staticmethod
    def create_manifest(
        dataset_id: str,
        source_name: str,
        source_version: str,
        licence: str,
        citation: str,
        raw_filepath: Path | str,
        record_count: int,
        date_range: dict[str, str],
        units: dict[str, str],
        validation_status: str,
        source_url: str | None = None,
        cleaned_filepath: Path | str | None = None,
        derived_filepath: Path | str | None = None,
        spatial_bounds: SpatialBounds | None = None,
        additional_metadata: dict[str, Any] | None = None,
        source_identifier: str | None = None,
        source_timestamp_utc: str | None = None,
        dataset_version: str | None = None,
        validation_outcome: dict[str, Any] | None = None,
        processing_history: list[ProcessingStep] | None = None,
        is_controlled_pipeline: bool = True,
        staleness_threshold_days: int = 60,
        is_archival_benchmark: bool = True,
        secret_key: str | None = None,
    ) -> ProvenanceManifest:
        """Construct, validate, and cryptographically sign a provenance manifest."""
        raw_p = Path(raw_filepath)
        raw_hash = compute_sha256(raw_p) if raw_p.is_file() else "MISSING"

        cleaned_p = Path(cleaned_filepath) if cleaned_filepath else None
        cleaned_hash = compute_sha256(cleaned_p) if cleaned_p and cleaned_p.is_file() else None

        derived_p = Path(derived_filepath) if derived_filepath else None
        derived_hash = compute_sha256(derived_p) if derived_p and derived_p.is_file() else None

        content_digest = cleaned_hash or derived_hash or raw_hash
        src_id = source_identifier or dataset_id
        ds_ver = dataset_version or source_version
        ingestion_ts = datetime.now(UTC).isoformat()

        # Build initial manifest dictionary
        history = list(processing_history or [])

        # Default validation outcome if not provided
        val_outcome = validation_outcome or {
            "is_valid": validation_status == "PASSED",
            "status": "PASSED" if validation_status == "PASSED" else "FAILED",
            "total_records": record_count,
            "error_count": 0 if validation_status == "PASSED" else 1,
            "errors": [] if validation_status == "PASSED" else ["Validation check failed."],
            "timestamp_utc": ingestion_ts,
        }

        manifest_data: dict[str, Any] = {
            "manifest_version": "2.0",
            "dataset_id": dataset_id,
            "source_identifier": src_id,
            "source_name": source_name,
            "source_version": source_version,
            "dataset_version": ds_ver,
            "source_url": source_url,
            "source_timestamp_utc": source_timestamp_utc,
            "licence": licence,
            "citation": citation,
            "ingestion_timestamp_utc": ingestion_ts,
            "content_digest": content_digest,
            "raw_sha256": raw_hash,
            "cleaned_sha256": cleaned_hash,
            "derived_sha256": derived_hash,
            "record_count": record_count,
            "date_range": date_range,
            "units": units,
            "spatial_bounds": spatial_bounds.model_dump() if spatial_bounds else None,
            "validation_status": "PASSED" if validation_status == "PASSED" else "FAILED",
            "validation_outcome": val_outcome,
            "processing_history": [step.model_dump() for step in history],
            "authenticity_status": "UNSIGNED_THIRD_PARTY",
            "signature": None,
            "signing_key_id": None,
            "staleness_threshold_days": staleness_threshold_days,
            "is_archival_benchmark": is_archival_benchmark,
            "pipeline_version": "0.1.0",
            "additional_metadata": additional_metadata or {},
        }

        # Apply cryptographic signature for internal controlled pipelines
        if is_controlled_pipeline:
            sig, key_id = sign_provenance_manifest(manifest_data, secret_key=secret_key)
            manifest_data["signature"] = sig
            manifest_data["signing_key_id"] = key_id
            manifest_data["authenticity_status"] = "AUTHENTIC_CONTROLLED_PIPELINE"
        else:
            # Rule: Unsigned third-party external data is NEVER signed
            manifest_data["signature"] = None
            manifest_data["signing_key_id"] = None
            manifest_data["authenticity_status"] = "UNSIGNED_THIRD_PARTY"

        return ProvenanceManifest.model_validate(manifest_data)

    @staticmethod
    def save_manifest(manifest: ProvenanceManifest, destination_path: Path | str) -> Path:
        """Write manifest as formatted JSON."""
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
        return dest

    @staticmethod
    def load_manifest(manifest_path: Path | str) -> ProvenanceManifest:
        """Load and validate manifest from JSON."""
        content = Path(manifest_path).read_text(encoding="utf-8")
        return ProvenanceManifest.model_validate_json(content)


__all__ = [
    "ProvenanceTracker",
    "compute_bytes_sha256",
    "compute_sha256",
]
