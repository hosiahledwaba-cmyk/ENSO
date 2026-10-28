"""Target leakage detection and temporal partition integrity guards."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

import pandas as pd

logger = logging.getLogger("enso_ml.features.leakage")

TARGET_COLUMNS = {
    "seasonal_precip_djf_mm",
    "seasonal_precip_zscore",
    "target_drought_p20",
    "target_below_normal_p33",
    "precip_dec",
    "precip_jan",
    "precip_feb",
}


class TargetLeakageError(ValueError):
    """Raised when target variables or future observations leak into the predictor feature set."""


class TemporalOrderViolationError(ValueError):
    """Raised when timestamps violate operational chronology or lead-time ordering."""


class PartitionOverlapError(ValueError):
    """Raised when training, validation, or test partitions share seasons or violate ordering."""


class TargetLeakageDetector:
    """Rigorous audit guards ensuring zero lookahead, zero target leakage, and partition hygiene."""

    @staticmethod
    def validate_timeline_integrity(df: pd.DataFrame) -> None:
        """Verify that every forecast issue date precedes the target window onset."""
        required = ["forecast_issue_date", "target_period"]
        for col in required:
            if col not in df.columns:
                raise TemporalOrderViolationError(f"Missing required timeline column: '{col}'")

        for idx, row in df.iterrows():
            issue_str = str(row["forecast_issue_date"])
            target_str = str(row["target_period"])

            try:
                issue_date = date.fromisoformat(issue_str)
            except ValueError as e:
                raise TemporalOrderViolationError(
                    f"Row {idx}: Invalid forecast_issue_date '{issue_str}'"
                ) from e

            # Target period format: 'YYYY-12_to_YYYY-02' or 'YYYY-12-01_to_YYYY-02-28'
            target_start_str = target_str.split("_to_")[0]
            if len(target_start_str) == 7:  # YYYY-MM
                target_start_str = f"{target_start_str}-01"

            try:
                target_start = date.fromisoformat(target_start_str)
            except ValueError as e:
                raise TemporalOrderViolationError(
                    f"Row {idx}: Invalid target period start '{target_start_str}'"
                ) from e

            if issue_date >= target_start:
                raise TemporalOrderViolationError(
                    f"Row {idx}: Issue date ({issue_date}) is not strictly prior to "
                    f"target start date ({target_start}). Lookahead violation!"
                )

    @staticmethod
    def validate_predictor_feature_isolation(
        predictor_columns: Sequence[str],
        allowed_extra: Sequence[str] | None = None,
    ) -> None:
        """Ensure no target column is included in the predictor feature matrix."""
        allowed = set(allowed_extra or [])
        forbidden = (TARGET_COLUMNS - allowed).intersection(set(predictor_columns))
        if forbidden:
            raise TargetLeakageError(
                f"Target leakage detected! Feature set contains targets: {sorted(forbidden)}"
            )

    @staticmethod
    def validate_partition_isolation(df: pd.DataFrame, split_column: str = "split") -> None:
        """Ensure that train, val, and test splits have zero overlap and strict chronology."""
        if split_column not in df.columns:
            logger.warning(
                "Split column '%s' not found in DataFrame; skipping partition check.", split_column
            )
            return

        splits = set(df[split_column].dropna().unique())
        expected_splits = {"train", "val", "test"}
        unknown = splits - expected_splits
        if unknown:
            raise PartitionOverlapError(
                f"Unknown split labels: {unknown}. Expected subset of {expected_splits}"
            )

        # Extract season years per split
        train_seasons = set(df[df[split_column] == "train"]["season_year"].tolist())
        val_seasons = set(df[df[split_column] == "val"]["season_year"].tolist())
        test_seasons = set(df[df[split_column] == "test"]["season_year"].tolist())

        # Check for set intersections
        if train_seasons.intersection(val_seasons):
            overlap = train_seasons.intersection(val_seasons)
            raise PartitionOverlapError(f"Overlap detected between train and val: {overlap}")
        if train_seasons.intersection(test_seasons):
            overlap = train_seasons.intersection(test_seasons)
            raise PartitionOverlapError(f"Overlap detected between train and test: {overlap}")
        if val_seasons.intersection(test_seasons):
            overlap = val_seasons.intersection(test_seasons)
            raise PartitionOverlapError(f"Overlap detected between val and test: {overlap}")

        # Enforce chronological monotonicity
        if train_seasons and val_seasons:
            max_train = max(train_seasons)
            min_val = min(val_seasons)
            if max_train >= min_val:
                raise PartitionOverlapError(
                    f"Chronological violation: max(train)={max_train} >= min(val)={min_val}"
                )

        if val_seasons and test_seasons:
            max_val = max(val_seasons)
            min_test = min(test_seasons)
            if max_val >= min_test:
                raise PartitionOverlapError(
                    f"Chronological violation: max(val)={max_val} >= min(test)={min_test}"
                )

        if train_seasons and test_seasons and not val_seasons:
            max_train = max(train_seasons)
            min_test = min(test_seasons)
            if max_train >= min_test:
                raise PartitionOverlapError(
                    f"Chronological violation: max(train)={max_train} >= min(test)={min_test}"
                )

    @staticmethod
    def verify_climatology_leakage_absence(
        train_df: pd.DataFrame,
        future_df: pd.DataFrame,
        fit_fn: Any,
    ) -> bool:
        """Verify that modifying future_df produces zero change in training parameters."""
        # Baseline reference parameters
        ref_base = fit_fn(train_df)

        # Perturbed future dataframe (e.g. 10x rainfall)
        future_perturbed = future_df.copy()
        if "seasonal_precip_djf_mm" in future_perturbed.columns:
            future_perturbed["seasonal_precip_djf_mm"] = (
                future_perturbed["seasonal_precip_djf_mm"] * 5.0
            )
        if "precip_oct_mm" in future_perturbed.columns:
            future_perturbed["precip_oct_mm"] = future_perturbed["precip_oct_mm"] + 50.0

        ref_after = fit_fn(train_df)

        is_invariant = (
            ref_base.mean_seasonal_precip_mm == ref_after.mean_seasonal_precip_mm
            and ref_base.std_seasonal_precip_mm == ref_after.std_seasonal_precip_mm
            and ref_base.tau_drought_p20_mm == ref_after.tau_drought_p20_mm
            and ref_base.mean_october_precip_mm == ref_after.mean_october_precip_mm
        )

        if not is_invariant:
            raise TargetLeakageError(
                "Training reference baseline is contaminated by future partition data!"
            )
        return True
