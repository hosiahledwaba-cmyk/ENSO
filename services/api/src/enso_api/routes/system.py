"""System status and diagnostics API router."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from enso_api import __version__
from enso_api.config import Settings
from enso_api.db import check_database_readiness, db_get_table_counts
from enso_api.jobs import list_jobs_async

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class SystemStatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    timestamp_utc: str
    database: dict[str, Any]
    pipelines: dict[str, Any]
    active_jobs: list[dict[str, Any]]


def check_dataset_file(base_dir: Path, dataset_stem: str) -> dict[str, Any]:
    """Check dataset file existence, non-emptiness, and readability without assuming false health.

    Checks authoritative *_monthly.csv with backward-compatible fallback to *_cleaned.csv.
    """
    candidates = [
        base_dir / f"{dataset_stem}_monthly.csv",
        base_dir / f"{dataset_stem}_cleaned.csv",
        base_dir / f"{dataset_stem}.csv",
    ]
    target_path = next((p for p in candidates if p.exists()), candidates[0])

    if not target_path.exists():
        return {
            "dataset": dataset_stem,
            "status": "MISSING",
            "path": str(target_path),
            "size_bytes": 0,
            "is_valid": False,
            "detail": f"Dataset file does not exist at expected path: {target_path}",
        }

    if not target_path.is_file():
        return {
            "dataset": dataset_stem,
            "status": "NOT_A_FILE",
            "path": str(target_path),
            "size_bytes": 0,
            "is_valid": False,
            "detail": f"Path exists but is not a regular file: {target_path}",
        }

    size = target_path.stat().st_size
    if size == 0:
        return {
            "dataset": dataset_stem,
            "status": "EMPTY",
            "path": str(target_path),
            "size_bytes": 0,
            "is_valid": False,
            "detail": f"Dataset file is empty (0 bytes): {target_path}",
        }

    try:
        with open(target_path, encoding="utf-8") as f:
            header = f.readline().strip()
            first_line = f.readline().strip()
            if not header or not first_line:
                return {
                    "dataset": dataset_stem,
                    "status": "EMPTY_OR_NO_ROWS",
                    "path": str(target_path),
                    "size_bytes": size,
                    "is_valid": False,
                    "detail": f"Dataset file contains header but no rows: {target_path}",
                }
    except Exception as exc:
        return {
            "dataset": dataset_stem,
            "status": "CORRUPT_OR_UNREADABLE",
            "path": str(target_path),
            "size_bytes": size,
            "is_valid": False,
            "detail": f"Failed to read dataset file: {exc}",
        }

    return {
        "dataset": dataset_stem,
        "status": "HEALTHY",
        "path": str(target_path),
        "size_bytes": size,
        "is_valid": True,
        "detail": "Verified healthy and readable.",
    }


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(request: Request) -> SystemStatusResponse:
    """Comprehensive diagnostic overview of API, DB, pipelines, and running jobs."""
    settings: Settings = request.app.state.settings

    # 1. Database readiness & counts
    db_check = await check_database_readiness(settings)
    table_counts = await db_get_table_counts()
    db_status = {
        "status": db_check["status"],
        "latency_ms": db_check.get("latency_ms"),
        "detail": db_check.get("detail"),
        "table_counts": table_counts,
    }

    # 2. Pipeline status checks - Authoritative cleaned datasets
    cleaned_dir = Path("data/cleaned")
    dataset_stems = ["chirps_rainfall", "noaa_oni", "noaa_nino34", "noaa_soi"]
    dataset_checks = {stem: check_dataset_file(cleaned_dir, stem) for stem in dataset_stems}

    all_valid = all(d["is_valid"] for d in dataset_checks.values())
    any_missing = any(d["status"] == "MISSING" for d in dataset_checks.values())
    any_corrupt_or_empty = any(
        d["status"] in ("EMPTY", "EMPTY_OR_NO_ROWS", "CORRUPT_OR_UNREADABLE", "NOT_A_FILE")
        for d in dataset_checks.values()
    )

    if all_valid:
        datasets_status = "operational"
    elif any_corrupt_or_empty:
        datasets_status = "degraded"
    elif any_missing:
        datasets_status = "uninitialized"
    else:
        datasets_status = "degraded"

    datasets_ready = all_valid

    features_ready = Path("data/features/enso_rainfall_features_labelled.csv").is_file()
    active_model_ready = Path("models/logistic_regression_baseline/model_manifest.json").is_file()
    latest_experiment_ready = Path(
        "reports/experiments/nonlinear_comparison/experiment_comparison_manifest.json"
    ).is_file()

    # Extract quick summary info if files exist
    model_summary = None
    if active_model_ready:
        with (
            contextlib.suppress(Exception),
            open(
                "models/logistic_regression_baseline/model_manifest.json",
                encoding="utf-8",
            ) as f,
        ):
            manifest = json.load(f)
            model_summary = {
                "architecture": manifest.get("model_architecture"),
                "brier_score": manifest.get("evaluation_metrics", {})
                .get("logistic_regression", {})
                .get("brier_score"),
                "bss": manifest.get("evaluation_metrics", {})
                .get("logistic_regression", {})
                .get("brier_skill_score"),
            }

    experiment_summary = None
    if latest_experiment_ready:
        with (
            contextlib.suppress(Exception),
            open(
                "reports/experiments/nonlinear_comparison/experiment_comparison_manifest.json",
                encoding="utf-8",
            ) as f,
        ):
            manifest = json.load(f)
            experiment_summary = {
                "experiment_id": manifest.get("experiment_id"),
                "timestamp": manifest.get("timestamp_utc"),
                "complexity_justified": manifest.get("verdict", {}).get(
                    "is_nonlinear_complexity_justified"
                ),
                "best_holdout_model": manifest.get("verdict", {}).get("best_holdout_model"),
            }

    pipelines = {
        "datasets": {
            "status": datasets_status,
            "cleaned_ready": datasets_ready,
            "dataset_details": dataset_checks,
        },
        "features": {
            "status": "operational" if features_ready else "uninitialized",
            "features_ready": features_ready,
        },
        "models": {
            "status": "operational" if active_model_ready else "uninitialized",
            "active_model": model_summary,
        },
        "experiments": {
            "status": "operational" if latest_experiment_ready else "uninitialized",
            "latest_experiment": experiment_summary,
        },
    }

    # 3. Active jobs
    all_jobs = await list_jobs_async(limit=10)
    active_jobs = [j for j in all_jobs if j["status"] in ("pending", "running")]

    return SystemStatusResponse(
        service="enso-shield-api",
        version=__version__,
        environment=settings.env,
        timestamp_utc=datetime.now(UTC).isoformat(),
        database=db_status,
        pipelines=pipelines,
        active_jobs=active_jobs,
    )
