"""Job monitoring and status inspection API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from enso_api.jobs import get_job_async, list_jobs_async

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    """List recent background jobs and their execution states."""
    jobs = await list_jobs_async(limit=limit)
    return {
        "jobs": jobs,
        "count": len(jobs),
    }


@router.get("/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieve execution status, logs, and outputs for a specific background job."""
    job = await get_job_async(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return job
