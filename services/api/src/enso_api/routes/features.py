"""Feature engineering API router."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from enso_api.jobs import JobConflictError, submit_job

router = APIRouter(prefix="/api/v1/features", tags=["features"])


class FeaturesJobRequest(BaseModel):
    cleaned_dir: str = Field(
        default="data/cleaned",
        description="Path to cleaned input datasets directory.",
    )
    output_dir: str = Field(
        default="data/features",
        description="Path to features output directory.",
    )


class JobSubmissionResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    message: str
    started_at: str


@router.get("/status")
def get_features_status() -> dict[str, Any]:
    """Inspect feature dataset status, reference distribution, and validation metrics."""
    features_csv = Path("data/features/enso_rainfall_features_labelled.csv")
    ref_dist_json = Path("data/features/climatology_reference_distribution.json")
    data_dict_md = Path("data/features/DATA_DICTIONARY.md")

    if not features_csv.is_file():
        return {
            "status": "uninitialized",
            "exists": False,
            "message": (
                "Feature dataset not yet generated. Run a feature job to generate features."
            ),
        }

    # Read reference distribution
    ref_dist = None
    if ref_dist_json.is_file():
        with contextlib.suppress(Exception), open(ref_dist_json, encoding="utf-8") as f:
            ref_dist = json.load(f)

    # Read basic row and column info
    columns: list[str] = []
    row_count = 0
    years: list[int] = []
    try:
        with open(features_csv, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            columns = header
            year_idx = header.index("year") if "year" in header else 0
            for line in f:
                parts = line.strip().split(",")
                if len(parts) > year_idx and parts[year_idx].isdigit():
                    years.append(int(parts[year_idx]))
                row_count += 1
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
        }

    # Data dictionary preview
    data_dict_preview = None
    if data_dict_md.is_file():
        with contextlib.suppress(Exception), open(data_dict_md, encoding="utf-8") as f:
            data_dict_preview = f.read(2000)

    return {
        "status": "operational",
        "exists": True,
        "features_csv": str(features_csv),
        "row_count": row_count,
        "feature_count": len(columns),
        "columns": columns,
        "year_min": min(years) if years else None,
        "year_max": max(years) if years else None,
        "reference_distribution": ref_dist,
        "data_dictionary_preview": data_dict_preview,
    }


@router.post(
    "/jobs",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_features_job(
    request: FeaturesJobRequest,
) -> JobSubmissionResponse:
    """Launch asynchronous feature generation pipeline."""
    try:
        job = await submit_job("features", request.model_dump())
        return JobSubmissionResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            message="Feature engineering job submitted and running in background.",
            started_at=job.started_at,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
