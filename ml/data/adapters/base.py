"""Extensible base adapter interface for climate and oceanographic datasets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ml.data.provenance.crypto import compute_sha256
from ml.data.provenance.tracker import ProvenanceTracker
from ml.data.validation.models import (
    ProcessingStep,
    ProvenanceManifest,
    SpatialBounds,
    ValidationReport,
)


class BaseDatasetAdapter(ABC):
    """Abstract interface for dataset adapters."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier (e.g. 'chirps_rainfall', 'noaa_oni')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Dataset release/version tag."""

    @property
    @abstractmethod
    def licence(self) -> str:
        """Licensing terms."""

    @property
    @abstractmethod
    def citation(self) -> str:
        """Standard scientific reference citation."""

    @property
    def source_url(self) -> str | None:
        """Public download URL or upstream data repository."""
        return None

    @property
    @abstractmethod
    def expected_units(self) -> dict[str, str]:
        """Expected units dictionary mapping column names to physical units."""

    @property
    def spatial_bounds(self) -> SpatialBounds | None:
        """Spatial bounding coordinates if dataset has geographic extent."""
        return None

    @property
    def staleness_threshold_days(self) -> int:
        """Expected maximum update interval before data is considered stale."""
        return 60

    @abstractmethod
    def load_raw(self, raw_path: Path | str) -> pd.DataFrame:
        """Parse raw file format into pandas DataFrame without modifying original files."""

    @abstractmethod
    def validate(self, raw_df: pd.DataFrame) -> ValidationReport:
        """Execute strict schema, physical range, missingness, and timestamp validations."""

    @abstractmethod
    def clean(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Produce standardized DataFrame with canonical column names and sorted timestamps."""

    def ingest(
        self,
        raw_path: Path | str,
        cleaned_path: Path | str,
        manifest_path: Path | str | None = None,
        is_archival_benchmark: bool = True,
    ) -> tuple[pd.DataFrame, ValidationReport, ProvenanceManifest]:
        """Execute end-to-end ingestion: load -> validate -> clean -> record signed provenance."""
        raw_p = Path(raw_path)
        clean_p = Path(cleaned_path)

        if not raw_p.is_file():
            raise FileNotFoundError(f"Raw dataset file not found: {raw_p}")

        # Compute raw file digest and timestamp to preserve original artefact state
        raw_sha256 = compute_sha256(raw_p)
        raw_mtime = raw_p.stat().st_mtime
        source_timestamp_utc = datetime.fromtimestamp(raw_mtime, UTC).isoformat()

        # Step 1: Raw Acquisition (Unsigned third-party external data)
        step_raw = ProcessingStep(
            step_name="raw_acquisition",
            timestamp_utc=source_timestamp_utc,
            operator=f"{self.source_id}_adapter:{self.version}",
            input_digests={},
            output_digest=raw_sha256,
            parameters={
                "source_url": self.source_url or "LOCAL_UPLOAD",
                "licence": self.licence,
                "note": (
                    "Unsigned third-party observational data. Hash recorded for "
                    "post-ingestion tamper detection."
                ),
            },
        )

        # 1. Parse raw data
        raw_df = self.load_raw(raw_p)

        # 2. Strict validation
        report = self.validate(raw_df)
        if not report.is_valid:
            error_details = "; ".join(report.errors)
            raise ValueError(f"Dataset validation failed for {self.source_id}: {error_details}")

        # 3. Clean and standardize
        cleaned_df = self.clean(raw_df)

        # 4. Save cleaned data (never overwrite raw data)
        clean_p.parent.mkdir(parents=True, exist_ok=True)
        cleaned_df.to_csv(clean_p, index=False)
        cleaned_sha256 = compute_sha256(clean_p)

        # Step 2: Validation and Standardization
        step_clean = ProcessingStep(
            step_name="validation_and_cleaning",
            timestamp_utc=datetime.now(UTC).isoformat(),
            operator=f"{self.source_id}_adapter:{self.version}",
            input_digests={"raw_artefact": raw_sha256},
            output_digest=cleaned_sha256,
            parameters={
                "expected_units": self.expected_units,
                "records_cleaned": len(cleaned_df),
                "checks_passed": len([c for c in report.checks if c.passed]),
            },
        )

        # 5. Build and cryptographically sign provenance manifest for controlled pipeline artefact
        date_min = f"{cleaned_df['year'].min()}-{int(cleaned_df['month'].min()):02d}"
        date_max = f"{cleaned_df['year'].max()}-{int(cleaned_df['month'].max()):02d}"

        manifest = ProvenanceTracker.create_manifest(
            dataset_id=self.source_id,
            source_identifier=self.source_id,
            source_name=self.name,
            source_version=self.version,
            dataset_version=self.version,
            source_url=self.source_url,
            source_timestamp_utc=source_timestamp_utc,
            licence=self.licence,
            citation=self.citation,
            raw_filepath=raw_p,
            cleaned_filepath=clean_p,
            record_count=len(cleaned_df),
            date_range={"start": date_min, "end": date_max},
            units=self.expected_units,
            spatial_bounds=self.spatial_bounds,
            validation_status="PASSED",
            validation_outcome=report.to_outcome_dict(),
            processing_history=[step_raw, step_clean],
            is_controlled_pipeline=True,
            staleness_threshold_days=self.staleness_threshold_days,
            is_archival_benchmark=is_archival_benchmark,
        )

        if manifest_path is not None:
            ProvenanceTracker.save_manifest(manifest, manifest_path)

        return cleaned_df, report, manifest
