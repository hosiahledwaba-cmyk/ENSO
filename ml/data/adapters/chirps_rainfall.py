"""CHIRPS-2.0 historical rainfall dataset adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.data.adapters.base import BaseDatasetAdapter
from ml.data.validation.models import SpatialBounds, ValidationReport
from ml.data.validation.validator import DatasetValidator

# Approved Southern African summer rainfall study zone (RD-003)
STUDY_AREA_BOUNDS = SpatialBounds(
    lat_min=-30.0,
    lat_max=-22.0,
    lon_min=25.0,
    lon_max=32.0,
)


class ChirpsRainfallAdapter(BaseDatasetAdapter):
    """Adapter for CHIRPS-2.0 monthly rainfall time-series."""

    @property
    def source_id(self) -> str:
        return "chirps_rainfall"

    @property
    def name(self) -> str:
        return "CHIRPS-2.0 Climate Hazards Group InfraRed Precipitation with Station Data"

    @property
    def version(self) -> str:
        return "CHIRPS-v2.0"

    @property
    def licence(self) -> str:
        return "Public Domain / CC0 (USGS & UC Santa Barbara CHC)"

    @property
    def citation(self) -> str:
        return (
            "Funk, C., Peterson, P., Landsfeld, M., et al. (2015). "
            "The climate hazards infrared precipitation with stations—a new environmental record "
            "for monitoring extremes. Scientific Data, 2, 150066. https://doi.org/10.1038/sdata.2015.66"
        )

    @property
    def source_url(self) -> str:
        return "https://data.chc.ucsb.edu/products/CHIRPS-2.0/"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"precip_mm": "mm/month"}

    @property
    def spatial_bounds(self) -> SpatialBounds:
        return STUDY_AREA_BOUNDS

    def load_raw(self, raw_path: Path | str) -> pd.DataFrame:
        """Parse raw CSV or space-delimited text file."""
        path = Path(raw_path)
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, comment="#")
        else:
            try:
                df = pd.read_csv(path, sep=r"\s+", comment="#")
            except (ValueError, OSError, pd.errors.ParserError):
                df = pd.read_csv(path, sep=None, engine="python", comment="#")

        # Normalize column header whitespace and casing
        df.columns = [c.strip().lower() for c in df.columns]

        # Alias common column representations
        col_aliases = {
            "rainfall": "precip_mm",
            "precip": "precip_mm",
            "precipitation": "precip_mm",
            "prcp": "precip_mm",
            "yr": "year",
            "mo": "month",
        }
        df = df.rename(columns=col_aliases)
        return df

    def validate(self, raw_df: pd.DataFrame) -> ValidationReport:
        """Execute strict schema, physical bounds, timestamp, and missingness checks."""
        # 1. Schema
        required = {"year": int, "month": int, "precip_mm": float}
        report = DatasetValidator.validate_schema(raw_df, required, self.source_id, self.version)
        if not report.is_valid:
            return report

        # 2. Timestamps
        DatasetValidator.validate_timestamps(
            raw_df, year_col="year", month_col="month", report=report
        )

        # 3. Missing values (No silent imputation)
        DatasetValidator.validate_no_missing(raw_df, ["year", "month", "precip_mm"], report=report)

        # 4. Physical range (Rainfall >= 0, and monthly precipitation <= 2000 mm)
        DatasetValidator.validate_value_ranges(raw_df, {"precip_mm": (0.0, 2000.0)}, report=report)

        # 5. Spatial coordinates (if present in tabular raster extract)
        if all(c in raw_df.columns for c in ("lat_min", "lat_max", "lon_min", "lon_max")):
            file_bounds = SpatialBounds(
                lat_min=float(raw_df["lat_min"].min()),
                lat_max=float(raw_df["lat_max"].max()),
                lon_min=float(raw_df["lon_min"].min()),
                lon_max=float(raw_df["lon_max"].max()),
            )
            DatasetValidator.validate_spatial_coverage(
                file_bounds, STUDY_AREA_BOUNDS, report=report
            )

        return report

    def clean(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Produce canonical, sorted time-series table."""
        df = raw_df.copy()
        df["year"] = df["year"].astype(int)
        df["month"] = df["month"].astype(int)
        df["precip_mm"] = df["precip_mm"].astype(float).round(3)

        # Add ISO date string
        df["date"] = df.apply(lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}", axis=1)

        # Add spatial bounds attributes if not explicitly in raw columns
        if "lat_min" not in df.columns:
            df["lat_min"] = STUDY_AREA_BOUNDS.lat_min
            df["lat_max"] = STUDY_AREA_BOUNDS.lat_max
            df["lon_min"] = STUDY_AREA_BOUNDS.lon_min
            df["lon_max"] = STUDY_AREA_BOUNDS.lon_max

        # Sort chronologically
        df = df.sort_values(by=["year", "month"]).reset_index(drop=True)

        cols = [
            "year",
            "month",
            "date",
            "precip_mm",
            "lat_min",
            "lat_max",
            "lon_min",
            "lon_max",
        ]
        return df[cols]
