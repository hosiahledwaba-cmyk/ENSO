"""NOAA CPC Niño 3.4 SST index and anomaly dataset adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.data.adapters.base import BaseDatasetAdapter
from ml.data.validation.models import ValidationReport
from ml.data.validation.validator import DatasetValidator


class NoaaNino34Adapter(BaseDatasetAdapter):
    """Adapter for NOAA CPC Niño 3.4 monthly Sea Surface Temperature and Anomaly."""

    @property
    def source_id(self) -> str:
        return "noaa_nino34"

    @property
    def name(self) -> str:
        return "NOAA CPC Niño 3.4 Sea Surface Temperature Index (ERSST.v5)"

    @property
    def version(self) -> str:
        return "NOAA-CPC-Nino3.4-v5"

    @property
    def licence(self) -> str:
        return "Public Domain (U.S. Government Work)"

    @property
    def citation(self) -> str:
        return (
            "Huang, B., Thorne, P. W., Banzon, V. F., et al. (2017). "
            "Extended Reconstructed Sea Surface Temperature, Version 5 (ERSSTv5): "
            "Upgrades, Validations, and Intercomparisons. Journal of Climate, 30(20), 8179-8205. "
            "https://doi.org/10.1175/JCLI-D-16-0836.1"
        )

    @property
    def source_url(self) -> str:
        return "https://www.cpc.ncep.noaa.gov/data/indices/ersst5.nino.mth.81-10.ascii"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"sst_degc": "degC", "anomaly_degc": "degC"}

    def load_raw(self, raw_path: Path | str) -> pd.DataFrame:
        """Parse raw file (supporting both NOAA whitespace ASCII table and standard CSV)."""
        path = Path(raw_path)
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, comment="#")
        else:
            try:
                df = pd.read_csv(path, sep=r"\s+", comment="#")
            except (ValueError, OSError, pd.errors.ParserError):
                df = pd.read_csv(path, sep=None, engine="python", comment="#")

        df.columns = [c.strip().lower() for c in df.columns]

        # Rename aliases
        col_aliases = {
            "yr": "year",
            "mo": "month",
            "mon": "month",
            "sst": "sst_degc",
            "total": "sst_degc",
            "nino34": "sst_degc",
            "anom": "anomaly_degc",
            "ssta": "anomaly_degc",
        }
        df = df.rename(columns=col_aliases)
        return df

    def validate(self, raw_df: pd.DataFrame) -> ValidationReport:
        """Validate schema, timestamps, missingness, and SST physical bounds."""
        required = {
            "year": int,
            "month": int,
            "sst_degc": float,
            "anomaly_degc": float,
        }
        report = DatasetValidator.validate_schema(raw_df, required, self.source_id, self.version)
        if not report.is_valid:
            return report

        # Timestamps
        DatasetValidator.validate_timestamps(
            raw_df, year_col="year", month_col="month", report=report
        )

        # Missing values (Prohibit silent imputation)
        DatasetValidator.validate_no_missing(
            raw_df, ["year", "month", "sst_degc", "anomaly_degc"], report=report
        )

        # Physical ranges: equatorial Pacific SST is typically 15C-35C, anomalies -5C to +5C
        DatasetValidator.validate_value_ranges(
            raw_df,
            {
                "sst_degc": (15.0, 35.0),
                "anomaly_degc": (-5.0, 5.0),
            },
            report=report,
        )

        return report

    def clean(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Standardize and chronologically sort Niño 3.4 table."""
        df = raw_df.copy()
        df["year"] = df["year"].astype(int)
        df["month"] = df["month"].astype(int)
        df["sst_degc"] = df["sst_degc"].astype(float).round(3)
        df["anomaly_degc"] = df["anomaly_degc"].astype(float).round(3)
        df["date"] = df.apply(lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}", axis=1)

        # Sort chronologically
        df = df.sort_values(by=["year", "month"]).reset_index(drop=True)
        cols = ["year", "month", "date", "sst_degc", "anomaly_degc"]
        return df[cols]
