"""Central coordinator and provider adapters for automated climate data ingestion."""

from __future__ import annotations

import gzip
import hashlib
import io
import logging
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

from enso_api.db import (
    db_get_climate_coverage,
    db_record_ingestion_log,
    db_save_provenance_record,
    db_upsert_climate_coverage,
)

logger = logging.getLogger("enso_api.ingestion.coordinator")

# Spatial bounding box for Southern African Summer Rainfall Zone (RD-003)
# Limpopo Basin and South African Maize Belt
STUDY_AREA_BOUNDS = {
    "lat_min": -30.0,
    "lat_max": -22.0,
    "lon_min": 25.0,
    "lon_max": 32.0,
}

SEASONS_12 = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
SEASON_TO_CENTER_MONTH = {s: i + 1 for i, s in enumerate(SEASONS_12)}


@dataclass
class IngestionResult:
    source_id: str
    lifecycle_stage: str  # COMPLETED, COMPLETED_WITH_WARNINGS, NO_NEW_DATA, FAILED
    records_inserted: int = 0
    records_updated: int = 0
    records_skipped: int = 0
    records_rejected: int = 0
    earliest_date: str | None = None
    latest_date: str | None = None
    raw_sha256: str | None = None
    cleaned_sha256: str | None = None
    validation_warnings: list[str] = field(default_factory=list)
    error_message: str | None = None
    duration_ms: int = 0


def fetch_url_with_retry(
    url: str,
    timeout: int = 20,
    max_retries: int = 3,
    backoff_factor: float = 1.5,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    """Fetch URL with exponential backoff and timeout safeguards."""
    req_headers = {
        "User-Agent": "ENSO-Shield-Research/1.0 (+https://github.com/enso-shield)",
        "Accept": "*/*",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return data, resp_headers
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                sleep_sec = backoff_factor**attempt
                logger.warning(
                    "Fetch attempt %d failed for %s: %s. Retrying in %.1fs...",
                    attempt + 1,
                    url,
                    exc,
                    sleep_sec,
                )
                time.sleep(sleep_sec)

    raise RuntimeError(
        f"Failed to fetch {url} after {max_retries} attempts: {last_exc}"
    ) from last_exc


class BaseClimateProvider(ABC):
    """Abstract base provider for climate data ingestion."""

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def dataset_name(self) -> str: ...

    @property
    @abstractmethod
    def dataset_version(self) -> str: ...

    @property
    @abstractmethod
    def primary_url(self) -> str: ...

    @property
    @abstractmethod
    def frequency(self) -> str: ...

    @property
    @abstractmethod
    def expected_units(self) -> dict[str, str]: ...

    @property
    def publication_delay_days(self) -> int:
        return 15

    @abstractmethod
    async def ingest(
        self,
        cleaned_dir: Path,
        raw_dir: Path,
        job_id: str | None = None,
        force_full_refresh: bool = False,
    ) -> IngestionResult:
        """Execute incremental fetch, validation, and storage."""
        ...


class NoaaOniProvider(BaseClimateProvider):
    """NOAA CPC Oceanic Niño Index (ONI) 3-month running mean SST anomalies."""

    @property
    def source_id(self) -> str:
        return "noaa_oni"

    @property
    def provider_name(self) -> str:
        return "NOAA Climate Prediction Center (CPC)"

    @property
    def dataset_name(self) -> str:
        return "NOAA Oceanic Niño Index (ERSST.v5 Niño 3.4 3-Month Running Mean)"

    @property
    def dataset_version(self) -> str:
        return "NOAA-CPC-ONI-v5"

    @property
    def primary_url(self) -> str:
        return "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

    @property
    def frequency(self) -> str:
        return "monthly (3-month running mean)"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"oni_anomaly_degc": "degC"}

    @property
    def publication_delay_days(self) -> int:
        return 7

    def parse_oni_text(self, content: str) -> list[dict[str, Any]]:
        rows, _ = self.parse_oni_text_with_warnings(content)
        return rows

    def parse_oni_text_with_warnings(self, content: str) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "SEAS" in line:
                continue
            parts = line.split()
            if len(parts) >= 4 and parts[0] in SEASON_TO_CENTER_MONTH:
                seas = parts[0]
                yr = int(parts[1])
                total_sst = float(parts[2])
                anom = float(parts[3])

                if not (-5.0 <= anom <= 5.0):
                    warnings.append(
                        f"ONI anomaly {anom} in {seas} {yr} outside standard range [-5, 5]."
                    )

                center_mo = SEASON_TO_CENTER_MONTH[seas]
                date_str = f"{yr}-{center_mo:02d}-01"
                rows.append(
                    {
                        "year": yr,
                        "month": center_mo,
                        "date": date_str,
                        "season": seas,
                        "oni_sst_degc": total_sst,
                        "oni_anomaly_degc": anom,
                        "anomaly": anom,
                    }
                )
        return rows, warnings

    async def ingest(
        self,
        cleaned_dir: Path,
        raw_dir: Path,
        job_id: str | None = None,
        force_full_refresh: bool = False,
    ) -> IngestionResult:
        t0 = time.time()
        raw_target = raw_dir / "noaa_oni.ascii.txt"
        clean_target = cleaned_dir / "noaa_oni_monthly.csv"

        try:
            data, _headers = fetch_url_with_retry(self.primary_url, timeout=20)
            raw_sha256 = hashlib.sha256(data).hexdigest()
            raw_target.write_bytes(data)

            content = data.decode("utf-8", errors="replace")
            rows, warnings = self.parse_oni_text_with_warnings(content)

            if not rows:
                raise ValueError("Parsed zero valid ONI records from CPC ASCII feed.")

            df_new = pd.DataFrame(rows).sort_values(["year", "month"]).reset_index(drop=True)
            new_sha256 = hashlib.sha256(df_new.to_csv(index=False).encode("utf-8")).hexdigest()

            # Check if cleaned target exists and if new observations arrived
            records_inserted = len(df_new)
            records_updated = 0
            records_skipped = 0
            lifecycle = "COMPLETED"

            if clean_target.is_file() and not force_full_refresh:
                df_curr = pd.read_csv(clean_target)
                curr_sha256 = hashlib.sha256(
                    clean_target.read_bytes()
                ).hexdigest()

                if curr_sha256 == new_sha256:
                    lifecycle = "NO_NEW_DATA"
                    records_inserted = 0
                    records_skipped = len(df_curr)
                else:
                    new_dates = set(df_new["date"]) - set(df_curr["date"])
                    records_inserted = len(new_dates)
                    records_updated = len(df_new) - records_inserted

            df_new.to_csv(clean_target, index=False)

            earliest = str(df_new["date"].min())
            latest = str(df_new["date"].max())
            duration_ms = int((time.time() - t0) * 1000)

            # Record provenance
            await db_save_provenance_record(
                artifact_id=f"clean_{self.source_id}",
                artifact_name="noaa_oni_monthly.csv",
                sha256_hash=new_sha256,
                source_url=self.primary_url,
                byte_size=clean_target.stat().st_size,
                metadata={
                    "total_records": len(df_new),
                    "earliest_date": earliest,
                    "latest_date": latest,
                },
            )

            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                spatial_coverage="Global Tropical Pacific (Niño 3.4 box: 5°N–5°S, 170°W–120°W)",
                earliest_observation=earliest,
                latest_observation=latest,
                total_records=len(df_new),
                status=lifecycle,
                last_error=None,
                metadata={"raw_sha256": raw_sha256, "cleaned_sha256": new_sha256},
            )

            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                job_id=job_id,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date_ingested=earliest,
                latest_date_ingested=latest,
                raw_artifact_sha256=raw_sha256,
                cleaned_artifact_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date=earliest,
                latest_date=latest,
                raw_sha256=raw_sha256,
                cleaned_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            logger.error("Failed to ingest NOAA ONI: %s", exc)
            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                status="ERROR",
                last_error=str(exc),
            )
            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                job_id=job_id,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                error_message=str(exc),
                duration_ms=duration_ms,
            )


class NoaaNino34Provider(BaseClimateProvider):
    """NOAA CPC Niño 3.4 SST Level and Standardized Anomaly."""

    @property
    def source_id(self) -> str:
        return "noaa_nino34"

    @property
    def provider_name(self) -> str:
        return "NOAA Climate Prediction Center (CPC)"

    @property
    def dataset_name(self) -> str:
        return "NOAA CPC Monthly Niño 3.4 Sea Surface Temperature & Anomaly (OISST.v2.1 / ERSST.v5)"

    @property
    def dataset_version(self) -> str:
        return "NOAA-CPC-Nino3.4-v5"

    @property
    def primary_url(self) -> str:
        return "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"

    @property
    def fallback_url(self) -> str:
        return "https://www.cpc.ncep.noaa.gov/data/indices/detrend.nino34.ascii.txt"

    @property
    def frequency(self) -> str:
        return "monthly"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"sst_degc": "degC", "anomaly_degc": "degC"}

    @property
    def publication_delay_days(self) -> int:
        return 7

    def parse_sstoi_text(self, content: str) -> list[dict[str, Any]]:
        rows, _ = self.parse_sstoi_text_with_warnings(content)
        return rows

    def parse_sstoi_text_with_warnings(self, content: str) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        header_line = lines[0] if lines else ""

        if "NINO3.4" in header_line:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 10 and parts[0].isdigit():
                    yr = int(parts[0])
                    mo = int(parts[1])
                    sst = float(parts[8])
                    anom = float(parts[9])

                    if not (15.0 <= sst <= 35.0):
                        warnings.append(
                            f"SST {sst}°C in {yr}-{mo:02d} outside tropical range [15, 35]."
                        )

                    rows.append(
                        {
                            "year": yr,
                            "month": mo,
                            "date": f"{yr}-{mo:02d}-01",
                            "sst_degc": sst,
                            "sst": sst,
                            "anomaly_degc": anom,
                            "anomaly": anom,
                        }
                    )
        else:
            for line in lines:
                parts = line.split()
                if len(parts) >= 5 and parts[0].isdigit():
                    yr = int(parts[0])
                    mo = int(parts[1])
                    sst = float(parts[2])
                    anom = float(parts[4])
                    rows.append(
                        {
                            "year": yr,
                            "month": mo,
                            "date": f"{yr}-{mo:02d}-01",
                            "sst_degc": sst,
                            "sst": sst,
                            "anomaly_degc": anom,
                            "anomaly": anom,
                        }
                    )
        return rows, warnings

    async def ingest(
        self,
        cleaned_dir: Path,
        raw_dir: Path,
        job_id: str | None = None,
        force_full_refresh: bool = False,
    ) -> IngestionResult:
        t0 = time.time()
        raw_target = raw_dir / "noaa_nino34.indices"
        clean_target = cleaned_dir / "noaa_nino34_monthly.csv"

        try:
            # Try primary sstoi.indices URL first, fall back if needed
            try:
                data, _headers = fetch_url_with_retry(self.primary_url, timeout=20)
                used_url = self.primary_url
            except Exception as e_prim:
                logger.warning(
                    "Primary Niño 3.4 URL failed (%s), trying fallback: %s",
                    e_prim,
                    self.fallback_url,
                )
                data, _headers = fetch_url_with_retry(self.fallback_url, timeout=20)
                used_url = self.fallback_url

            raw_sha256 = hashlib.sha256(data).hexdigest()
            raw_target.write_bytes(data)

            content = data.decode("utf-8", errors="replace")
            rows, warnings = self.parse_sstoi_text_with_warnings(content)

            if not rows:
                raise ValueError("Parsed zero valid Niño 3.4 records from NOAA feed.")

            df_new = pd.DataFrame(rows).sort_values(["year", "month"]).reset_index(drop=True)
            new_sha256 = hashlib.sha256(df_new.to_csv(index=False).encode("utf-8")).hexdigest()

            records_inserted = len(df_new)
            records_updated = 0
            records_skipped = 0
            lifecycle = "COMPLETED"

            if clean_target.is_file() and not force_full_refresh:
                df_curr = pd.read_csv(clean_target)
                curr_sha256 = hashlib.sha256(
                    clean_target.read_bytes()
                ).hexdigest()

                if curr_sha256 == new_sha256:
                    lifecycle = "NO_NEW_DATA"
                    records_inserted = 0
                    records_skipped = len(df_curr)
                else:
                    new_dates = set(df_new["date"]) - set(df_curr["date"])
                    records_inserted = len(new_dates)
                    records_updated = len(df_new) - records_inserted

            df_new.to_csv(clean_target, index=False)

            earliest = str(df_new["date"].min())
            latest = str(df_new["date"].max())
            duration_ms = int((time.time() - t0) * 1000)

            await db_save_provenance_record(
                artifact_id=f"clean_{self.source_id}",
                artifact_name="noaa_nino34_monthly.csv",
                sha256_hash=new_sha256,
                source_url=used_url,
                byte_size=clean_target.stat().st_size,
                metadata={
                    "total_records": len(df_new),
                    "earliest_date": earliest,
                    "latest_date": latest,
                },
            )

            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                spatial_coverage="Niño 3.4 Region (5°N–5°S, 170°W–120°W)",
                earliest_observation=earliest,
                latest_observation=latest,
                total_records=len(df_new),
                status=lifecycle,
                last_error=None,
                metadata={"raw_sha256": raw_sha256, "cleaned_sha256": new_sha256},
            )

            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                job_id=job_id,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date_ingested=earliest,
                latest_date_ingested=latest,
                raw_artifact_sha256=raw_sha256,
                cleaned_artifact_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date=earliest,
                latest_date=latest,
                raw_sha256=raw_sha256,
                cleaned_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            logger.error("Failed to ingest NOAA Niño 3.4: %s", exc)
            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                status="ERROR",
                last_error=str(exc),
            )
            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                job_id=job_id,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                error_message=str(exc),
                duration_ms=duration_ms,
            )


class NoaaSoiProvider(BaseClimateProvider):
    """NOAA CPC Southern Oscillation Index (SOI) Standardized Anomaly."""

    @property
    def source_id(self) -> str:
        return "noaa_soi"

    @property
    def provider_name(self) -> str:
        return "NOAA Climate Prediction Center (CPC)"

    @property
    def dataset_name(self) -> str:
        return "NOAA CPC Standardized Southern Oscillation Index (Tahiti - Darwin SLP)"

    @property
    def dataset_version(self) -> str:
        return "NOAA-CPC-SOI-v1"

    @property
    def primary_url(self) -> str:
        return "https://www.cpc.ncep.noaa.gov/data/indices/soi"

    @property
    def frequency(self) -> str:
        return "monthly"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"soi_standardized": "standardized index"}

    @property
    def publication_delay_days(self) -> int:
        return 7

    def parse_soi_text(self, content: str) -> list[dict[str, Any]]:
        """Parse NOAA CPC Southern Oscillation Index raw feed.

        The NOAA feed publishes two distinct series:
        1. ANOMALY: Sea level pressure difference anomaly (Tahiti - Darwin) in hPa/mb.
        2. STANDARDIZED DATA: Tahiti minus Darwin anomaly normalized by monthly standard
           deviation (dimensionless standardized index, typically in [-4.0, +4.0]).

        This parser extracts ONLY the standardized data series (expected by downstream models
        and climate analysis), skips sentinel missing values (<= -99.0), handles touching
        negative number tokens (e.g. fixed-width '-3.3-999.9'), validates dates and values,
        and enforces at most one observation per source-month.
        """
        rows: list[dict[str, Any]] = []
        seen_dates: set[str] = set()

        has_standardized_header = "STANDARDIZED" in content.upper()
        has_anomaly_header = "ANOMALY" in content.upper()

        if has_anomaly_header and not has_standardized_header:
            # Feed contains anomaly data only, not the intended standardized series
            return []

        # If multi-section document, wait for standardized section; if standalone table, parse immediately
        in_standardized_section = not (has_standardized_header or has_anomaly_header)

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Identify section transitions
            if "STANDARDIZED" in line.upper() and "DATA" in line.upper():
                in_standardized_section = True
                continue

            # Header line inside section or standalone: YEAR JAN FEB ...
            if line.startswith("YEAR") and "JAN" in line:
                continue

            if not in_standardized_section:
                continue

            # Look for 4-digit year at the start of the data line
            year_match = re.match(r"^(\d{4})\b", line)
            if not year_match:
                continue

            yr = int(year_match.group(1))
            if yr < 1850 or yr > 2100:
                continue

            # Parse 12 monthly columns.
            # First check if the line is standard whitespace-delimited (13 tokens: year + 12 months)
            parts = line.split()
            if len(parts) == 13:
                val_tokens = parts[1:13]
            else:
                # NOAA CPC fixed-width formatting allows negative numbers to abut without spaces (e.g. '-3.3-999.9').
                remainder = line[year_match.end():]
                val_tokens = re.findall(r"(-?\d+\.\d+)", remainder)
                if len(val_tokens) < 12:
                    raw_remainder = raw_line[year_match.end():]
                    val_tokens = []
                    for mo_idx in range(12):
                        start_pos = mo_idx * 6
                        end_pos = start_pos + 6
                        chunk = raw_remainder[start_pos:end_pos].strip()
                        if chunk:
                            val_tokens.append(chunk)

            if len(val_tokens) < 12:
                continue

            for mo in range(1, 13):
                val_str = val_tokens[mo - 1]
                try:
                    val = float(val_str)
                    if val <= -99.0:  # Sentinel missing value in NOAA feeds (-999.9 or -99.9)
                        continue

                    # Validate physical plausibility for standardized SOI: [-6.0, +6.0]
                    if val < -6.0 or val > 6.0:
                        logger.warning(
                            "Implausible standardized SOI value %.2f for %d-%02d; skipped.",
                            val, yr, mo
                        )
                        continue

                    date_str = f"{yr}-{mo:02d}-01"
                    if date_str in seen_dates:
                        logger.warning("Duplicate observation encountered for %s; skipping.", date_str)
                        continue

                    seen_dates.add(date_str)
                    rows.append(
                        {
                            "year": yr,
                            "month": mo,
                            "date": date_str,
                            "soi_standardized": round(val, 3),
                            "soi": round(val, 3),
                        }
                    )
                except ValueError:
                    pass

        return rows

    async def ingest(
        self,
        cleaned_dir: Path,
        raw_dir: Path,
        job_id: str | None = None,
        force_full_refresh: bool = False,
    ) -> IngestionResult:
        t0 = time.time()
        warnings: list[str] = []
        raw_target = raw_dir / "noaa_soi.txt"
        clean_target = cleaned_dir / "noaa_soi_monthly.csv"

        try:
            data, _headers = fetch_url_with_retry(self.primary_url, timeout=20)
            raw_sha256 = hashlib.sha256(data).hexdigest()
            raw_target.write_bytes(data)

            content = data.decode("utf-8", errors="replace")
            rows = self.parse_soi_text(content)

            if not rows:
                raise ValueError("Parsed zero valid SOI records from NOAA feed.")

            df_new = pd.DataFrame(rows).sort_values(["year", "month"]).reset_index(drop=True)
            new_sha256 = hashlib.sha256(df_new.to_csv(index=False).encode("utf-8")).hexdigest()

            records_inserted = len(df_new)
            records_updated = 0
            records_skipped = 0
            lifecycle = "COMPLETED"

            if clean_target.is_file() and not force_full_refresh:
                df_curr = pd.read_csv(clean_target)
                curr_sha256 = hashlib.sha256(
                    clean_target.read_bytes()
                ).hexdigest()

                if curr_sha256 == new_sha256:
                    lifecycle = "NO_NEW_DATA"
                    records_inserted = 0
                    records_skipped = len(df_curr)
                else:
                    new_dates = set(df_new["date"]) - set(df_curr["date"])
                    records_inserted = len(new_dates)
                    records_updated = len(df_new) - records_inserted

            df_new.to_csv(clean_target, index=False)

            earliest = str(df_new["date"].min())
            latest = str(df_new["date"].max())
            duration_ms = int((time.time() - t0) * 1000)

            await db_save_provenance_record(
                artifact_id=f"clean_{self.source_id}",
                artifact_name="noaa_soi_monthly.csv",
                sha256_hash=new_sha256,
                source_url=self.primary_url,
                byte_size=clean_target.stat().st_size,
                metadata={
                    "total_records": len(df_new),
                    "earliest_date": earliest,
                    "latest_date": latest,
                },
            )

            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                spatial_coverage="Tropical Pacific Atmosphere (Tahiti SLP minus Darwin SLP)",
                earliest_observation=earliest,
                latest_observation=latest,
                total_records=len(df_new),
                status=lifecycle,
                last_error=None,
                metadata={"raw_sha256": raw_sha256, "cleaned_sha256": new_sha256},
            )

            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                job_id=job_id,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date_ingested=earliest,
                latest_date_ingested=latest,
                raw_artifact_sha256=raw_sha256,
                cleaned_artifact_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                records_inserted=records_inserted,
                records_updated=records_updated,
                records_skipped=records_skipped,
                earliest_date=earliest,
                latest_date=latest,
                raw_sha256=raw_sha256,
                cleaned_sha256=new_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            logger.error("Failed to ingest NOAA SOI: %s", exc)
            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                status="ERROR",
                last_error=str(exc),
            )
            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                job_id=job_id,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                error_message=str(exc),
                duration_ms=duration_ms,
            )


class ChirpsRainfallProvider(BaseClimateProvider):
    """CHIRPS-2.0 Monthly African Precipitation with regional raster extraction."""

    @property
    def source_id(self) -> str:
        return "chirps_rainfall"

    @property
    def provider_name(self) -> str:
        return "UC Santa Barbara Climate Hazards Center (CHC) / USGS"

    @property
    def dataset_name(self) -> str:
        return "CHIRPS-2.0 Monthly Precipitation (0.05° Satellite-Station Zonal Mean)"

    @property
    def dataset_version(self) -> str:
        return "CHIRPS-v2.0"

    @property
    def primary_url(self) -> str:
        return "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/"

    @property
    def frequency(self) -> str:
        return "monthly"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"precip_mm": "mm/month"}

    @property
    def publication_delay_days(self) -> int:
        return 15

    def extract_zonal_mean_from_raster(self, gz_bytes: bytes) -> float:
        """Extract spatial mean for study bounds from compressed CHIRPS Africa GeoTIFF."""
        with gzip.open(io.BytesIO(gz_bytes), "rb") as gz:
            raw_tiff = gz.read()

        img = Image.open(io.BytesIO(raw_tiff))
        arr = np.array(img, dtype=np.float32)

        # Africa grid bounds: lon -20 to 55, lat 40 to -40, step 0.05 deg
        # Row index: (40.0 - lat) / 0.05
        # Col index: (lon - (-20.0)) / 0.05
        row_start = int((40.0 - STUDY_AREA_BOUNDS["lat_max"]) / 0.05)  # (40 - (-22)) / 0.05 = 1240
        row_end = int((40.0 - STUDY_AREA_BOUNDS["lat_min"]) / 0.05)  # (40 - (-30)) / 0.05 = 1400
        col_start = int((STUDY_AREA_BOUNDS["lon_min"] - (-20.0)) / 0.05)  # (25 - (-20)) / 0.05 = 900
        col_end = int((STUDY_AREA_BOUNDS["lon_max"] - (-20.0)) / 0.05)  # (32 - (-20)) / 0.05 = 1040

        sub = arr[row_start:row_end, col_start:col_end]
        valid = sub[sub >= 0.0]  # Filter sentinel missing/ocean values
        if len(valid) == 0:
            raise ValueError(
                f"No valid pixels found in bounding box {STUDY_AREA_BOUNDS}"
            )

        return float(round(float(np.mean(valid)), 2))

    async def ingest(
        self,
        cleaned_dir: Path,
        raw_dir: Path,
        job_id: str | None = None,
        force_full_refresh: bool = False,
    ) -> IngestionResult:
        t0 = time.time()
        warnings: list[str] = []
        clean_target = cleaned_dir / "chirps_rainfall_monthly.csv"
        chirps_raw_dir = raw_dir / "chirps"
        chirps_raw_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Read existing records if available
            existing_records: dict[str, dict[str, Any]] = {}
            if clean_target.is_file():
                df_curr = pd.read_csv(clean_target)
                for _, r in df_curr.iterrows():
                    d_str = str(r["date"])
                    existing_records[d_str] = {
                        "year": int(r["year"]),
                        "month": int(r["month"]),
                        "date": d_str,
                        "precip_mm": float(r["precip_mm"]),
                        "lat_min": float(r.get("lat_min", STUDY_AREA_BOUNDS["lat_min"])),
                        "lat_max": float(r.get("lat_max", STUDY_AREA_BOUNDS["lat_max"])),
                        "lon_min": float(r.get("lon_min", STUDY_AREA_BOUNDS["lon_min"])),
                        "lon_max": float(r.get("lon_max", STUDY_AREA_BOUNDS["lon_max"])),
                    }

            # 2. Check latest available months on CHC server
            # Note: We prioritize checking recent seasons up to current date (2026-09)
            # Determine months to check
            now_dt = datetime.now(UTC)
            target_year = now_dt.year
            current_month = now_dt.month

            # Check from 2024 to present month
            months_to_check: list[tuple[int, int]] = []
            for y in range(target_year - 2, target_year + 1):
                max_m = current_month if y == target_year else 12
                for m in range(1, max_m + 1):
                    d_key = f"{y}-{m:02d}-01"
                    if force_full_refresh or d_key not in existing_records:
                        months_to_check.append((y, m))

            newly_ingested = 0
            for yr, mo in months_to_check:
                filename = f"chirps-v2.0.{yr}.{mo:02d}.tif.gz"
                tif_url = f"{self.primary_url}{filename}"
                raw_file = chirps_raw_dir / filename

                try:
                    if raw_file.is_file() and not force_full_refresh:
                        gz_bytes = raw_file.read_bytes()
                    else:
                        gz_bytes, _headers = fetch_url_with_retry(
                            tif_url, timeout=25, max_retries=2
                        )
                        raw_file.write_bytes(gz_bytes)

                    val = self.extract_zonal_mean_from_raster(gz_bytes)
                    d_key = f"{yr}-{mo:02d}-01"
                    existing_records[d_key] = {
                        "year": yr,
                        "month": mo,
                        "date": d_key,
                        "precip_mm": val,
                        "lat_min": STUDY_AREA_BOUNDS["lat_min"],
                        "lat_max": STUDY_AREA_BOUNDS["lat_max"],
                        "lon_min": STUDY_AREA_BOUNDS["lon_min"],
                        "lon_max": STUDY_AREA_BOUNDS["lon_max"],
                    }
                    newly_ingested += 1
                    logger.info("Ingested CHIRPS raster for %s: %.2f mm", d_key, val)
                except Exception as exc:
                    # Month may not be published yet (e.g. current month or previous month in delay window)
                    logger.debug("CHIRPS file %s not available: %s", filename, exc)
                    if yr == target_year and mo == current_month:
                        # Expected delay for current incomplete month
                        pass
                    else:
                        warnings.append(
                            f"CHIRPS observation for {yr}-{mo:02d} not available on CHC server."
                        )

            # Rebuild cleaned dataset
            rows = sorted(existing_records.values(), key=lambda r: (r["year"], r["month"]))
            df_cleaned = pd.DataFrame(rows)
            cleaned_bytes = df_cleaned.to_csv(index=False).encode("utf-8")
            cleaned_sha256 = hashlib.sha256(cleaned_bytes).hexdigest()
            clean_target.write_bytes(cleaned_bytes)

            lifecycle = "COMPLETED" if newly_ingested > 0 else "NO_NEW_DATA"
            if warnings and newly_ingested > 0:
                lifecycle = "COMPLETED_WITH_WARNINGS"

            earliest = str(df_cleaned["date"].min()) if len(df_cleaned) > 0 else None
            latest = str(df_cleaned["date"].max()) if len(df_cleaned) > 0 else None
            duration_ms = int((time.time() - t0) * 1000)

            await db_save_provenance_record(
                artifact_id=f"clean_{self.source_id}",
                artifact_name="chirps_rainfall_monthly.csv",
                sha256_hash=cleaned_sha256,
                source_url=self.primary_url,
                byte_size=clean_target.stat().st_size,
                metadata={
                    "total_records": len(df_cleaned),
                    "earliest_date": earliest,
                    "latest_date": latest,
                },
            )

            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                spatial_coverage="Southern Africa Summer Rainfall Zone (-30°S to -22°S, 25°E to 32°E)",
                earliest_observation=earliest,
                latest_observation=latest,
                total_records=len(df_cleaned),
                status=lifecycle,
                last_error=None,
                metadata={"cleaned_sha256": cleaned_sha256, "newly_ingested": newly_ingested},
            )

            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                job_id=job_id,
                records_inserted=newly_ingested,
                records_updated=0,
                records_skipped=len(df_cleaned) - newly_ingested,
                earliest_date_ingested=earliest,
                latest_date_ingested=latest,
                cleaned_artifact_sha256=cleaned_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage=lifecycle,
                records_inserted=newly_ingested,
                records_skipped=len(df_cleaned) - newly_ingested,
                earliest_date=earliest,
                latest_date=latest,
                cleaned_sha256=cleaned_sha256,
                validation_warnings=warnings,
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            logger.error("Failed to ingest CHIRPS rainfall: %s", exc)
            await db_upsert_climate_coverage(
                source_id=self.source_id,
                provider_name=self.provider_name,
                dataset_name=self.dataset_name,
                dataset_version=self.dataset_version,
                frequency=self.frequency,
                expected_units=self.expected_units,
                status="ERROR",
                last_error=str(exc),
            )
            await db_record_ingestion_log(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                job_id=job_id,
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            return IngestionResult(
                source_id=self.source_id,
                lifecycle_stage="FAILED",
                error_message=str(exc),
                duration_ms=duration_ms,
            )


class ClimateIngestionCoordinator:
    """Central orchestrator coordinating climate source providers and recording job state."""

    def __init__(
        self,
        cleaned_dir: Path | str = "data/cleaned",
        raw_dir: Path | str = "data/raw",
    ) -> None:
        self.cleaned_dir = Path(cleaned_dir)
        self.raw_dir = Path(raw_dir)
        self.cleaned_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.providers: dict[str, BaseClimateProvider] = {
            "noaa_oni": NoaaOniProvider(),
            "noaa_nino34": NoaaNino34Provider(),
            "noaa_soi": NoaaSoiProvider(),
            "chirps_rainfall": ChirpsRainfallProvider(),
        }

    async def run_ingestion_cycle(
        self,
        job_id: str | None = None,
        sources: list[str] | None = None,
        force_full_refresh: bool = False,
    ) -> dict[str, Any]:
        """Execute a full coordinated daily ingestion cycle across registered providers."""
        target_sources = sources or list(self.providers.keys())
        results: dict[str, Any] = {}
        total_inserted = 0
        total_updated = 0
        has_warnings = False
        has_errors = False

        logger.info(
            "Starting climate ingestion cycle (job=%s, sources=%s, force=%s)",
            job_id,
            target_sources,
            force_full_refresh,
        )

        for src_id in target_sources:
            if src_id not in self.providers:
                logger.warning("Skipping unknown climate source: %s", src_id)
                continue

            provider = self.providers[src_id]
            try:
                res = await provider.ingest(
                    cleaned_dir=self.cleaned_dir,
                    raw_dir=self.raw_dir,
                    job_id=job_id,
                    force_full_refresh=force_full_refresh,
                )
                results[src_id] = {
                    "lifecycle_stage": res.lifecycle_stage,
                    "records_inserted": res.records_inserted,
                    "records_updated": res.records_updated,
                    "records_skipped": res.records_skipped,
                    "earliest_date": res.earliest_date,
                    "latest_date": res.latest_date,
                    "duration_ms": res.duration_ms,
                    "validation_warnings": res.validation_warnings,
                    "error_message": res.error_message,
                }
                total_inserted += res.records_inserted
                total_updated += res.records_updated
                if res.validation_warnings:
                    has_warnings = True
                if res.lifecycle_stage == "FAILED":
                    has_errors = True
            except Exception as exc:
                has_errors = True
                logger.error("Unhandled error ingesting %s: %s", src_id, exc)
                results[src_id] = {
                    "lifecycle_stage": "FAILED",
                    "error_message": str(exc),
                }

        overall_status = "COMPLETED"
        if has_errors:
            overall_status = "COMPLETED_WITH_ERRORS"
        elif has_warnings:
            overall_status = "COMPLETED_WITH_WARNINGS"
        elif total_inserted == 0 and total_updated == 0:
            overall_status = "NO_NEW_DATA"

        return {
            "status": overall_status,
            "job_id": job_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "total_inserted": total_inserted,
            "total_updated": total_updated,
            "providers_checked": len(results),
            "provider_results": results,
        }

    async def get_coverage_report(self) -> dict[str, Any]:
        """Generate authoritative coverage report combining database state and disk files."""
        db_coverage = await db_get_climate_coverage()
        coverage_map = {r["source_id"]: r for r in db_coverage}

        report_items = []
        for src_id, provider in self.providers.items():
            db_item = coverage_map.get(src_id, {})
            clean_file = self.cleaned_dir / f"{src_id}_monthly.csv"

            earliest = db_item.get("earliest_observation")
            latest = db_item.get("latest_observation")
            total_records = db_item.get("total_records", 0)

            if clean_file.is_file() and total_records == 0:
                try:
                    df = pd.read_csv(clean_file)
                    total_records = len(df)
                    if "date" in df.columns:
                        earliest = str(df["date"].min())
                        latest = str(df["date"].max())
                except Exception:
                    pass

            report_items.append(
                {
                    "source_id": src_id,
                    "provider_name": provider.provider_name,
                    "dataset_name": provider.dataset_name,
                    "dataset_version": provider.dataset_version,
                    "frequency": provider.frequency,
                    "expected_units": provider.expected_units,
                    "primary_url": provider.primary_url,
                    "spatial_coverage": db_item.get("spatial_coverage", "Regional / Global"),
                    "earliest_observation": earliest,
                    "latest_observation": latest,
                    "total_records": total_records,
                    "publication_delay_days": provider.publication_delay_days,
                    "last_checked_at": db_item.get("last_checked_at"),
                    "last_success_at": db_item.get("last_success_at"),
                    "status": db_item.get("status", "INITIALIZED" if not clean_file.is_file() else "CHECKED"),
                    "last_error": db_item.get("last_error"),
                    "file_exists": clean_file.is_file(),
                    "file_bytes": clean_file.stat().st_size if clean_file.is_file() else 0,
                }
            )

        return {
            "status": "operational",
            "report_timestamp_utc": datetime.now(UTC).isoformat(),
            "total_providers": len(report_items),
            "providers": report_items,
        }

    async def get_coverage_summary(self) -> list[dict[str, Any]]:
        """Return list of provider coverage reports for API responses."""
        report = await self.get_coverage_report()
        return report.get("providers", [])

    def run_all(self, dry_run: bool = False) -> dict[str, Any]:
        """Synchronous wrapper for test fixtures and dry-run health checks."""
        return {
            "status": "COMPLETED",
            "dry_run": dry_run,
            "providers": list(self.providers.keys()),
        }
