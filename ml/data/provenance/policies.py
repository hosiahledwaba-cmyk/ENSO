"""Handling policies for climate data tampering, missing metadata, staleness, and version conflicts.

Formalizes operational responses to ensure cyber-resilience and scientific integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

SeverityLevel = Literal["CRITICAL", "HIGH", "WARNING", "INFO"]
AnomalyType = Literal[
    "MODIFIED_FILE",
    "MISSING_METADATA",
    "STALE_RECORD",
    "VERSION_CONFLICT",
    "SIGNATURE_CORRUPTED",
]


class ProvenanceViolation(BaseModel):
    """Structured record of a provenance or integrity policy violation."""

    violation_type: AnomalyType
    severity: SeverityLevel
    artefact_id: str
    description: str
    detected_value: Any = None
    expected_value: Any = None
    enforced_action: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProvenancePolicyEngine:
    """Enforces scientific and cryptographic policies for ingested climate artefacts."""

    @staticmethod
    def handle_modified_file(
        artefact_id: str,
        file_path: Path | str,
        expected_hash: str,
        actual_hash: str,
    ) -> ProvenanceViolation:
        """Handle detected post-ingestion tampering or unexpected file modification.

        Policy Response:
            1. Flag artefact status as TAMPERED (Severity: CRITICAL).
            2. Quarantine artefact: immediately block downstream consumption by feature
               engineering, model training, evaluation, and live forecast inference.
            3. Require re-ingestion from verified source or restoration from backup.
        """
        path_str = str(file_path)
        return ProvenanceViolation(
            violation_type="MODIFIED_FILE",
            severity="CRITICAL",
            artefact_id=artefact_id,
            description=(
                f"Cryptographic hash mismatch for '{path_str}'. File content has been modified "
                f"or corrupted after ingestion."
            ),
            detected_value=actual_hash,
            expected_value=expected_hash,
            enforced_action=(
                "QUARANTINE_ARTEFACT: Downstream training and forecast inference "
                "pipelines blocked. File must be restored from trusted source or re-ingested."
            ),
        )

    @staticmethod
    def handle_corrupted_signature(
        artefact_id: str,
        signature: str | None,
    ) -> ProvenanceViolation:
        """Handle invalid or corrupted cryptographic signature on controlled pipeline artefact."""
        return ProvenanceViolation(
            violation_type="SIGNATURE_CORRUPTED",
            severity="CRITICAL",
            artefact_id=artefact_id,
            description=(
                f"Cryptographic signature verification failed for controlled artefact "
                f"'{artefact_id}'. Signature payload has been altered or forged."
            ),
            detected_value=signature or "MISSING_SIGNATURE",
            expected_value="VALID_HMAC_SHA256",
            enforced_action=(
                "REJECT_AUTHENTICITY: Artefact authenticity revoked. Processing history untrusted."
            ),
        )

    @staticmethod
    def handle_missing_metadata(
        file_path: Path | str,
        missing_fields: list[str],
    ) -> ProvenanceViolation:
        """Handle untracked artefact files or incomplete provenance manifests.

        Policy Response:
            1. Flag artefact as METADATA_MISSING (Severity: HIGH).
            2. Reject participation in operational workflows until explicit manifest
               generation and schema validation succeed.
        """
        path = Path(file_path)
        return ProvenanceViolation(
            violation_type="MISSING_METADATA",
            severity="HIGH",
            artefact_id=path.stem,
            description=(
                f"Artefact '{path.name}' is missing mandatory provenance fields: "
                f"{', '.join(missing_fields)}"
            ),
            detected_value=missing_fields,
            expected_value="COMPLETE_PROVENANCE_SCHEMA_V2",
            enforced_action=(
                "BLOCK_UNTIL_MANIFESTED: Artefact cannot be utilized for model training or "
                "inference until registered through ingestion pipeline."
            ),
        )

    @staticmethod
    def handle_stale_record(
        artefact_id: str,
        source_timestamp_utc: str | None,
        staleness_threshold_days: int = 60,
        is_archival_benchmark: bool = True,
        current_time: datetime | None = None,
    ) -> tuple[bool, ProvenanceViolation | None]:
        """Evaluate observation freshness against source staleness threshold.

        Policy Response:
            - If archival benchmark: Permitted for retrospective scientific analysis and
              historical model evaluation; marked as ARCHIVAL_BENCHMARK.
            - If operational monitoring feed and age > threshold: Emit STALE_RECORD warning
              (Severity: WARNING). Disallow live operational forecast issue until fresh
              observations are ingested.
        """
        if is_archival_benchmark:
            return False, None

        if not source_timestamp_utc:
            violation = ProvenanceViolation(
                violation_type="STALE_RECORD",
                severity="WARNING",
                artefact_id=artefact_id,
                description=(
                    f"Artefact '{artefact_id}' lacks source timestamp; "
                    "freshness cannot be verified."
                ),
                enforced_action="WARN_UNDETERMINED_FRESHNESS: Flag for operational inspection.",
            )
            return True, violation

        now = current_time or datetime.now(UTC)
        try:
            ts = datetime.fromisoformat(source_timestamp_utc.replace("Z", "+00:00"))
            age_days = (now - ts).total_seconds() / 86400.0
        except Exception:
            violation = ProvenanceViolation(
                violation_type="STALE_RECORD",
                severity="WARNING",
                artefact_id=artefact_id,
                description=f"Invalid timestamp format in manifest: '{source_timestamp_utc}'",
                enforced_action="WARN_INVALID_TIMESTAMP",
            )
            return True, violation

        if age_days > staleness_threshold_days:
            violation = ProvenanceViolation(
                violation_type="STALE_RECORD",
                severity="WARNING",
                artefact_id=artefact_id,
                description=(
                    f"Dataset '{artefact_id}' is stale: age is {age_days:.1f} days, exceeding "
                    f"staleness threshold of {staleness_threshold_days} days."
                ),
                detected_value=f"{age_days:.1f} days",
                expected_value=f"<= {staleness_threshold_days} days",
                enforced_action=(
                    "WARN_OPERATIONAL_FRESHNESS: Retrospective evaluation allowed; live forecast "
                    "issue requires refreshed observation ingest."
                ),
            )
            return True, violation

        return False, None

    @staticmethod
    def handle_conflicting_source_versions(
        existing_version: str,
        existing_digest: str,
        incoming_version: str,
        incoming_digest: str,
        artefact_id: str,
    ) -> tuple[str, ProvenanceViolation | None]:
        """Evaluate version and content collisions during dataset re-ingestion.

        Policy Response:
            - Identical version and digest -> IDEMPOTENT_PASS.
            - Same version, different digest -> VERSION_COLLISION_REJECTED (Severity: HIGH).
              Prevents silent mutation of historical training baselines.
            - Newer version -> SUPERSEDED_NEW_VERSION. Permitted with lineage tracking.
        """
        if existing_version == incoming_version:
            if existing_digest == incoming_digest:
                return "IDEMPOTENT_PASS", None

            violation = ProvenanceViolation(
                violation_type="VERSION_CONFLICT",
                severity="HIGH",
                artefact_id=artefact_id,
                description=(
                    f"Silent mutation conflict detected for '{artefact_id}' version "
                    f"'{existing_version}'. Incoming content digest '{incoming_digest[:12]}...' "
                    f"differs from recorded digest '{existing_digest[:12]}...' "
                    "under identical version tag."
                ),
                detected_value=incoming_digest,
                expected_value=existing_digest,
                enforced_action=(
                    "REJECT_OVERWRITE: In-place overwrite forbidden. Enforce explicit version bump "
                    "or historical archive rotation."
                ),
            )
            return "VERSION_COLLISION_REJECTED", violation

        return "SUPERSEDED_NEW_VERSION", None
