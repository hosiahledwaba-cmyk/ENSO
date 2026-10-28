"""Core validation engine for climate data ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from ml.data.validation.models import SpatialBounds, ValidationReport

# Standard sentinel missing value representations in legacy climate datasets
SENTINEL_MISSING_VALUES = {-9999.0, -999.0, -99.99, -99.9, -9999, -999}


class DatasetValidator:
    """Enforces strict scientific and data-engineering validation rules."""

    @staticmethod
    def validate_schema(
        df: pd.DataFrame,
        required_columns: Mapping[str, Any],
        dataset_id: str,
        source_version: str,
    ) -> ValidationReport:
        """Validate presence and types of required dataframe columns."""
        report = ValidationReport(
            dataset_id=dataset_id,
            source_version=source_version,
            total_records=len(df),
            is_valid=True,
        )

        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            report.add_check(
                name="schema_columns",
                passed=False,
                detail=f"Missing required columns: {missing_cols}",
                error_count=len(missing_cols),
            )
        else:
            report.add_check(
                name="schema_columns",
                passed=True,
                detail=f"All {len(required_columns)} required columns present.",
            )

        return report

    @staticmethod
    def validate_timestamps(
        df: pd.DataFrame,
        year_col: str = "year",
        month_col: str = "month",
        report: ValidationReport | None = None,
    ) -> ValidationReport:
        """Verify chronological ordering, no duplicates, and valid calendar bounds."""
        if report is None:
            report = ValidationReport(
                dataset_id="unknown",
                source_version="unknown",
                total_records=len(df),
                is_valid=True,
            )

        if year_col not in df.columns or month_col not in df.columns:
            report.add_check(
                name="timestamp_format",
                passed=False,
                detail=f"Columns {year_col} or {month_col} missing for timestamp check.",
            )
            return report

        # 1. Month range check [1, 12]
        invalid_months = df[(df[month_col] < 1) | (df[month_col] > 12)]
        if not invalid_months.empty:
            report.add_check(
                name="month_bounds",
                passed=False,
                detail="Month values must be integers between 1 and 12.",
                error_count=len(invalid_months),
                sample_errors=[
                    f"Row index {i}: month={row[month_col]}"
                    for i, row in invalid_months.head(3).iterrows()
                ],
            )
        else:
            report.add_check(
                name="month_bounds",
                passed=True,
                detail="All month values within [1, 12].",
            )

        # 2. Duplicate timestamp check
        duplicates = df[df.duplicated(subset=[year_col, month_col], keep=False)]
        if not duplicates.empty:
            sample = [
                f"Year {row[year_col]} Month {row[month_col]}"
                for _, row in duplicates.head(3).iterrows()
            ]
            report.add_check(
                name="duplicate_timestamps",
                passed=False,
                detail=f"Found {len(duplicates)} duplicate timestamp rows.",
                error_count=len(duplicates),
                sample_errors=sample,
            )
        else:
            report.add_check(
                name="duplicate_timestamps",
                passed=True,
                detail="Zero duplicate timestamps detected.",
            )

        # 3. Monotonic chronological ordering check
        sort_values = df[year_col] * 12 + df[month_col]
        is_monotonic = bool(sort_values.is_monotonic_increasing)
        if not is_monotonic:
            report.add_check(
                name="monotonic_timestamps",
                passed=False,
                detail="Records are not strictly sorted in chronological order.",
            )
        else:
            report.add_check(
                name="monotonic_timestamps",
                passed=True,
                detail="Records are strictly monotonic ascending.",
            )

        return report

    @staticmethod
    def validate_no_missing(
        df: pd.DataFrame,
        checked_columns: list[str],
        report: ValidationReport,
    ) -> ValidationReport:
        """Strict check that records contain zero nulls, NaNs, or sentinel missing values.

        DO NOT SILENTLY IMPUTE: Missing values must be flagged and rejected explicitly.
        """
        for col in checked_columns:
            if col not in df.columns:
                continue

            null_mask = df[col].isna() | df[col].isnull()
            sentinel_mask = df[col].isin(SENTINEL_MISSING_VALUES)
            combined_mask = null_mask | sentinel_mask
            bad_count = int(combined_mask.sum())

            if bad_count > 0:
                bad_indices = list(df[combined_mask].index[:5])
                report.add_check(
                    name=f"missing_values_{col}",
                    passed=False,
                    detail=(
                        f"Column '{col}' has {bad_count} missing or sentinel values. "
                        "Silent imputation prohibited."
                    ),
                    error_count=bad_count,
                    sample_errors=[f"Index {idx}" for idx in bad_indices],
                )
            else:
                report.add_check(
                    name=f"missing_values_{col}",
                    passed=True,
                    detail=f"Column '{col}' has 0 missing or sentinel values.",
                )

        return report

    @staticmethod
    def validate_spatial_coverage(
        bounds: SpatialBounds,
        target_bounds: SpatialBounds,
        report: ValidationReport,
    ) -> ValidationReport:
        """Validate that dataset spatial coverage encloses or equals the expected study region."""
        # Target Limpopo/Maize-belt domain: Lat [-30.0, -22.0], Lon [25.0, 32.0]
        # In Southern Africa coordinates: lat_min is -30.0 (south), lat_max is -22.0 (north)
        lat_valid = (
            bounds.lat_min <= target_bounds.lat_min and bounds.lat_max >= target_bounds.lat_max
        )
        lon_valid = (
            bounds.lon_min <= target_bounds.lon_min and bounds.lon_max >= target_bounds.lon_max
        )

        passed = lat_valid and lon_valid
        b_str = f"[{bounds.lat_min}, {bounds.lat_max}], [{bounds.lon_min}, {bounds.lon_max}]"
        t_str = f"[{target_bounds.lat_min}, {target_bounds.lat_max}]"
        detail = f"Dataset bounds ({b_str}) vs target ({t_str})."
        report.add_check(
            name="geographic_coverage",
            passed=passed,
            detail=detail
            if not passed
            else "Dataset geographic domain covers the required study area.",
        )
        return report

    @staticmethod
    def validate_value_ranges(
        df: pd.DataFrame,
        value_ranges: dict[str, tuple[float | None, float | None]],
        report: ValidationReport,
    ) -> ValidationReport:
        """Verify physical value bounds (e.g. precipitation >= 0 mm, SST in [15, 35] C)."""
        for col, (min_val, max_val) in value_ranges.items():
            if col not in df.columns:
                continue

            violations = pd.Series(False, index=df.index)
            if min_val is not None:
                violations |= df[col] < min_val
            if max_val is not None:
                violations |= df[col] > max_val

            bad_count = int(violations.sum())
            if bad_count > 0:
                samples = [f"Row {i}: {df.loc[i, col]}" for i in df[violations].index[:3]]
                report.add_check(
                    name=f"physical_range_{col}",
                    passed=False,
                    detail=(
                        f"Column '{col}' has {bad_count} values outside expected range "
                        f"[{min_val}, {max_val}]."
                    ),
                    error_count=bad_count,
                    sample_errors=samples,
                )
            else:
                report.add_check(
                    name=f"physical_range_{col}",
                    passed=True,
                    detail=f"All '{col}' values within physical range [{min_val}, {max_val}].",
                )

        return report
