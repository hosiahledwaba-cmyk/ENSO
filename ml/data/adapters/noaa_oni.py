"""NOAA CPC Oceanic Niño Index (ONI) dataset adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ml.data.adapters.base import BaseDatasetAdapter
from ml.data.validation.models import ValidationReport
from ml.data.validation.validator import DatasetValidator

SEASONS_12 = [
    "DJF",
    "JFM",
    "FMA",
    "MAM",
    "AMJ",
    "MJJ",
    "JJA",
    "JAS",
    "ASO",
    "SON",
    "OND",
    "NDJ",
]
SEASON_TO_CENTER_MONTH = {s: i + 1 for i, s in enumerate(SEASONS_12)}


class NoaaOniAdapter(BaseDatasetAdapter):
    """Adapter for NOAA CPC Oceanic Niño Index (3-month running mean SST anomalies)."""

    @property
    def source_id(self) -> str:
        return "noaa_oni"

    @property
    def name(self) -> str:
        return "NOAA CPC Oceanic Niño Index (ERSST.v5 Niño 3.4 3-Month Running Mean)"

    @property
    def version(self) -> str:
        return "NOAA-CPC-ONI-v5"

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
        return "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

    @property
    def expected_units(self) -> dict[str, str]:
        return {"oni_anomaly_degc": "degC"}

    def load_raw(self, raw_path: Path | str) -> pd.DataFrame:
        """Parse NOAA ONI format (wide seasonal matrix, sequential ascii, or CSV)."""
        path = Path(raw_path)
        content = path.read_text(encoding="utf-8", errors="replace")

        # 1. Detect if wide seasonal matrix (Year followed by DJF, JFM, ...)
        first_lines = [line.strip() for line in content.splitlines() if line.strip()][:5]
        is_matrix = any("DJF" in line and "JFM" in line for line in first_lines)

        if is_matrix:
            # Parse wide table: Year, DJF, JFM, ...
            rows: list[dict[str, object]] = []
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "DJF" in line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    year = int(parts[0])
                    for i, s in enumerate(SEASONS_12):
                        val_idx = i + 1
                        if val_idx < len(parts):
                            try:
                                val = float(parts[val_idx])
                                rows.append(
                                    {
                                        "year": year,
                                        "season": s,
                                        "month": SEASON_TO_CENTER_MONTH[s],
                                        "oni_anomaly_degc": val,
                                    }
                                )
                            except ValueError:
                                pass
            return pd.DataFrame(rows)

        # 2. Sequential NOAA ASCII format: SEAS YR TOTAL ANOM
        if any("SEAS" in line and "ANOM" in line for line in first_lines):
            rows = []
            for line in content.splitlines():
                line = line.strip()
                if not line or "SEAS" in line:
                    continue
                parts = line.split()
                if len(parts) >= 4 and parts[0] in SEASON_TO_CENTER_MONTH:
                    s = parts[0]
                    year = int(parts[1])
                    anom = float(parts[3])
                    rows.append(
                        {
                            "year": year,
                            "season": s,
                            "month": SEASON_TO_CENTER_MONTH[s],
                            "oni_anomaly_degc": anom,
                        }
                    )
            return pd.DataFrame(rows)

        # 3. Standard CSV / TSV fallback
        df = pd.read_csv(path, sep=None, engine="python")
        df.columns = [c.strip().lower() for c in df.columns]
        aliases = {
            "anom": "oni_anomaly_degc",
            "anomaly": "oni_anomaly_degc",
            "oni": "oni_anomaly_degc",
            "yr": "year",
            "mo": "month",
        }
        df = df.rename(columns=aliases)
        if "season" not in df.columns and "month" in df.columns:
            month_to_season = {v: k for k, v in SEASON_TO_CENTER_MONTH.items()}
            df["season"] = df["month"].map(month_to_season)
        return df

    def validate(self, raw_df: pd.DataFrame) -> ValidationReport:
        """Validate schema, calendar sequence, physical range, and missingness."""
        required = {"year": int, "month": int, "season": str, "oni_anomaly_degc": float}
        report = DatasetValidator.validate_schema(raw_df, required, self.source_id, self.version)
        if not report.is_valid:
            return report

        # Timestamps
        DatasetValidator.validate_timestamps(
            raw_df, year_col="year", month_col="month", report=report
        )

        # Missing values (Prohibit silent imputation)
        DatasetValidator.validate_no_missing(
            raw_df, ["year", "month", "season", "oni_anomaly_degc"], report=report
        )

        # Physical range: ONI anomaly in Pacific Niño 3.4 rarely exceeds [-4.0, +4.0] degC
        DatasetValidator.validate_value_ranges(
            raw_df, {"oni_anomaly_degc": (-4.0, 4.0)}, report=report
        )

        return report

    def clean(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Produce canonical, chronologically sorted ONI table."""
        df = raw_df.copy()
        df["year"] = df["year"].astype(int)
        df["month"] = df["month"].astype(int)
        df["season"] = df["season"].astype(str)
        df["oni_anomaly_degc"] = df["oni_anomaly_degc"].astype(float).round(3)
        df["date"] = df.apply(lambda r: f"{int(r['year']):04d}-{int(r['month']):02d}", axis=1)

        # Sort chronologically
        df = df.sort_values(by=["year", "month"]).reset_index(drop=True)
        cols = ["year", "month", "date", "season", "oni_anomaly_degc"]
        return df[cols]
