"""Automated tampering, authenticity, and provenance policy test suite.

Verifies:
1. Detection of post-ingestion byte tampering (content integrity).
2. Enforcement of the Unsigned Third-Party rule (hash != authenticity).
3. Authenticated digital signatures for controlled pipeline outputs.
4. Detection of corrupted or forged signatures.
5. Untracked file / missing metadata detection.
6. Staleness threshold monitoring.
7. Conflicting source version collision prevention.
8. Complete auditability of processing history and validation outcomes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ml.data.adapters.chirps_rainfall import ChirpsRainfallAdapter
from ml.data.provenance.auditor import ProvenanceAuditor
from ml.data.provenance.crypto import (
    compute_sha256,
    verify_provenance_signature,
)
from ml.data.provenance.policies import ProvenancePolicyEngine
from ml.data.provenance.tracker import ProvenanceTracker
from ml.data.validation.models import ProvenanceManifest

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"


@pytest.fixture
def chirps_raw_path() -> Path:
    p = FIXTURES_DIR / "chirps_sample.csv"
    assert p.is_file(), f"Fixture missing: {p}"
    return p


def test_unsigned_third_party_data_never_marked_authenticated(
    chirps_raw_path: Path,
) -> None:
    """CRITICAL RULE: Computing a cryptographic digest does NOT make third-party data authenticated."""
    raw_hash = compute_sha256(chirps_raw_path)

    manifest = ProvenanceTracker.create_manifest(
        dataset_id="chirps_rainfall_raw",
        source_identifier="chirps_rainfall",
        source_name="CHIRPS-2.0",
        source_version="v2.0",
        licence="Public Domain",
        citation="Funk et al. (2015)",
        raw_filepath=chirps_raw_path,
        record_count=96,
        date_range={"start": "1981-01", "end": "1988-12"},
        units={"precip_mm": "mm/month"},
        validation_status="PASSED",
        is_controlled_pipeline=False,  # Raw external download
    )

    # 1. Content digest must be computed for post-ingestion tamper detection
    assert manifest.content_digest == raw_hash
    assert manifest.raw_sha256 == raw_hash

    # 2. But authenticity status must strictly be UNSIGNED_THIRD_PARTY
    assert manifest.authenticity_status == "UNSIGNED_THIRD_PARTY"
    assert manifest.signature is None
    assert manifest.signing_key_id is None

    # 3. Auditor must confirm unsigned status with explicit rationale
    auditor = ProvenanceAuditor()
    audit_res = auditor.audit_artefact(manifest, target_path=chirps_raw_path, tier="raw")
    assert audit_res.content_integrity == "VERIFIED"
    assert audit_res.source_authenticity == "UNSIGNED_THIRD_PARTY"
    assert "Unsigned third-party" in audit_res.authenticity_detail


def test_controlled_pipeline_output_is_cryptographically_signed(
    tmp_path: Path,
    chirps_raw_path: Path,
) -> None:
    """Internal pipeline outputs must carry authenticated HMAC-SHA256 signatures."""
    adapter = ChirpsRainfallAdapter()
    clean_csv = tmp_path / "chirps_clean.csv"
    manifest_json = tmp_path / "chirps_manifest.json"

    _df, _report, manifest = adapter.ingest(
        raw_path=chirps_raw_path,
        cleaned_path=clean_csv,
        manifest_path=manifest_json,
    )

    assert manifest.authenticity_status == "AUTHENTIC_CONTROLLED_PIPELINE"
    assert manifest.signature is not None
    assert len(manifest.signature) == 64
    assert manifest.signing_key_id == "enso-pipeline-hmac-v1"

    # Signature must verify against manifest canonical payload
    assert verify_provenance_signature(manifest.model_dump(), manifest.signature)


def test_post_ingestion_tampering_is_detected_and_quarantined(
    tmp_path: Path,
    chirps_raw_path: Path,
) -> None:
    """Modifying even 1 byte of an ingested artefact triggers TAMPERED status and quarantine."""
    adapter = ChirpsRainfallAdapter()
    clean_csv = tmp_path / "chirps_rainfall_monthly.csv"
    manifest_json = tmp_path / "chirps_rainfall_provenance.json"

    _df, _report, manifest = adapter.ingest(
        raw_path=chirps_raw_path,
        cleaned_path=clean_csv,
        manifest_path=manifest_json,
    )

    auditor = ProvenanceAuditor(root_dir=tmp_path)

    # 1. Initially verified
    initial_audit = auditor.audit_artefact(manifest, target_path=clean_csv)
    assert initial_audit.content_integrity == "VERIFIED"
    assert len(initial_audit.violations) == 0

    # 2. Tamper with the cleaned file (e.g., inject malicious or corrupted rainfall record)
    with open(clean_csv, "a", encoding="utf-8") as f:
        f.write("1989,1,1989-01,999.9,-25.0,-25.0,28.0,28.0\n")

    # 3. Re-audit must detect tampering
    tampered_audit = auditor.audit_artefact(manifest, target_path=clean_csv)
    assert tampered_audit.content_integrity == "TAMPERED"
    assert not tampered_audit.digest_matches
    assert len(tampered_audit.violations) == 1

    violation = tampered_audit.violations[0]
    assert violation.violation_type == "MODIFIED_FILE"
    assert violation.severity == "CRITICAL"
    assert "QUARANTINE_ARTEFACT" in violation.enforced_action


def test_corrupted_signature_detection(
    tmp_path: Path,
    chirps_raw_path: Path,
) -> None:
    """Tampering with a signature or payload triggers SIGNATURE_INVALID and policy violation."""
    adapter = ChirpsRainfallAdapter()
    clean_csv = tmp_path / "chirps_clean.csv"

    _df, _report, manifest = adapter.ingest(
        raw_path=chirps_raw_path,
        cleaned_path=clean_csv,
    )

    # Alter the signature string to simulate forgery
    corrupted_data = manifest.model_dump()
    corrupted_data["signature"] = "deadbeef" * 8
    corrupted_manifest = ProvenanceManifest.model_validate(corrupted_data)

    auditor = ProvenanceAuditor(root_dir=tmp_path)
    res = auditor.audit_artefact(corrupted_manifest, target_path=clean_csv)

    assert res.source_authenticity == "SIGNATURE_INVALID"
    assert any(v.violation_type == "SIGNATURE_CORRUPTED" for v in res.violations)


def test_missing_metadata_policy_flags_untracked_files(tmp_path: Path) -> None:
    """Files existing without schema-compliant manifests are quarantined as untracked."""
    data_dir = tmp_path / "data"
    cleaned_dir = data_dir / "cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    p_dir = data_dir / "provenance"
    p_dir.mkdir(parents=True, exist_ok=True)

    # Create untracked file
    untracked_csv = cleaned_dir / "mystery_rainfall_monthly.csv"
    untracked_csv.write_text("year,month,precip_mm\n1981,1,100.0\n", encoding="utf-8")

    auditor = ProvenanceAuditor(root_dir=tmp_path)
    report = auditor.audit_repository(provenance_dir=p_dir)

    assert report.untracked_files_count == 1
    assert any(
        v.violation_type == "MISSING_METADATA" and "mystery_rainfall" in v.description
        for v in report.violations
    )


def test_stale_record_detection() -> None:
    """Stale operational feeds are flagged, while archival benchmark datasets are exempted."""
    # 1. Operational dataset older than 60 days threshold
    stale_ts = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    is_stale, violation = ProvenancePolicyEngine.handle_stale_record(
        artefact_id="live_chirps_rainfall",
        source_timestamp_utc=stale_ts,
        staleness_threshold_days=60,
        is_archival_benchmark=False,
    )
    assert is_stale
    assert violation is not None
    assert violation.violation_type == "STALE_RECORD"
    assert violation.severity == "WARNING"

    # 2. Historical calibration benchmark is permitted regardless of age
    is_stale_bench, violation_bench = ProvenancePolicyEngine.handle_stale_record(
        artefact_id="chirps_benchmark_1981_1988",
        source_timestamp_utc=stale_ts,
        staleness_threshold_days=60,
        is_archival_benchmark=True,
    )
    assert not is_stale_bench
    assert violation_bench is None


def test_conflicting_source_version_policy() -> None:
    """Silent mutation of historical versions is blocked by version collision policy."""
    existing_ver = "CHIRPS-v2.0"
    existing_hash = "329bd595f543156cf16c85c5e6613d3bb619102251acc746433a42d00482fe9c"

    # Same version, identical hash -> Idempotent
    action, viol = ProvenancePolicyEngine.handle_conflicting_source_versions(
        existing_version=existing_ver,
        existing_digest=existing_hash,
        incoming_version=existing_ver,
        incoming_digest=existing_hash,
        artefact_id="chirps_rainfall",
    )
    assert action == "IDEMPOTENT_PASS"
    assert viol is None

    # Same version, different hash -> Collision rejected!
    altered_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    action_conflict, viol_conflict = ProvenancePolicyEngine.handle_conflicting_source_versions(
        existing_version=existing_ver,
        existing_digest=existing_hash,
        incoming_version=existing_ver,
        incoming_digest=altered_hash,
        artefact_id="chirps_rainfall",
    )
    assert action_conflict == "VERSION_COLLISION_REJECTED"
    assert viol_conflict is not None
    assert viol_conflict.violation_type == "VERSION_CONFLICT"
    assert viol_conflict.severity == "HIGH"
    assert "REJECT_OVERWRITE" in viol_conflict.enforced_action


def test_processing_history_and_validation_outcome_integrity(
    tmp_path: Path,
    chirps_raw_path: Path,
) -> None:
    """Artefact manifest preserves complete processing lineage and validation outcomes."""
    adapter = ChirpsRainfallAdapter()
    clean_csv = tmp_path / "chirps_clean.csv"

    _df, report, manifest = adapter.ingest(
        raw_path=chirps_raw_path,
        cleaned_path=clean_csv,
    )

    # 1. Validation outcome auditable details
    outcome = manifest.validation_outcome
    assert outcome["is_valid"] is True
    assert outcome["status"] == "PASSED"
    assert outcome["checks_count"] == len(report.checks)
    assert "schema_columns" in outcome["passed_checks"]
    assert outcome["error_count"] == 0

    # 2. Processing history records raw acquisition and cleaning stages
    history = manifest.processing_history
    assert len(history) == 2

    step1 = history[0]
    assert step1.step_name == "raw_acquisition"
    assert step1.output_digest == manifest.raw_sha256
    assert "note" in step1.parameters

    step2 = history[1]
    assert step2.step_name == "validation_and_cleaning"
    assert step2.input_digests["raw_artefact"] == manifest.raw_sha256
    assert step2.output_digest == manifest.cleaned_sha256
