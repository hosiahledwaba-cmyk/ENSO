"""Models, cryptographic integrity, training, and poisoning resilience API router."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from enso_api.jobs import JobConflictError, submit_job
from ml.registry.loader import SecureModelLoader
from ml.registry.manifest import ModelManifest
from ml.registry.quarantine import (
    ModelIntegrityError,
    ModelQuarantineManager,
)
from ml.security.poisoning import (
    PoisoningAttackClass,
    TrainingPoisoningHarness,
)

router = APIRouter(prefix="/api/v1", tags=["models"])


class TrainingJobRequest(BaseModel):
    features_csv: str = Field(
        default="data/features/enso_rainfall_features_labelled.csv",
        description="Path to labelled features CSV.",
    )
    model_dir: str = Field(
        default="models/logistic_regression_baseline",
        description="Output directory for trained model artifacts.",
    )
    holdout_count: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Number of final untouched seasons reserved for holdout evaluation.",
    )


class JobSubmissionResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    message: str
    started_at: str


class ModelVerificationRequest(BaseModel):
    model_dir: str = Field(
        default="models/logistic_regression_baseline",
        description="Model directory containing model_manifest.json and weights.",
    )


class QuarantineRequest(BaseModel):
    model_dir: str = Field(..., description="Suspect model directory to isolate.")
    reason: str = Field(
        default="MANUAL_QUARANTINE",
        description="Reason code, e.g. ARTEFACT_DIGEST_MISMATCH, UNAPPROVED_VERSION.",
    )
    details: str = Field(..., description="Audit details or investigator observations.")


class QuarantineReviewRequest(BaseModel):
    dossier_id: str
    new_status: str = Field(
        default="CONFIRMED_COMPROMISED",
        description="Updated status: CONFIRMED_COMPROMISED, CLEARED, or REPLACED.",
    )
    notes: str = Field(default="", description="Investigator notes.")


class ReplacementRequest(BaseModel):
    target_model_dir: str = Field(
        ..., description="Quarantined or corrupted model directory to replace."
    )
    replacement_source_dir: str = Field(
        ..., description="Approved golden model directory to restore from."
    )
    approved_by: str = Field(
        default="security_lead", description="Authorizing reviewer identifier."
    )


class PoisoningExperimentRequest(BaseModel):
    attack_class: PoisoningAttackClass = Field(
        default="LABEL_FLIPPING",
        description="Attack class: LABEL_FLIPPING, SUBPOPULATION_FEATURE_POISONING, etc.",
    )
    attack_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Attack-specific configuration (e.g. flip_fraction, shift_delta, n_outliers).",
    )
    holdout_count: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Number of final untouched seasons reserved for holdout evaluation.",
    )


@router.get("/models")
def list_models() -> dict[str, Any]:
    """List available trained models, manifests, and cryptographic status."""
    models_root = Path("models")
    models: list[dict[str, Any]] = []
    loader = SecureModelLoader()

    if models_root.is_dir():
        for manifest_path in models_root.glob("*/model_manifest.json"):
            model_dir = manifest_path.parent
            if model_dir.name.startswith("."):
                continue

            audit_info = loader.audit_model(model_dir)
            with contextlib.suppress(Exception), open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
                models.append(
                    {
                        "model_id": model_dir.name,
                        "path": str(model_dir),
                        "model_version": manifest.get("model_version", "1.0.0"),
                        "approval_status": manifest.get("approval_status", "APPROVED"),
                        "manifest_version": manifest.get("manifest_version", "1.0"),
                        "artefact_digest": manifest.get("artefact_digest", ""),
                        "training_data_fingerprint": manifest.get(
                            "training_data_fingerprint", manifest.get("dataset_sha256", "")
                        ),
                        "audit_passed": audit_info.get("audit_passed", False),
                        "quarantined": audit_info.get("quarantined", False),
                        "architecture": manifest.get("model_type", "logistic_regression"),
                        "training_seasons": manifest.get("training_seasons"),
                        "holdout_seasons": manifest.get("holdout_seasons"),
                        "evaluation_metrics": manifest.get("evaluation_report", {}),
                        "holdout_bss": manifest.get("holdout_bss"),
                        "beats_baseline_on_holdout": manifest.get("beats_baseline_on_holdout"),
                    }
                )

    return {
        "models": models,
        "count": len(models),
    }


@router.get("/models/active")
def get_active_model() -> dict[str, Any]:
    """Retrieve full manifest and feature requirements of active operational baseline model."""
    manifest_path = Path("models/logistic_regression_baseline/model_manifest.json")
    if not manifest_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active model manifest not found. Please train a baseline model first.",
        )

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Read logistic weights if available
    weights_path = Path("models/logistic_regression_baseline/logistic_regression.json")
    weights = None
    if weights_path.is_file():
        with contextlib.suppress(Exception), open(weights_path, encoding="utf-8") as f:
            weights = json.load(f)

    # Read baseline info
    baseline_path = Path("models/logistic_regression_baseline/baseline.json")
    baseline_info = None
    if baseline_path.is_file():
        with contextlib.suppress(Exception), open(baseline_path, encoding="utf-8") as f:
            baseline_info = json.load(f)

    # Run cryptographic audit
    loader = SecureModelLoader()
    audit = loader.audit_model(manifest_path.parent)

    return {
        "status": "operational",
        "model_id": "logistic_regression_baseline",
        "manifest": manifest,
        "logistic_weights": weights,
        "climatology_baseline": baseline_info,
        "audit": audit,
    }


@router.get("/models/audit")
def audit_all_models() -> dict[str, Any]:
    """Perform pre-load integrity, manifest, and approval audit across all models."""
    models_root = Path("models")
    loader = SecureModelLoader()
    items: list[dict[str, Any]] = []

    if models_root.is_dir():
        for dir_item in models_root.iterdir():
            if dir_item.is_dir() and not dir_item.name.startswith("."):
                item_audit = loader.audit_model(dir_item)
                items.append(item_audit)

    quarantine_manager = ModelQuarantineManager()
    quarantined_dossiers = quarantine_manager.list_quarantined_models()

    passed_count = sum(1 for m in items if m.get("audit_passed"))
    compromised_count = sum(1 for m in items if not m.get("audit_passed"))

    return {
        "audit_timestamp_utc": True,
        "total_scanned": len(items),
        "passed_count": passed_count,
        "compromised_count": compromised_count,
        "quarantined_count": len(quarantined_dossiers),
        "posture": "HEALTHY" if compromised_count == 0 else "DEGRADED_ATTENTION_REQUIRED",
        "models": items,
        "quarantined_dossiers": [d.to_dict() for d in quarantined_dossiers],
    }


@router.post("/models/verify")
def verify_model_integrity(request: ModelVerificationRequest) -> dict[str, Any]:
    """Verify cryptographic SHA-256 digest of specified model artefact against manifest."""
    loader = SecureModelLoader()
    audit_result = loader.audit_model(request.model_dir)
    return {
        "model_dir": request.model_dir,
        "audit": audit_result,
        "verified": audit_result.get("audit_passed", False),
    }


@router.post("/models/quarantine")
def quarantine_model_endpoint(request: QuarantineRequest) -> dict[str, Any]:
    """Isolate suspect model artefact, mark as QUARANTINED, and generate forensic dossier."""
    manager = ModelQuarantineManager()
    target = Path(request.model_dir)
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model directory not found: {request.model_dir}",
        )

    # Compute observed digest if weights exist
    manifest_path = target / "model_manifest.json"
    expected = ""
    observed = ""
    if manifest_path.is_file():
        with contextlib.suppress(Exception):
            m = ModelManifest.from_json(manifest_path)
            expected = m.artefact_digest
            observed = m.compute_artefact_digest(target)

    dossier = manager.quarantine_model(
        model_dir=request.model_dir,
        reason=request.reason,
        details=request.details,
        expected_digest=expected,
        observed_digest=observed,
    )
    return {
        "status": "quarantined",
        "message": f"Model '{target.name}' quarantined successfully.",
        "dossier": dossier.to_dict(),
    }


@router.get("/models/quarantine")
def list_quarantined_models_endpoint() -> dict[str, Any]:
    """List all quarantined models and audit dossiers."""
    manager = ModelQuarantineManager()
    dossiers = manager.list_quarantined_models()
    return {
        "quarantined_models": [d.to_dict() for d in dossiers],
        "count": len(dossiers),
    }


@router.post("/models/quarantine/review")
def review_quarantined_model_endpoint(request: QuarantineReviewRequest) -> dict[str, Any]:
    """Update review investigation status of a quarantined model."""
    manager = ModelQuarantineManager()
    try:
        updated = manager.review_quarantined_model(
            dossier_id=request.dossier_id,
            new_status=request.new_status,  # type: ignore[arg-type]
            notes=request.notes,
        )
        return {"status": "updated", "dossier": updated.to_dict()}
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/models/replace")
def replace_quarantined_model_endpoint(request: ReplacementRequest) -> dict[str, Any]:
    """Safely restore/replace suspect model directory using an approved golden candidate."""
    manager = ModelQuarantineManager()
    try:
        restored = manager.replace_quarantined_model(
            target_model_dir=request.target_model_dir,
            replacement_source_dir=request.replacement_source_dir,
            approved_by=request.approved_by,
        )
        return {
            "status": "replaced",
            "message": f"Model restored from {request.replacement_source_dir}.",
            "manifest": restored.model_dump(),
        }
    except (FileNotFoundError, ModelIntegrityError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/models/poisoning/scenarios")
def list_poisoning_scenarios() -> dict[str, Any]:
    """List available controlled poisoning attack classes and parameters."""
    return {
        "scenarios": [
            {
                "attack_class": "LABEL_FLIPPING",
                "name": "Label Flipping (Drought Alert Suppression)",
                "description": (
                    "Flips positive drought targets (1 -> 0) on highest-impact El Niño "
                    "seasons to blind seasonal risk detection."
                ),
                "parameters": {
                    "flip_fraction": {"type": "float", "default": 0.20, "min": 0.05, "max": 0.50}
                },
                "tested_threat": "Targeted manipulation of historical severe drought occurrences.",
            },
            {
                "attack_class": "SUBPOPULATION_FEATURE_POISONING",
                "name": "Subpopulation Clean-Label Feature Bias",
                "description": (
                    "Shifts antecedent Pacific SST anomalies (ONI ASO) negatively on drought "
                    "seasons without modifying labels, inverting the physical slope."
                ),
                "parameters": {
                    "feature_name": {"type": "string", "default": "oni_aso_degc"},
                    "shift_delta": {"type": "float", "default": -1.5, "min": -3.0, "max": 3.0},
                },
                "tested_threat": (
                    "Clean-label subpopulation shift evading basic marginal distribution checks."
                ),
            },
            {
                "attack_class": "EXTREME_LEVERAGE_OUTLIER",
                "name": "Extreme Leverage Outlier Injection",
                "description": (
                    "Injects synthetic high-leverage covariate points (super-El Niño magnitude + "
                    "spring drought deficit) paired with non-drought target to rotate hyperplane."
                ),
                "parameters": {
                    "n_outliers": {"type": "integer", "default": 1, "min": 1, "max": 3}
                },
                "tested_threat": (
                    "Single or dual high-leverage points rotating linear decision boundaries."
                ),
            },
            {
                "attack_class": "TARGETED_BACKDOOR",
                "name": "Targeted Backdoor Watermark",
                "description": (
                    "Embeds specific feature trigger combination paired with target=0 to "
                    "establish dormant bypass behavior."
                ),
                "parameters": {
                    "trigger_feature": {"type": "string", "default": "nino34_aso_anom_degc"},
                    "trigger_value": {"type": "float", "default": 3.14},
                },
                "tested_threat": "Backdoor pattern trigger compromising specific predictions.",
            },
        ],
        "threat_limitations": [
            "Linear models with small training seasons (N=24) are vulnerable to leverage outliers.",
            "Cryptographic manifests guarantee post-training artefact integrity, not data purity.",
            "Clean-label poisons within statistical bounds require multi-variate leverage audits.",
        ],
        "recovery_protocol": [
            "1. Revoke and quarantine suspect model manifest.",
            "2. Audit training dataset SHA-256 against authenticated provenance baseline.",
            "3. Restore dataset from tamper-evident backup snapshot.",
            "4. Retrain model and verify holdout BSS > 0 against climatological baseline.",
            "5. Re-sign model manifest and commit cryptographic digest.",
        ],
    }


@router.post("/models/poisoning/evaluate")
def evaluate_poisoning_experiment(request: PoisoningExperimentRequest) -> dict[str, Any]:
    """Execute isolated poisoning simulation and compare candidate model against clean baseline."""
    harness = TrainingPoisoningHarness()
    try:
        report = harness.run_experiment(
            attack_class=request.attack_class,
            attack_params=request.attack_params,
            holdout_count=request.holdout_count,
        )
        return {
            "status": "completed",
            "report": report.model_dump(),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Poisoning experiment failed: {exc}",
        ) from exc


@router.get("/training/status")
def get_training_status() -> dict[str, Any]:
    """Retrieve active training status and latest evaluation summary."""
    summary_path = Path("models/logistic_regression_baseline/evaluation_summary.json")
    if not summary_path.is_file():
        return {
            "status": "uninitialized",
            "message": "No training runs completed yet.",
        }

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    return {
        "status": "operational",
        "summary": summary,
    }


@router.post(
    "/training/jobs",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_training_job(
    request: TrainingJobRequest,
) -> JobSubmissionResponse:
    """Launch asynchronous baseline model training pipeline."""
    try:
        job = await submit_job("training", request.model_dump())
        return JobSubmissionResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            message="Model training job submitted and running in background.",
            started_at=job.started_at,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
