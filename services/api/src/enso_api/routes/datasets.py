"""Datasets, ingestion, and provenance API router."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from enso_api.jobs import JobConflictError, submit_job

router = APIRouter(prefix="/api/v1", tags=["datasets"])


class IngestionJobRequest(BaseModel):
    use_fixtures: bool = Field(
        default=True,
        description=(
            "Whether to use deterministic offline fixtures (True) or process raw downloads."
        ),
    )
    sources: list[str] | None = Field(
        default=None,
        description="Optional subset of sources: 'chirps_rainfall', 'noaa_oni', 'noaa_nino34'.",
    )


class JobSubmissionResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    message: str
    started_at: str


def _inspect_dataset_file(path: Path, source_name: str, tier: str) -> dict[str, Any]:
    """Inspect local dataset file metadata safely."""
    if not path.is_file():
        return {
            "source": source_name,
            "tier": tier,
            "file_name": path.name,
            "exists": False,
            "byte_size": 0,
            "record_count": 0,
            "last_modified": None,
            "is_fixture": "fixture" in str(path).lower(),
        }

    try:
        stat = path.stat()
        byte_size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()

        # Count non-empty rows without loading whole file
        row_count = 0
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip():
                    row_count += 1
        # Subtract header if present
        if row_count > 0:
            row_count -= 1

        return {
            "source": source_name,
            "tier": tier,
            "file_name": path.name,
            "file_path": str(path),
            "exists": True,
            "byte_size": byte_size,
            "record_count": row_count,
            "last_modified": last_modified,
            "is_fixture": "fixture" in str(path).lower() or byte_size < 10_000,
        }
    except Exception as exc:
        return {
            "source": source_name,
            "tier": tier,
            "file_name": path.name,
            "exists": True,
            "error": str(exc),
        }


@router.get("/datasets")
def list_datasets() -> dict[str, Any]:
    """Inspect dataset availability across raw, cleaned, and derived storage tiers."""
    datasets: list[dict[str, Any]] = [
        _inspect_dataset_file(Path("data/raw/chirps_sample.csv"), "chirps_rainfall", "raw"),
        _inspect_dataset_file(
            Path("data/cleaned/chirps_rainfall_monthly.csv")
            if Path("data/cleaned/chirps_rainfall_monthly.csv").is_file()
            else Path("data/cleaned/chirps_rainfall_cleaned.csv"),
            "chirps_rainfall",
            "cleaned",
        ),
        _inspect_dataset_file(Path("data/raw/oni_sample.txt"), "noaa_oni", "raw"),
        _inspect_dataset_file(
            Path("data/cleaned/noaa_oni_monthly.csv")
            if Path("data/cleaned/noaa_oni_monthly.csv").is_file()
            else Path("data/cleaned/noaa_oni_cleaned.csv"),
            "noaa_oni",
            "cleaned",
        ),
        _inspect_dataset_file(Path("data/raw/nino34_sample.txt"), "noaa_nino34", "raw"),
        _inspect_dataset_file(
            Path("data/cleaned/noaa_nino34_monthly.csv")
            if Path("data/cleaned/noaa_nino34_monthly.csv").is_file()
            else Path("data/cleaned/noaa_nino34_cleaned.csv"),
            "noaa_nino34",
            "cleaned",
        ),
        _inspect_dataset_file(
            Path("data/derived/enso_rainfall_seasonal_analysis.csv"),
            "seasonal_analysis_matrix",
            "derived",
        ),
    ]

    return {
        "datasets": datasets,
        "total_datasets": len(datasets),
        "cleaned_operational": all(d["exists"] for d in datasets if d["tier"] == "cleaned"),
    }


@router.get("/datasets/timeseries")
def get_dataset_timeseries() -> dict[str, Any]:
    """Retrieve actual historical time series for rainfall, ONI index, and seasonal aggregates."""
    rainfall_path = Path("data/cleaned/chirps_rainfall_monthly.csv")
    oni_path = Path("data/cleaned/noaa_oni_monthly.csv")
    features_path = Path("data/features/enso_rainfall_features_labelled.csv")
    ref_dist_path = Path("data/features/climatology_reference_distribution.json")

    rainfall_series: list[dict[str, Any]] = []
    if rainfall_path.is_file():
        with contextlib.suppress(Exception), open(rainfall_path, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            date_idx = header.index("date") if "date" in header else 2
            precip_idx = header.index("precip_mm") if "precip_mm" in header else 3
            for line in f:
                parts = line.strip().split(",")
                if len(parts) > precip_idx:
                    with contextlib.suppress(ValueError):
                        rainfall_series.append(
                            {
                                "date": parts[date_idx],
                                "precip_mm": float(parts[precip_idx]),
                            }
                        )

    oni_series: list[dict[str, Any]] = []
    if oni_path.is_file():
        with contextlib.suppress(Exception), open(oni_path, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            date_idx = header.index("date") if "date" in header else 2
            anom_idx = header.index("oni_anomaly_degc") if "oni_anomaly_degc" in header else 4
            for line in f:
                parts = line.strip().split(",")
                if len(parts) > anom_idx:
                    with contextlib.suppress(ValueError):
                        oni_series.append(
                            {
                                "date": parts[date_idx],
                                "oni_anomaly_degc": float(parts[anom_idx]),
                            }
                        )

    seasonal_series: list[dict[str, Any]] = []
    if features_path.is_file():
        with contextlib.suppress(Exception), open(features_path, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
            yr_idx = header.index("season_year") if "season_year" in header else 0
            p_col = "seasonal_precip_djf_mm"
            p_idx = header.index(p_col) if p_col in header else -1
            oni_idx = header.index("oni_aso_degc") if "oni_aso_degc" in header else -1
            d_col = "target_drought_p20"
            drought_idx = header.index(d_col) if d_col in header else -1
            z_idx = header.index("precip_oct_zscore") if "precip_oct_zscore" in header else -1

            for line in f:
                parts = line.strip().split(",")
                if len(parts) > yr_idx and parts[yr_idx].isdigit():
                    rec: dict[str, Any] = {"season_year": int(parts[yr_idx])}
                    if p_idx >= 0 and len(parts) > p_idx:
                        with contextlib.suppress(ValueError):
                            rec["seasonal_precip_djf_mm"] = float(parts[p_idx])
                    if oni_idx >= 0 and len(parts) > oni_idx:
                        with contextlib.suppress(ValueError):
                            rec["oni_aso_degc"] = float(parts[oni_idx])
                    if drought_idx >= 0 and len(parts) > drought_idx:
                        with contextlib.suppress(ValueError):
                            rec["target_drought_p20"] = int(parts[drought_idx])
                    if z_idx >= 0 and len(parts) > z_idx:
                        with contextlib.suppress(ValueError):
                            rec["precip_oct_zscore"] = float(parts[z_idx])
                    seasonal_series.append(rec)

    ref_dist: dict[str, Any] = {}
    if ref_dist_path.is_file():
        with contextlib.suppress(Exception), open(ref_dist_path, encoding="utf-8") as f:
            ref_dist = json.load(f)

    return {
        "region_id": "ZA_SRZ",
        "region_name": "Limpopo and South African Maize Belt Summer Rainfall Zone",
        "rainfall_monthly": rainfall_series,
        "oni_monthly": oni_series,
        "seasonal_history": seasonal_series,
        "reference_distribution": ref_dist,
        "coverage": {
            "rainfall_months": len(rainfall_series),
            "oni_months": len(oni_series),
            "seasonal_seasons": len(seasonal_series),
            "start_year": 1981,
            "end_year": 1988,
            "missing_periods": [],
            "is_fixture_coverage": True,
        },
    }


class VerifyArtefactRequest(BaseModel):
    dataset_id: str | None = Field(
        default=None, description="Dataset identifier (e.g. 'chirps_rainfall')"
    )
    file_path: str | None = Field(default=None, description="Explicit file path to verify on disk")


@router.get("/provenance/datasets")
async def list_provenance_records() -> dict[str, Any]:
    """Inspect cryptographic provenance records, signatures, and processing history."""
    from enso_api.db import db_save_provenance_record

    provenance_dir = Path("data/provenance")
    records: list[dict[str, Any]] = []

    if provenance_dir.is_dir():
        for p_file in sorted(provenance_dir.glob("*.json")):
            with contextlib.suppress(Exception), open(p_file, encoding="utf-8") as f:
                manifest = json.load(f)
                records.append(manifest)
                # Background sync to PostgreSQL provenance ledger if DB is active
                ds_id = manifest.get("dataset_id") or p_file.stem
                digest = manifest.get("content_digest") or manifest.get("cleaned_sha256") or ""
                if ds_id and digest:
                    clean_file = Path("data/cleaned") / f"{ds_id}_monthly.csv"
                    b_size = clean_file.stat().st_size if clean_file.is_file() else 0
                    with contextlib.suppress(Exception):
                        await db_save_provenance_record(
                            artifact_id=ds_id,
                            artifact_name=manifest.get("source_name") or ds_id,
                            sha256_hash=digest,
                            source_url=manifest.get("source_url"),
                            byte_size=b_size,
                            metadata=manifest,
                        )

    return {
        "records": records,
        "count": len(records),
        "provenance_dir": str(provenance_dir),
    }


@router.get("/provenance/audit")
def get_provenance_audit() -> dict[str, Any]:
    """Execute real-time cryptographic integrity, authenticity, and freshness audit."""
    from ml.data.provenance.auditor import ProvenanceAuditor

    auditor = ProvenanceAuditor()
    report = auditor.audit_repository()
    return report.model_dump()


@router.post("/provenance/verify")
def verify_artefact_endpoint(request: VerifyArtefactRequest) -> dict[str, Any]:
    """Verify cryptographic integrity, authenticity, and validity of a single artefact."""
    from ml.data.provenance.auditor import ProvenanceAuditor
    from ml.data.provenance.tracker import ProvenanceTracker

    if not request.dataset_id and not request.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'dataset_id' or 'file_path' must be provided for verification.",
        )

    auditor = ProvenanceAuditor()
    provenance_dir = Path("data/provenance")

    # Locate manifest
    manifest: Any = None
    if request.dataset_id:
        candidate = provenance_dir / f"{request.dataset_id}_provenance.json"
        if candidate.is_file():
            manifest = ProvenanceTracker.load_manifest(candidate)

    if manifest is None and request.file_path:
        stem = Path(request.file_path).stem.replace("_monthly", "").replace("_cleaned", "")
        candidate = provenance_dir / f"{stem}_provenance.json"
        if candidate.is_file():
            manifest = ProvenanceTracker.load_manifest(candidate)

    if manifest is None:
        target_name = request.dataset_id or request.file_path
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance manifest not found for dataset '{target_name}'.",
        )

    res = auditor.audit_artefact(manifest, target_path=request.file_path)
    return res.model_dump()


@router.post(
    "/ingestion/jobs",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_ingestion_job(
    request: IngestionJobRequest,
) -> JobSubmissionResponse:
    """Launch asynchronous climate data ingestion pipeline."""
    try:
        job = await submit_job("ingestion", request.model_dump())
        return JobSubmissionResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            message="Climate data ingestion job submitted and running in background.",
            started_at=job.started_at,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
