"""Comprehensive climate-data integrity and authenticity auditor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ml.data.provenance.crypto import (
    compute_sha256,
    verify_provenance_signature,
)
from ml.data.provenance.policies import (
    ProvenancePolicyEngine,
    ProvenanceViolation,
)
from ml.data.validation.models import ProvenanceManifest


class ArtefactAuditResult(BaseModel):
    """Detailed audit assessment for a single climate data artefact."""

    artefact_id: str
    file_name: str
    tier: str
    file_path: str
    exists: bool
    byte_size: int = 0

    # Three core pillars
    content_integrity: Literal["VERIFIED", "TAMPERED", "MISSING_FILE"]
    source_authenticity: Literal[
        "AUTHENTIC_CONTROLLED_PIPELINE",
        "UNSIGNED_THIRD_PARTY",
        "SIGNATURE_INVALID",
    ]
    scientific_validity: Literal["VALID", "INVALID", "UNCHECKED"]

    # Freshness
    freshness_status: Literal["FRESH", "STALE_RECORD", "ARCHIVAL_BENCHMARK"]

    # Cryptographic details
    expected_digest: str | None = None
    actual_digest: str | None = None
    digest_matches: bool = False
    is_signed: bool = False
    signing_key_id: str | None = None

    # Lineage and policy
    processing_steps_count: int = 0
    authenticity_detail: str = ""
    violations: list[ProvenanceViolation] = Field(default_factory=list)


class ProvenanceAuditReport(BaseModel):
    """Auditable system-wide report of climate-data integrity and authenticity."""

    audit_timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    overall_status: Literal["PASSED", "DEGRADED", "FAILED"]
    total_artefacts: int = 0
    verified_count: int = 0
    tampered_count: int = 0
    missing_files_count: int = 0
    signed_pipeline_count: int = 0
    unsigned_third_party_count: int = 0
    invalid_signature_count: int = 0
    valid_scientific_count: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    archival_benchmark_count: int = 0
    untracked_files_count: int = 0
    violations_count: int = 0
    violations: list[ProvenanceViolation] = Field(default_factory=list)
    artefacts: list[ArtefactAuditResult] = Field(default_factory=list)


class ProvenanceAuditor:
    """Audits data files on disk against provenance manifests and policy rules."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path(__file__).resolve().parents[3]

    def audit_artefact(
        self,
        manifest: ProvenanceManifest,
        target_path: Path | str | None = None,
        tier: str = "cleaned",
    ) -> ArtefactAuditResult:
        """Perform exhaustive 3-pillar audit on a single artefact."""
        resolved_path: Path
        if target_path:
            resolved_path = Path(target_path)
            if not resolved_path.is_absolute():
                resolved_path = self.root_dir / resolved_path
        else:
            # Derive canonical location based on dataset_id and tier
            candidates = [
                self.root_dir / "data" / tier / f"{manifest.dataset_id}_monthly.csv",
                self.root_dir / "data" / tier / f"{manifest.dataset_id}.csv",
                self.root_dir / "data" / "features" / f"{manifest.dataset_id}.csv",
                self.root_dir / "data" / "derived" / f"{manifest.dataset_id}.csv",
                self.root_dir / "data" / "cleaned" / f"{manifest.dataset_id}_monthly.csv",
            ]
            found = next((c for c in candidates if c.is_file()), candidates[0])
            resolved_path = found

        violations: list[ProvenanceViolation] = []
        file_exists = resolved_path.is_file()
        byte_size = resolved_path.stat().st_size if file_exists else 0
        actual_sha256 = compute_sha256(resolved_path) if file_exists else None

        expected_sha256 = (
            manifest.content_digest
            or manifest.cleaned_sha256
            or manifest.raw_sha256
            or manifest.derived_sha256
        )

        # 1. Content Integrity
        if not file_exists:
            content_integrity = "MISSING_FILE"
            digest_matches = False
            violations.append(
                ProvenanceViolation(
                    violation_type="MODIFIED_FILE",
                    severity="CRITICAL",
                    artefact_id=manifest.dataset_id,
                    description=f"Artefact file is missing on disk: {resolved_path}",
                    enforced_action="QUARANTINE_MISSING: Restore from trusted archive.",
                )
            )
        elif actual_sha256 == expected_sha256:
            content_integrity = "VERIFIED"
            digest_matches = True
        else:
            content_integrity = "TAMPERED"
            digest_matches = False
            violations.append(
                ProvenancePolicyEngine.handle_modified_file(
                    artefact_id=manifest.dataset_id,
                    file_path=resolved_path,
                    expected_hash=expected_sha256 or "",
                    actual_hash=actual_sha256 or "",
                )
            )

        # 2. Source Authenticity
        # Rule: Unsigned third-party data is NEVER authenticated simply because digest was computed.
        if manifest.authenticity_status == "AUTHENTIC_CONTROLLED_PIPELINE":
            # Verify signature over canonical payload
            manifest_dict = manifest.model_dump()
            is_valid_sig = verify_provenance_signature(manifest_dict, manifest.signature)
            if is_valid_sig:
                source_authenticity = "AUTHENTIC_CONTROLLED_PIPELINE"
                authenticity_detail = (
                    "Authenticated internal pipeline artefact; cryptographic HMAC-SHA256 "
                    "signature verified."
                )
            else:
                source_authenticity = "SIGNATURE_INVALID"
                authenticity_detail = (
                    "Controlled pipeline signature verification FAILED; payload modified or "
                    "signature forged."
                )
                violations.append(
                    ProvenancePolicyEngine.handle_corrupted_signature(
                        manifest.dataset_id, manifest.signature
                    )
                )
        else:
            source_authenticity = "UNSIGNED_THIRD_PARTY"
            authenticity_detail = (
                "Unsigned third-party scientific source. Cryptographic hash tracks content "
                "integrity, but producer did not provide cryptographic digital signature."
            )

        # 3. Scientific Validity
        if manifest.validation_status == "PASSED":
            scientific_validity = "VALID"
        else:
            scientific_validity = "INVALID"
            violations.append(
                ProvenanceViolation(
                    violation_type="MISSING_METADATA",
                    severity="HIGH",
                    artefact_id=manifest.dataset_id,
                    description="Domain scientific validation failed or incomplete.",
                    enforced_action=(
                        "REVISE_VALIDATION: Rectify data physical constraint violations."
                    ),
                )
            )

        # 4. Freshness
        is_stale, stale_violation = ProvenancePolicyEngine.handle_stale_record(
            artefact_id=manifest.dataset_id,
            source_timestamp_utc=manifest.source_timestamp_utc,
            staleness_threshold_days=manifest.staleness_threshold_days,
            is_archival_benchmark=manifest.is_archival_benchmark,
        )
        if manifest.is_archival_benchmark:
            freshness_status = "ARCHIVAL_BENCHMARK"
        elif is_stale:
            freshness_status = "STALE_RECORD"
            if stale_violation:
                violations.append(stale_violation)
        else:
            freshness_status = "FRESH"

        return ArtefactAuditResult(
            artefact_id=manifest.dataset_id,
            file_name=resolved_path.name,
            tier=tier,
            file_path=str(resolved_path),
            exists=file_exists,
            byte_size=byte_size,
            content_integrity=content_integrity,
            source_authenticity=source_authenticity,
            scientific_validity=scientific_validity,
            freshness_status=freshness_status,
            expected_digest=expected_sha256,
            actual_digest=actual_sha256,
            digest_matches=digest_matches,
            is_signed=bool(manifest.signature),
            signing_key_id=manifest.signing_key_id,
            processing_steps_count=len(manifest.processing_history),
            authenticity_detail=authenticity_detail,
            violations=violations,
        )

    def audit_repository(
        self,
        provenance_dir: Path | str | None = None,
    ) -> ProvenanceAuditReport:
        """Scan all manifests and active data directories to generate system audit report."""
        p_dir = Path(provenance_dir) if provenance_dir else self.root_dir / "data" / "provenance"
        if not p_dir.is_absolute():
            p_dir = self.root_dir / p_dir

        artefact_results: list[ArtefactAuditResult] = []
        all_violations: list[ProvenanceViolation] = []
        manifest_dataset_ids: set[str] = set()

        if p_dir.is_dir():
            for m_path in sorted(p_dir.glob("*.json")):
                try:
                    content = m_path.read_text(encoding="utf-8")
                    manifest = ProvenanceManifest.model_validate_json(content)
                    manifest_dataset_ids.add(manifest.dataset_id)

                    tier = "cleaned"
                    if "feature" in manifest.dataset_id:
                        tier = "features"
                    elif "derived" in manifest.dataset_id or "seasonal" in manifest.dataset_id:
                        tier = "derived"

                    res = self.audit_artefact(manifest, tier=tier)
                    artefact_results.append(res)
                    all_violations.extend(res.violations)
                except Exception as exc:
                    v = ProvenanceViolation(
                        violation_type="MISSING_METADATA",
                        severity="CRITICAL",
                        artefact_id=m_path.stem,
                        description=f"Corrupt manifest JSON file '{m_path.name}': {exc}",
                        enforced_action="REBUILD_MANIFEST",
                    )
                    all_violations.append(v)

        # Check for untracked operational files in data directories
        data_subdirs = [
            ("cleaned", self.root_dir / "data" / "cleaned"),
            ("derived", self.root_dir / "data" / "derived"),
            ("features", self.root_dir / "data" / "features"),
        ]
        untracked_count = 0
        for _tier_name, dir_path in data_subdirs:
            if not dir_path.is_dir():
                continue
            for f in dir_path.glob("*.csv"):
                # Determine matching manifest
                matched = any(
                    res.file_name == f.name or res.artefact_id in f.stem for res in artefact_results
                )
                if not matched and not f.name.startswith("."):
                    untracked_count += 1
                    all_violations.append(
                        ProvenancePolicyEngine.handle_missing_metadata(f, ["MANIFEST_RECORD"])
                    )

        # Aggregate counts
        verified_count = sum(1 for r in artefact_results if r.content_integrity == "VERIFIED")
        tampered_count = sum(1 for r in artefact_results if r.content_integrity == "TAMPERED")
        missing_count = sum(1 for r in artefact_results if r.content_integrity == "MISSING_FILE")
        signed_pipeline_count = sum(
            1 for r in artefact_results if r.source_authenticity == "AUTHENTIC_CONTROLLED_PIPELINE"
        )
        unsigned_third_party_count = sum(
            1 for r in artefact_results if r.source_authenticity == "UNSIGNED_THIRD_PARTY"
        )
        invalid_sig_count = sum(
            1 for r in artefact_results if r.source_authenticity == "SIGNATURE_INVALID"
        )
        valid_sci_count = sum(1 for r in artefact_results if r.scientific_validity == "VALID")
        fresh_count = sum(1 for r in artefact_results if r.freshness_status == "FRESH")
        stale_count = sum(1 for r in artefact_results if r.freshness_status == "STALE_RECORD")
        archival_count = sum(
            1 for r in artefact_results if r.freshness_status == "ARCHIVAL_BENCHMARK"
        )

        critical_violations = [v for v in all_violations if v.severity == "CRITICAL"]
        high_violations = [v for v in all_violations if v.severity == "HIGH"]

        if critical_violations or tampered_count > 0 or invalid_sig_count > 0:
            overall_status = "FAILED"
        elif high_violations or missing_count > 0 or untracked_count > 0:
            overall_status = "DEGRADED"
        else:
            overall_status = "PASSED"

        return ProvenanceAuditReport(
            overall_status=overall_status,
            total_artefacts=len(artefact_results),
            verified_count=verified_count,
            tampered_count=tampered_count,
            missing_files_count=missing_count,
            signed_pipeline_count=signed_pipeline_count,
            unsigned_third_party_count=unsigned_third_party_count,
            invalid_signature_count=invalid_sig_count,
            valid_scientific_count=valid_sci_count,
            fresh_count=fresh_count,
            stale_count=stale_count,
            archival_benchmark_count=archival_count,
            untracked_files_count=untracked_count,
            violations_count=len(all_violations),
            violations=all_violations,
            artefacts=artefact_results,
        )
