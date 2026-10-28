"""Persistent async scheduler for automated daily climate data ingestion."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from enso_api.db import db_get_job, db_save_job, db_update_job
from enso_api.ingestion.coordinator import ClimateIngestionCoordinator

logger = logging.getLogger("enso_api.ingestion.scheduler")

_SCHEDULER_INSTANCE: IngestionScheduler | None = None


class IngestionScheduler:
    """Manages scheduled daily climate data ingestion jobs and prevents concurrent duplicates."""

    def __init__(
        self,
        coordinator: ClimateIngestionCoordinator | None = None,
        cron_hour_utc: int = 2,
        cron_minute_utc: int = 0,
    ) -> None:
        self.coordinator = coordinator or ClimateIngestionCoordinator()
        self.cron_hour_utc = cron_hour_utc
        self.cron_minute_utc = cron_minute_utc
        self._scheduler = AsyncIOScheduler(timezone=UTC)
        self._run_lock = asyncio.Lock()
        self._is_running = False
        self._last_run_started_at: str | None = None
        self._last_run_completed_at: str | None = None
        self._last_run_status: str = "NEVER_RUN"
        self._last_job_id: str | None = None
        self._next_fire_time_utc: str | None = None

    def start(self) -> None:
        """Initialize APScheduler with daily UTC cron trigger."""
        if self._scheduler.running:
            logger.info("IngestionScheduler already running.")
            return

        trigger = CronTrigger(hour=self.cron_hour_utc, minute=self.cron_minute_utc, timezone=UTC)
        job = self._scheduler.add_job(
            self.execute_scheduled_job,
            trigger=trigger,
            id="daily_climate_ingestion_job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        next_fire = job.next_run_time
        self._next_fire_time_utc = next_fire.isoformat() if next_fire else None
        logger.info(
            "Persistent IngestionScheduler started. Next daily run scheduled for: %s",
            self._next_fire_time_utc,
        )

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return bool(self._scheduler.running)

    @property
    def is_job_active(self) -> bool:
        """Check if an ingestion cycle is currently active."""
        return self._is_running or self._run_lock.locked()

    def get_next_run_time(self) -> datetime | None:
        """Retrieve next scheduled run timestamp in UTC."""
        job = self._scheduler.get_job("daily_climate_ingestion_job")
        if job and job.next_run_time:
            nxt: datetime | None = job.next_run_time
            return nxt
        return None

    def shutdown(self) -> None:
        """Gracefully shut down scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("IngestionScheduler shut down.")

    async def execute_scheduled_job(self) -> dict[str, Any]:
        """Triggered automatically by cron schedule."""
        logger.info("Executing scheduled daily climate ingestion run...")
        return await self.trigger_now(is_scheduled=True)

    async def trigger_now(
        self,
        sources: list[str] | None = None,
        force_full_refresh: bool = False,
        is_scheduled: bool = False,
    ) -> dict[str, Any]:
        """Execute on-demand or scheduled ingestion cycle with concurrency guards."""
        if self._run_lock.locked():
            logger.warning("Ingestion job already in progress. Rejecting concurrent trigger.")
            return {
                "status": "BUSY",
                "message": "An ingestion cycle is already currently active.",
                "job_id": self._last_job_id,
            }

        async with self._run_lock:
            job_id = f"job_ingest_{uuid.uuid4().hex[:10]}"
            self._last_job_id = job_id
            self._is_running = True
            started_at = datetime.now(UTC).isoformat()
            self._last_run_started_at = started_at

            try:
                # Save initial job record in PostgreSQL
                await db_save_job(
                    job_id=job_id,
                    job_type="ingestion",
                    parameters={
                        "is_scheduled": is_scheduled,
                        "sources": sources
                        or ["noaa_oni", "noaa_nino34", "noaa_soi", "chirps_rainfall"],
                        "force_full_refresh": force_full_refresh,
                    },
                )

                result = await self.coordinator.run_ingestion_cycle(
                    job_id=job_id,
                    sources=sources,
                    force_full_refresh=force_full_refresh,
                )
                completed_at = datetime.now(UTC).isoformat()
                self._last_run_completed_at = completed_at
                self._last_run_status = result["status"]

                # Update job in PostgreSQL
                log_summary = (
                    f"[{completed_at}] Ingestion completed with status {result['status']}. "
                    f"Records added: {result['total_inserted']}, updated: {result['total_updated']}\n"
                )
                await db_update_job(
                    job_id=job_id,
                    status="completed" if "ERRORS" not in result["status"] else "failed",
                    result=result,
                    error_detail=None,
                    logs=log_summary,
                )

                # Update next run time
                job_def = self._scheduler.get_job("daily_climate_ingestion_job")
                if job_def and job_def.next_run_time:
                    self._next_fire_time_utc = job_def.next_run_time.isoformat()

                return {
                    "job_id": job_id,
                    "status": result["status"],
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "result": result,
                }

            except Exception as exc:
                completed_at = datetime.now(UTC).isoformat()
                self._last_run_completed_at = completed_at
                self._last_run_status = "FAILED"
                err_msg = f"Fatal error in ingestion cycle: {exc}"
                logger.error(err_msg, exc_info=True)

                await db_update_job(
                    job_id=job_id,
                    status="failed",
                    result=None,
                    error_detail=str(exc),
                    logs=f"[{completed_at}] ERROR: {exc}\n",
                )

                return {
                    "job_id": job_id,
                    "status": "FAILED",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "error": str(exc),
                }
            finally:
                self._is_running = False

    async def get_status(self) -> dict[str, Any]:
        """Return real-time scheduler state and historical context."""
        job_def = self._scheduler.get_job("daily_climate_ingestion_job")
        next_run = job_def.next_run_time.isoformat() if job_def and job_def.next_run_time else None

        last_job_detail = None
        if self._last_job_id:
            last_job_detail = await db_get_job(self._last_job_id)

        return {
            "scheduler_running": self._scheduler.running,
            "is_job_active": self._is_running,
            "cadence": "daily at 02:00 UTC",
            "next_scheduled_run_utc": next_run,
            "last_job_id": self._last_job_id,
            "last_run_started_at": self._last_run_started_at,
            "last_run_completed_at": self._last_run_completed_at,
            "last_run_status": self._last_run_status,
            "last_job": last_job_detail,
        }


def get_ingestion_scheduler() -> IngestionScheduler:
    """Singleton getter for IngestionScheduler."""
    global _SCHEDULER_INSTANCE
    if _SCHEDULER_INSTANCE is None:
        _SCHEDULER_INSTANCE = IngestionScheduler()
    return _SCHEDULER_INSTANCE
