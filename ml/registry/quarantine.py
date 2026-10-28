"""Model quarantine, tampering detection, and safe artefact replacement subsystem."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ml.registry.manifest import ModelManifest

logger = logging.getLogger("enso_ml.registry.quarantine")


class ModelIntegrityError(Exception):
    """Base exception for model integrity, verification, or schema failures."""


class ModelTamperingError(ModelIntegrityError):
    """Raised when a model artefact digest does not match its registered manifest digest."""


class UnapprovedModelVersionError(ModelIntegrityError):
    """Raised when a model version has not been approved or is marked deprecated/revoked."""


class IncompatibleFeatureSchemaError(ModelIntegrityError):
    """Raised when a candidate dataset or inference input violates the model feature schema."""


class MissingManifestError(ModelIntegrityError):
    """Raised when a model directory lacks a valid model_manifest.json."""


class MissingArtefactError(ModelIntegrityError):
    """Raised when the serialized model weights file referenced in manifest does not exist."""


QuarantineStatus = Literal[
    "PENDING_REVIEW",
    "CONFIRMED_COMPROMISED",
    "CLEARED",
    "REPLACED",
]


class QuarantineDossier(BaseModel):
    """Formal audit record generated whenever an artefact is placed into quarantine."""

    dossier_id: str = Field(default_factory=lambda: f"quar_{uuid.uuid4().hex[:12]}")
    model_id: str
    model_version: str
    original_model_path: str
    quarantine_store_path: str
    quarantined_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason: str
    details: str
    expected_digest: str = ""
    observed_digest: str = ""
    investigation_status: QuarantineStatus = "PENDING_REVIEW"
    reviewer_notes: str = ""
    resolved_at_utc: str | None = None
    replacement_model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ModelAuditItem(BaseModel):
    """Audit report item for a model directory."""

    model_id: str
    model_dir: str
    manifest_found: bool
    manifest_version: str = ""
    model_version: str = ""
    approval_status: str = "UNKNOWN"
    is_approved: bool = False
    artefact_found: bool = False
    expected_digest: str = ""
    observed_digest: str = ""
    digest_matches: bool = False
    feature_count: int = 0
    quarantined: bool = False
    quarantine_dossier_id: str | None = None
    audit_passed: bool = False
    issues: list[str] = Field(default_factory=list)


class ModelQuarantineManager:
    """Manages isolation, formal review, and safe replacement of suspect model artefacts."""

    def __init__(self, quarantine_dir: Path | str = "models/.quarantine") -> None:
        self.quarantine_dir = Path(quarantine_dir)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def quarantine_model(
        self,
        model_dir: Path | str,
        reason: str,
        details: str,
        expected_digest: str = "",
        observed_digest: str = "",
    ) -> QuarantineDossier:
        """Isolate a suspect model directory, generate an audit dossier, and revoke active status.

        Parameters
        ----------
        model_dir : Path | str
            Directory of the suspect model.
        reason : str
            Classification code (e.g. ARTEFACT_DIGEST_MISMATCH, UNAPPROVED_VERSION).
        details : str
            Human-readable explanation of the detected tampering or anomaly.
        expected_digest : str
            Digest stated in manifest.
        observed_digest : str
            Actual digest computed from the artefact file.

        Returns
        -------
        QuarantineDossier
            Audit dossier recording the isolation event.
        """
        source_dir = Path(model_dir)
        timestamp_slug = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        model_id = source_dir.name
        model_version = "unknown"

        # Read manifest if readable to capture metadata
        manifest_path = source_dir / "model_manifest.json"
        if manifest_path.is_file():
            try:
                manifest = ModelManifest.from_json(manifest_path)
                model_id = manifest.model_id
                model_version = manifest.model_version
                # Mark manifest as QUARANTINED in source directory
                manifest.approval_status = "QUARANTINED"
                manifest.to_json(manifest_path)
            except Exception as e:
                logger.warning("Could not parse manifest during quarantine: %s", e)

        target_quarantine_subdir = self.quarantine_dir / f"{model_id}_{timestamp_slug}"
        target_quarantine_subdir.mkdir(parents=True, exist_ok=True)

        dossier = QuarantineDossier(
            model_id=model_id,
            model_version=model_version,
            original_model_path=str(source_dir),
            quarantine_store_path=str(target_quarantine_subdir),
            reason=reason,
            details=details,
            expected_digest=expected_digest,
            observed_digest=observed_digest,
            investigation_status="PENDING_REVIEW",
        )

        # Copy all current artefacts into quarantine store for forensic inspection
        if source_dir.is_dir():
            for item in source_dir.iterdir():
                if item.name.startswith("."):
                    continue
                dest = target_quarantine_subdir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)

        # Save the dossier into the quarantine folder
        dossier_path = target_quarantine_subdir / "quarantine_dossier.json"
        with open(dossier_path, "w", encoding="utf-8") as f:
            f.write(dossier.model_dump_json(indent=2))

        # Also write a quarantine marker in the source directory
        marker_path = source_dir / ".quarantined"
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump(dossier.to_dict(), f, indent=2)

        logger.warning(
            "QUARANTINED suspect model [%s] to [%s]. Reason: %s",
            model_id,
            target_quarantine_subdir,
            reason,
        )
        return dossier

    def list_quarantined_models(self) -> list[QuarantineDossier]:
        """List all quarantine dossiers recorded in the quarantine store."""
        dossiers: list[QuarantineDossier] = []
        if not self.quarantine_dir.is_dir():
            return dossiers

        for dossier_file in self.quarantine_dir.glob("*/quarantine_dossier.json"):
            try:
                with open(dossier_file, encoding="utf-8") as f:
                    data = json.load(f)
                dossiers.append(QuarantineDossier(**data))
            except Exception as exc:
                logger.warning("Error reading dossier %s: %s", dossier_file, exc)

        return sorted(dossiers, key=lambda d: d.quarantined_at_utc, reverse=True)

    def review_quarantined_model(
        self,
        dossier_id: str,
        new_status: QuarantineStatus,
        notes: str,
    ) -> QuarantineDossier:
        """Update review notes and investigation status of a quarantined artefact."""
        for dossier_file in self.quarantine_dir.glob("*/quarantine_dossier.json"):
            try:
                with open(dossier_file, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("dossier_id") == dossier_id:
                    dossier = QuarantineDossier(**data)
                    dossier.investigation_status = new_status
                    dossier.reviewer_notes = notes
                    dossier.resolved_at_utc = datetime.now(UTC).isoformat()
                    with open(dossier_file, "w", encoding="utf-8") as f:
                        f.write(dossier.model_dump_json(indent=2))
                    return dossier
            except Exception as exc:
                logger.warning("Error reading dossier %s: %s", dossier_file, exc)

        raise KeyError(f"Quarantine dossier ID '{dossier_id}' not found.")

    def replace_quarantined_model(
        self,
        target_model_dir: Path | str,
        replacement_source_dir: Path | str,
        approved_by: str = "security_lead",
    ) -> ModelManifest:
        """Safely replace a quarantined or corrupted model with an approved golden model.

        Parameters
        ----------
        target_model_dir : Path | str
            Directory of the model being replaced.
        replacement_source_dir : Path | str
            Directory containing the approved replacement candidate.
        approved_by : str
            Identifier of reviewing authority authorizing replacement.

        Returns
        -------
        ModelManifest
            The verified manifest of the newly restored operational model.
        """
        target_path = Path(target_model_dir)
        source_path = Path(replacement_source_dir)

        if not source_path.is_dir():
            raise FileNotFoundError(f"Replacement source directory not found: {source_path}")

        manifest_path = source_path / "model_manifest.json"
        if not manifest_path.is_file():
            raise MissingManifestError(f"Replacement model missing manifest at: {manifest_path}")

        # Verify replacement model manifest integrity before proceeding
        manifest = ModelManifest.from_json(manifest_path)
        is_valid, expected, observed = manifest.verify_artefact_integrity(source_path)
        if not is_valid:
            raise ModelTamperingError(
                f"Cannot replace with compromised candidate: digest mismatch in {source_path}. "
                f"Expected {expected}, observed {observed}."
            )

        if manifest.approval_status != "APPROVED":
            raise UnapprovedModelVersionError(
                f"Replacement model must have approval_status='APPROVED', "
                f"found '{manifest.approval_status}'."
            )

        # Clear existing corrupted files and quarantine marker from target directory
        target_path.mkdir(parents=True, exist_ok=True)
        marker = target_path / ".quarantined"
        if marker.is_file():
            marker.unlink()

        # Copy approved files from replacement source into target directory
        for item in source_path.iterdir():
            if item.name.startswith("."):
                continue
            dest = target_path / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)

        # Verify target directory passes integrity check after replacement
        restored_manifest = ModelManifest.from_json(target_path / "model_manifest.json")
        target_valid, _exp, _obs = restored_manifest.verify_artefact_integrity(target_path)
        if not target_valid:
            raise ModelIntegrityError(
                "Restoration verification failed: target directory digest does not match manifest."
            )

        # Update any corresponding quarantine dossiers
        for dossier in self.list_quarantined_models():
            if (
                Path(dossier.original_model_path).resolve() == target_path.resolve()
                and dossier.investigation_status == "PENDING_REVIEW"
            ):
                self.review_quarantined_model(
                    dossier.dossier_id,
                    new_status="REPLACED",
                    notes=f"Replaced from [{source_path.name}] authorized by [{approved_by}].",
                )

        logger.info(
            "Successfully replaced model in [%s] using approved candidate from [%s].",
            target_path,
            source_path,
        )
        return restored_manifest
