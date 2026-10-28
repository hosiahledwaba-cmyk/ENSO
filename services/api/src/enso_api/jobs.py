"""Asynchronous background job orchestration for climate data pipelines, training, and experiments.

Ensures long-running ML workloads do not block HTTP requests, prevents overlapping
conflicts on shared dataset paths, and persists execution logs and status into PostgreSQL.
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from enso_api.db import db_get_job, db_list_jobs, db_save_job, db_update_job

logger = logging.getLogger("enso_api.jobs")

JobType = Literal["ingestion", "features", "training", "experiment"]
JobStatus = Literal["pending", "running", "completed", "failed"]

# Global locks per job type to prevent race conditions on shared files
_JOB_TYPE_LOCKS: dict[str, asyncio.Lock] = {
    "ingestion": asyncio.Lock(),
    "features": asyncio.Lock(),
    "training": asyncio.Lock(),
    "experiment": asyncio.Lock(),
}

# Retain references to background tasks to prevent premature garbage collection
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


@dataclass
class JobRecord:
    job_id: str
    job_type: JobType
    status: JobStatus
    parameters: dict[str, Any]
    result: dict[str, Any] | None = None
    error_detail: str | None = None
    logs: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "parameters": self.parameters,
            "result": self.result,
            "error_detail": self.error_detail,
            "logs": self.logs,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# In-memory store for fast retrieval and real-time log capturing
_IN_MEMORY_JOBS: dict[str, JobRecord] = {}


class JobConflictError(Exception):
    """Raised when a job of the same type is already running."""


def get_job(job_id: str) -> JobRecord | None:
    """Retrieve job from in-memory cache."""
    return _IN_MEMORY_JOBS.get(job_id)


async def get_job_async(job_id: str) -> dict[str, Any] | None:
    """Retrieve job by ID, checking memory first and falling back to database."""
    if job_id in _IN_MEMORY_JOBS:
        return _IN_MEMORY_JOBS[job_id].to_dict()
    db_record = await db_get_job(job_id)
    return db_record


async def list_jobs_async(limit: int = 50) -> list[dict[str, Any]]:
    """List recent jobs combining in-memory records and database history."""
    db_records = await db_list_jobs(limit=limit)
    db_ids = {r["job_id"] for r in db_records}

    # Add any active in-memory jobs not yet in the DB list
    combined: list[dict[str, Any]] = []
    for job in sorted(_IN_MEMORY_JOBS.values(), key=lambda j: j.started_at, reverse=True):
        if job.job_id not in db_ids:
            combined.append(job.to_dict())

    combined.extend(db_records)
    return combined[:limit]


def is_job_type_running(job_type: str) -> bool:
    """Check if any job of the given type is currently active."""
    return any(
        j.job_type == job_type and j.status in ("pending", "running")
        for j in _IN_MEMORY_JOBS.values()
    )


# ---------------------------------------------------------------------------
# Synchronous Pipeline Worker Wrappers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Synchronous Pipeline Worker Wrappers
# ---------------------------------------------------------------------------


def _run_ingestion_sync(parameters: dict[str, Any]) -> dict[str, Any]:
    """Execute climate data ingestion pipeline synchronously."""
    from ml.data.cli import setup_fixtures_in_raw
    from ml.data.pipeline import IngestionPipeline

    use_fixtures = bool(parameters.get("use_fixtures", True))
    raw_dir = Path(parameters.get("raw_dir", "data/raw"))
    cleaned_dir = Path(parameters.get("cleaned_dir", "data/cleaned"))
    derived_dir = Path(parameters.get("derived_dir", "data/derived"))
    manifest_dir = Path(parameters.get("manifest_dir", "data/provenance"))

    for d in (raw_dir, cleaned_dir, derived_dir, manifest_dir):
        d.mkdir(parents=True, exist_ok=True)

    if use_fixtures:
        raw_files = setup_fixtures_in_raw(raw_dir)
    else:
        raw_files = {}
        for f in raw_dir.glob("*"):
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if "chirps" in name_lower or "rain" in name_lower or "precip" in name_lower:
                raw_files["chirps_rainfall"] = f
            elif "oni" in name_lower:
                raw_files["noaa_oni"] = f
            elif "nino" in name_lower or "sst" in name_lower:
                raw_files["noaa_nino34"] = f

    if not raw_files:
        raise ValueError(
            f"No source files found in {raw_dir}. "
            f"Use use_fixtures=true or place files in {raw_dir}."
        )

    pipeline = IngestionPipeline()
    results = []
    for source_id, raw_f in raw_files.items():
        cleaned_df, manifest = pipeline.ingest_dataset(source_id, raw_f, cleaned_dir, manifest_dir)
        results.append(
            {
                "source": source_id,
                "records": len(cleaned_df),
                "sha256": manifest.cleaned_sha256,
                "raw_sha256": manifest.raw_sha256,
            }
        )

    # Build derived seasonal dataset if all 3 sources ingested
    derived_built = False
    chirps_f = cleaned_dir / "chirps_rainfall_monthly.csv"
    oni_f = cleaned_dir / "noaa_oni_monthly.csv"
    nino34_f = cleaned_dir / "noaa_nino34_monthly.csv"
    if chirps_f.is_file() and oni_f.is_file() and nino34_f.is_file():
        _derived_df, _ = pipeline.build_derived_seasonal_dataset(
            cleaned_dir, derived_dir, manifest_dir
        )
        derived_built = True

    return {
        "status": "success",
        "use_fixtures": use_fixtures,
        "datasets_processed": len(results),
        "results": results,
        "derived_built": derived_built,
    }


def _run_features_sync(parameters: dict[str, Any]) -> dict[str, Any]:
    """Execute feature generation pipeline synchronously."""
    from ml.features.pipeline import FeaturePipeline

    cleaned_dir = Path(parameters.get("cleaned_dir", "data/cleaned"))
    output_dir = Path(parameters.get("output_dir", "data/features"))
    manifest_dir = Path(parameters.get("manifest_dir", "data/provenance"))
    include_lag1 = bool(parameters.get("include_lag1", False))

    pipeline = FeaturePipeline()
    df_labelled, ref_dist, manifest = pipeline.run(
        cleaned_dir=cleaned_dir,
        output_dir=output_dir,
        manifest_dir=manifest_dir,
        include_lag1=include_lag1,
    )

    non_feature_cols = {
        "season_year",
        "split",
        "target_drought_p20",
        "target_drought_p33",
        "target_rainfall_djf_mm",
    }
    feature_cols = [c for c in df_labelled.columns if c not in non_feature_cols]

    return {
        "status": "success",
        "features_csv": str(output_dir / "enso_rainfall_features_labelled.csv"),
        "row_count": len(df_labelled),
        "feature_count": len(feature_cols),
        "feature_columns": feature_cols,
        "training_seasons": sorted(
            int(y) for y in df_labelled[df_labelled["split"] == "train"]["season_year"].tolist()
        ),
        "holdout_seasons": sorted(
            int(y) for y in df_labelled[df_labelled["split"] == "test"]["season_year"].tolist()
        ),
        "fingerprint_sha256": manifest.cleaned_sha256 or manifest.dataset_id,
        "distribution": {
            "mean": ref_dist.mean_seasonal_precip_mm,
            "std": ref_dist.std_seasonal_precip_mm,
            "p20": ref_dist.tau_drought_p20_mm,
            "p33": ref_dist.tau_below_normal_p33_mm,
        },
    }


def _run_training_sync(parameters: dict[str, Any]) -> dict[str, Any]:
    """Execute baseline model training pipeline synchronously."""
    from ml.training.config import TrainingConfig
    from ml.training.experiment import ClimateModelExperiment

    features_csv = Path(
        parameters.get("features_csv", "data/features/enso_rainfall_features_labelled.csv")
    )
    model_dir = Path(parameters.get("model_dir", "models/logistic_regression_baseline"))
    holdout_count = int(parameters.get("holdout_count", 2))
    seed = int(parameters.get("seed", 42))

    cfg = TrainingConfig(random_seed=seed)
    experiment = ClimateModelExperiment(config=cfg)
    _, _, manifest = experiment.run(
        features_csv_path=features_csv,
        output_model_dir=model_dir,
        holdout_seasons_count=holdout_count,
    )

    baseline_bs = (
        manifest.baseline_holdout_metrics.brier_score
        if manifest.baseline_holdout_metrics
        else 0.0
    )
    logistic_bs = manifest.holdout_metrics.brier_score if manifest.holdout_metrics else 0.0
    bss = manifest.holdout_bss or 0.0

    return {
        "status": "success",
        "model_dir": str(model_dir),
        "manifest_path": str(model_dir / "model_manifest.json"),
        "dataset_hash": manifest.dataset_sha256,
        "training_seasons": manifest.training_seasons,
        "holdout_seasons": manifest.holdout_seasons,
        "baseline_brier_score": baseline_bs,
        "logistic_brier_score": logistic_bs,
        "brier_skill_score": bss,
        "holdout_superiority_confirmed": manifest.beats_baseline_on_holdout,
    }


def _run_experiment_sync(parameters: dict[str, Any]) -> dict[str, Any]:
    """Execute multi-model comparison experiment synchronously."""
    from ml.experiments.comparison import MultiModelExperimentRunner
    from ml.training.config import TrainingConfig

    features_csv = Path(
        parameters.get("features_csv", "data/features/enso_rainfall_features_labelled.csv")
    )
    output_dir = Path(parameters.get("output_dir", "reports/experiments/nonlinear_comparison"))
    seed = int(parameters.get("seed", 42))
    holdout_count = int(parameters.get("holdout_count", 2))

    cfg = TrainingConfig(random_seed=seed)
    runner = MultiModelExperimentRunner(config=cfg)
    manifest = runner.run(
        features_csv_path=features_csv,
        output_dir=output_dir,
        holdout_count=holdout_count,
    )

    return {
        "status": "success",
        "output_dir": str(output_dir),
        "experiment_id": manifest.experiment_id,
        "seed": manifest.random_seed,
        "cv_brier_logistic": manifest.rolling_origin_cv["logistic_regression"].brier_score,
        "cv_brier_xgboost": manifest.rolling_origin_cv["xgboost"].brier_score,
        "holdout_brier_baseline": manifest.holdout_evaluation["climatology_baseline"].brier_score,
        "holdout_brier_logistic": manifest.holdout_evaluation["logistic_regression"].brier_score,
        "holdout_brier_xgboost": manifest.holdout_evaluation["xgboost"].brier_score,
        "complexity_justified": manifest.verdict.is_nonlinear_complexity_justified,
        "verdict_rationale": manifest.verdict.justification_rationale,
    }


_WORKER_ROUTING: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "ingestion": _run_ingestion_sync,
    "features": _run_features_sync,
    "training": _run_training_sync,
    "experiment": _run_experiment_sync,
}


# ---------------------------------------------------------------------------
# Background Task Execution with Log Capture
# ---------------------------------------------------------------------------


async def _execute_job_task(job: JobRecord) -> None:
    """Run worker in a thread while capturing stdout/stderr into the job's log."""
    lock = _JOB_TYPE_LOCKS[job.job_type]
    async with lock:
        job.status = "running"
        await db_save_job(job.job_id, job.job_type, job.parameters)

        worker = _WORKER_ROUTING.get(job.job_type)
        if worker is None:
            job.status = "failed"
            job.error_detail = f"Unsupported job type: {job.job_type}"
            job.completed_at = datetime.now(UTC).isoformat()
            await db_update_job(job.job_id, job.status, None, job.error_detail, job.logs)
            return

        log_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        try:
            # Capture print and logger statements during execution
            sys.stdout = log_capture
            sys.stderr = log_capture

            now_str = datetime.now(UTC).isoformat()
            print(f"[{now_str}] Starting {job.job_type} job (ID: {job.job_id})")
            print(f"Parameters: {job.parameters}\n---")

            # Execute synchronous heavy calculation in worker thread
            result = await asyncio.to_thread(worker, job.parameters)

            finish_str = datetime.now(UTC).isoformat()
            print(f"---\n[{finish_str}] {job.job_type.capitalize()} job completed successfully.")
            job.status = "completed"
            job.result = result
            job.error_detail = None
        except Exception as exc:
            traceback.print_exc(file=log_capture)
            job.status = "failed"
            job.error_detail = str(exc)
            job.result = None
            err_str = datetime.now(UTC).isoformat()
            print(f"---\n[{err_str}] {job.job_type.capitalize()} job FAILED: {exc}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            job.logs = log_capture.getvalue()
            job.completed_at = datetime.now(UTC).isoformat()
            await db_update_job(job.job_id, job.status, job.result, job.error_detail, job.logs)


async def submit_job(job_type: JobType, parameters: dict[str, Any]) -> JobRecord:
    """Submit a new background job with concurrency checks."""
    if is_job_type_running(job_type):
        raise JobConflictError(
            f"A '{job_type}' job is already currently running. Please wait for it to complete."
        )

    job_id = f"job_{job_type}_{uuid.uuid4().hex[:10]}"
    job = JobRecord(
        job_id=job_id,
        job_type=job_type,
        status="pending",
        parameters=parameters,
    )
    _IN_MEMORY_JOBS[job_id] = job

    # Launch task in background and retain strong reference
    task = asyncio.create_task(_execute_job_task(job))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return job
