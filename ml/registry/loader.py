"""Secure cryptographic model loading with integrity verification and schema enforcement."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ml.registry.manifest import ModelManifest
from ml.registry.quarantine import (
    IncompatibleFeatureSchemaError,
    MissingArtefactError,
    MissingManifestError,
    ModelQuarantineManager,
    ModelTamperingError,
    UnapprovedModelVersionError,
)
from ml.training.baseline import ClimatologyBaseline
from ml.training.models import LogisticRegressionPredictor

logger = logging.getLogger("enso_ml.registry.loader")


class SecureModelLoader:
    """Loads trained model artefacts with strict cryptographic integrity and schema guarantees."""

    def __init__(self, quarantine_manager: ModelQuarantineManager | None = None) -> None:
        self.quarantine_manager = quarantine_manager or ModelQuarantineManager()

    def audit_model(
        self,
        model_dir: Path | str,
        allowed_versions: set[str] | None = None,
    ) -> dict[str, Any]:
        """Perform non-destructive pre-load audit of a model directory.

        Returns structured dictionary describing manifest status, digest match, and approvals.
        """
        path = Path(model_dir)
        manifest_path = path / "model_manifest.json"
        is_quarantined = (path / ".quarantined").is_file()

        if not manifest_path.is_file():
            return {
                "model_id": path.name,
                "model_dir": str(path),
                "manifest_found": False,
                "audit_passed": False,
                "quarantined": is_quarantined,
                "issues": ["model_manifest.json not found"],
            }

        try:
            manifest = ModelManifest.from_json(manifest_path)
        except Exception as exc:
            return {
                "model_id": path.name,
                "model_dir": str(path),
                "manifest_found": True,
                "audit_passed": False,
                "quarantined": is_quarantined,
                "issues": [f"Malformed model_manifest.json: {exc}"],
            }

        issues: list[str] = []
        if is_quarantined or manifest.approval_status == "QUARANTINED":
            issues.append("Model is currently marked QUARANTINED")

        if manifest.approval_status != "APPROVED":
            issues.append(f"Approval status is '{manifest.approval_status}' (must be 'APPROVED')")

        if allowed_versions is not None and manifest.model_version not in allowed_versions:
            issues.append(
                f"Version '{manifest.model_version}' not in whitelist: {sorted(allowed_versions)}"
            )

        artefact_path = path / manifest.artefact_relpath
        artefact_found = artefact_path.is_file()
        if not artefact_found:
            issues.append(f"Model artefact weights file missing: {manifest.artefact_relpath}")
            return {
                "model_id": manifest.model_id,
                "model_dir": str(path),
                "manifest_found": True,
                "manifest_version": manifest.manifest_version,
                "model_version": manifest.model_version,
                "approval_status": manifest.approval_status,
                "is_approved": manifest.is_approved(allowed_versions),
                "artefact_found": False,
                "expected_digest": manifest.artefact_digest,
                "observed_digest": "",
                "digest_matches": False,
                "feature_count": len(manifest.feature_schema),
                "quarantined": is_quarantined,
                "audit_passed": False,
                "issues": issues,
            }

        is_valid, expected, observed = manifest.verify_artefact_integrity(path)
        if not is_valid:
            issues.append(
                f"Cryptographic digest mismatch: expected '{expected}', observed '{observed}'"
            )

        return {
            "model_id": manifest.model_id,
            "model_dir": str(path),
            "manifest_found": True,
            "manifest_version": manifest.manifest_version,
            "model_version": manifest.model_version,
            "approval_status": manifest.approval_status,
            "is_approved": manifest.is_approved(allowed_versions),
            "artefact_found": True,
            "expected_digest": expected,
            "observed_digest": observed,
            "digest_matches": is_valid,
            "feature_count": len(manifest.feature_schema),
            "quarantined": is_quarantined,
            "audit_passed": len(issues) == 0,
            "issues": issues,
        }

    def load(
        self,
        model_dir: Path | str,
        allowed_versions: set[str] | None = None,
        auto_quarantine: bool = True,
        verify_feature_schema: list[str] | None = None,
    ) -> tuple[ModelManifest, LogisticRegressionPredictor, ClimatologyBaseline]:
        """Verify cryptographic integrity, schema, and approval before loading model weights.

        Parameters
        ----------
        model_dir : Path | str
            Directory housing the model manifest and serialized weights.
        allowed_versions : set[str] | None
            Optional whitelist of approved model versions.
        auto_quarantine : bool, default True
            If True, automatically moves tampered models to the quarantine repository.
        verify_feature_schema : list[str] | None
            Optional list of candidate features to verify for schema compatibility.

        Returns
        -------
        tuple[ModelManifest, LogisticRegressionPredictor, ClimatologyBaseline]
            Verified manifest, logistic regression predictor, and baseline.

        Raises
        ------
        MissingManifestError
            If model_manifest.json does not exist.
        UnapprovedModelVersionError
            If approval_status is not APPROVED or version is disallowed.
        MissingArtefactError
            If serialized weights file does not exist.
        ModelTamperingError
            If file digest does not match manifest digest.
        IncompatibleFeatureSchemaError
            If required features are missing from candidate feature set.
        """
        path = Path(model_dir)
        manifest_path = path / "model_manifest.json"

        # 1. Verify manifest existence
        if not manifest_path.is_file():
            raise MissingManifestError(f"Model manifest not found at: {manifest_path}")

        manifest = ModelManifest.from_json(manifest_path)

        # 2. Check quarantine status and approvals
        if (path / ".quarantined").is_file() or manifest.approval_status == "QUARANTINED":
            raise UnapprovedModelVersionError(
                f"Model [{manifest.model_id}] is currently QUARANTINED and cannot be loaded."
            )

        if manifest.approval_status != "APPROVED":
            raise UnapprovedModelVersionError(
                f"Model [{manifest.model_id}] has unapproved status: '{manifest.approval_status}'. "
                "Only 'APPROVED' models are permitted for operational inference."
            )

        if allowed_versions is not None and manifest.model_version not in allowed_versions:
            raise UnapprovedModelVersionError(
                f"Version '{manifest.model_version}' not in approved list: {allowed_versions}"
            )

        # 3. Check weights artefact existence
        artefact_path = path / manifest.artefact_relpath
        if not artefact_path.is_file():
            raise MissingArtefactError(f"Model artefact weights file missing at: {artefact_path}")

        # 4. Cryptographic integrity check (SHA-256)
        is_valid, expected, observed = manifest.verify_artefact_integrity(path)
        if not is_valid:
            logger.critical(
                "SECURITY ALERT: Tampered artefact at %s! Expected: %s, Observed: %s",
                artefact_path,
                expected,
                observed,
            )
            if auto_quarantine:
                self.quarantine_manager.quarantine_model(
                    model_dir=path,
                    reason="ARTEFACT_DIGEST_MISMATCH",
                    details=(
                        f"Hash mismatch for '{manifest.artefact_relpath}'. "
                        f"Expected SHA-256: {expected}, Observed SHA-256: {observed}."
                    ),
                    expected_digest=expected,
                    observed_digest=observed,
                )
            raise ModelTamperingError(
                f"Model artefact '{manifest.artefact_relpath}' failed digest verification! "
                f"Expected: {expected}, Observed: {observed}. Possible tampering detected."
            )

        # 5. Feature schema compatibility check
        if verify_feature_schema is not None:
            is_compat, missing = manifest.validate_feature_compatibility(verify_feature_schema)
            if not is_compat:
                raise IncompatibleFeatureSchemaError(
                    f"Candidate features do not satisfy model feature schema. Missing: {missing}"
                )

        # 6. Safe load of deserialized model weights
        with open(artefact_path, encoding="utf-8") as f:
            weights_data = json.load(f)
        predictor = LogisticRegressionPredictor.from_dict(weights_data)

        # 7. Safe load of baseline
        baseline_path = path / "baseline.json"
        if baseline_path.is_file():
            with open(baseline_path, encoding="utf-8") as f:
                baseline_data = json.load(f)
            baseline = ClimatologyBaseline.from_dict(baseline_data)
        else:
            baseline = ClimatologyBaseline()

        logger.info(
            "Securely loaded verified model [%s v%s, digest=%s]",
            manifest.model_id,
            manifest.model_version,
            manifest.artefact_digest[:12],
        )
        return manifest, predictor, baseline
