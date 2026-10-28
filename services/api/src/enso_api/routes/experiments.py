"""Experiments, benchmarks, and calibration evaluation API router."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from enso_api.jobs import JobConflictError, submit_job

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


class ExperimentJobRequest(BaseModel):
    features_csv: str = Field(
        default="data/features/enso_rainfall_features_labelled.csv",
        description="Path to labelled features CSV.",
    )
    output_dir: str = Field(
        default="reports/experiments/nonlinear_comparison",
        description="Output directory for comparison manifests and reports.",
    )
    seed: int = Field(
        default=42,
        description="Random seed for reproducibility.",
    )


class JobSubmissionResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    message: str
    started_at: str


@router.get("")
def list_experiments() -> dict[str, Any]:
    """List available experiment runs and reports."""
    reports_root = Path("reports/experiments")
    experiments: list[dict[str, Any]] = []

    if reports_root.is_dir():
        for manifest_path in reports_root.glob("*/experiment_comparison_manifest.json"):
            with contextlib.suppress(Exception), open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
                experiments.append(
                    {
                        "experiment_id": data.get("experiment_id"),
                        "directory": manifest_path.parent.name,
                        "timestamp_utc": data.get("timestamp_utc"),
                        "random_seed": data.get("random_seed"),
                        "software_versions": data.get("software_versions"),
                        "complexity_justified": data.get("verdict", {}).get(
                            "is_nonlinear_complexity_justified"
                        ),
                        "best_holdout_model": data.get("verdict", {}).get("best_holdout_model"),
                    }
                )

    return {
        "experiments": experiments,
        "count": len(experiments),
    }


@router.get("/latest")
def get_latest_experiment() -> dict[str, Any]:
    """Retrieve full multi-model comparison manifest and diagnostic reports."""
    manifest_path = Path(
        "reports/experiments/nonlinear_comparison/experiment_comparison_manifest.json"
    )
    if not manifest_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest experiment manifest not found. Please run an experiment suite first.",
        )

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    # Read ablation report if available
    ablation_path = Path("reports/experiments/nonlinear_comparison/ablation_report.json")
    ablations = None
    if ablation_path.is_file():
        with contextlib.suppress(Exception), open(ablation_path, encoding="utf-8") as f:
            ablations = json.load(f)

    # Read threshold report if available
    threshold_path = Path("reports/experiments/nonlinear_comparison/threshold_report.json")
    thresholds = None
    if threshold_path.is_file():
        with contextlib.suppress(Exception), open(threshold_path, encoding="utf-8") as f:
            thresholds = json.load(f)

    # Read location report if available
    location_path = Path("reports/experiments/nonlinear_comparison/location_report.json")
    locations = None
    if location_path.is_file():
        with contextlib.suppress(Exception), open(location_path, encoding="utf-8") as f:
            locations = json.load(f)

    return {
        "status": "operational",
        "manifest": manifest,
        "ablation_report": ablations,
        "threshold_report": thresholds,
        "location_report": locations,
    }


@router.get("/{experiment_id}")
def get_experiment_by_id(experiment_id: str) -> dict[str, Any]:
    """Retrieve specific experiment manifest by ID."""
    reports_root = Path("reports/experiments")
    if not reports_root.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No experiments found.")

    for manifest_path in reports_root.glob("*/experiment_comparison_manifest.json"):
        with contextlib.suppress(Exception), open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
            matched_id = data.get("experiment_id") == experiment_id
            matched_dir = manifest_path.parent.name == experiment_id
            if matched_id or matched_dir:
                return {
                    "status": "found",
                    "manifest": data,
                }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Experiment '{experiment_id}' not found.",
    )


@router.post(
    "/jobs",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_experiment_job(
    request: ExperimentJobRequest,
) -> JobSubmissionResponse:
    """Launch asynchronous multi-model comparison experiment."""
    try:
        job = await submit_job("experiment", request.model_dump())
        return JobSubmissionResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            message="Multi-model experiment job submitted and running in background.",
            started_at=job.started_at,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
