"""API route for automated climate data ingestion, provider coverage, and scheduled jobs."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from enso_api.db import db_get_climate_coverage, db_list_ingestion_logs
from enso_api.ingestion import get_ingestion_scheduler
from enso_api.ingestion.coordinator import ClimateIngestionCoordinator

logger = logging.getLogger("enso_api.routes.ingestion")

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


class IngestionCoverageItem(BaseModel):
    source_id: str
    provider_name: str
    dataset_name: str
    dataset_version: str
    temporal_frequency: str = Field(default="monthly", alias="frequency")
    units: str = Field(default="°C / mm")
    spatial_coverage: str = Field(default="Regional")
    earliest_observation: str | None = None
    latest_observation: str | None = None
    latest_observation_date: str | None = None
    last_retrieval_timestamp: str | None = None
    last_checked_timestamp: str | None = None
    update_status: str = Field(default="OPERATIONAL", alias="status")
    record_count: int = Field(default=0, alias="total_records")
    provenance_url: str | None = Field(default=None, alias="primary_url")
    checksum_sha256: str | None = None
    notes: str | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}


class IngestionHistoryItem(BaseModel):
    log_id: str
    job_id: str
    source_id: str
    status: str
    start_time: str
    end_time: str | None
    records_added: int
    records_updated: int
    latest_observation: str | None
    validation_status: str | None
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    checksum_sha256: str | None = None


class SchedulerStatusResponse(BaseModel):
    is_running: bool
    is_job_active: bool
    next_run_time_utc: str | None
    cadence: str
    timezone: str


class TriggerRunResponse(BaseModel):
    status: str
    message: str
    job_id: str | None = None


@router.get("/coverage", response_model=list[IngestionCoverageItem])
async def get_coverage_report() -> list[dict[str, Any]]:
    """Retrieve actual earliest and latest climate observation coverage for all public providers."""
    records = await db_get_climate_coverage()
    if records:
        return records

    # If database records have not yet been populated by an ingestion run, inspect local files
    coordinator = ClimateIngestionCoordinator()
    fallback_records = await coordinator.get_coverage_summary()
    return fallback_records


@router.get("/history", response_model=list[IngestionHistoryItem])
async def get_ingestion_history(
    limit: int = Query(default=50, ge=1, le=500),
    source_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Retrieve historical automated ingestion run logs and validation results."""
    records = await db_list_ingestion_logs(limit=limit, source_id=source_id)
    mapped = []
    for r in records:
        mapped.append(
            {
                "log_id": str(r["id"]),
                "job_id": r["job_id"] or "unknown",
                "source_id": r["source_id"],
                "status": r["lifecycle_stage"],
                "start_time": r["created_at"],
                "end_time": r["created_at"],
                "records_added": r["records_inserted"],
                "records_updated": r["records_updated"],
                "latest_observation": r["latest_date_ingested"],
                "validation_status": "VALIDATED" if not r["error_message"] else "FAILED",
                "warnings": r["validation_warnings"] or [],
                "error_message": r["error_message"],
                "checksum_sha256": r["raw_artifact_sha256"],
            }
        )
    return mapped


@router.get("/scheduler", response_model=SchedulerStatusResponse)
async def get_scheduler_status() -> dict[str, Any]:
    """Retrieve live status of persistent daily climate ingestion background scheduler."""
    scheduler = get_ingestion_scheduler()
    next_run = scheduler.get_next_run_time()
    return {
        "is_running": scheduler.is_running,
        "is_job_active": scheduler.is_job_active,
        "next_run_time_utc": next_run.isoformat() if next_run else None,
        "cadence": "Daily at 02:00:00 UTC",
        "timezone": "UTC",
    }


@router.post("/run-now", response_model=TriggerRunResponse)
async def run_ingestion_now(source_id: str | None = None) -> dict[str, Any]:
    """Trigger an immediate automated climate ingestion run across providers."""
    scheduler = get_ingestion_scheduler()
    if scheduler.is_job_active:
        return {
            "status": "already_running",
            "message": "An ingestion run is already actively running. Duplicate concurrent execution prevented.",
            "job_id": None,
        }

    sources = [source_id] if source_id else None
    run_res = await scheduler.trigger_now(sources=sources)
    job_id = run_res.get("job_id") if isinstance(run_res, dict) else None
    if job_id:
        return {
            "status": "triggered",
            "message": f"Daily climate ingestion job {job_id} successfully executed.",
            "job_id": job_id,
        }

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to initiate climate ingestion job.",
    )


@router.post("/refresh-coverage")
async def refresh_coverage() -> dict[str, Any]:
    """Refresh coverage status and checksums directly from cleaned climate datasets."""
    coordinator = ClimateIngestionCoordinator()
    summary = await coordinator.get_coverage_summary()
    return {
        "status": "success",
        "coverage_sources": len(summary),
        "sources": summary,
    }
