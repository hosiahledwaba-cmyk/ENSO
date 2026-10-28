"""Defensive data-anomaly detection module for ENSO Shield.

Implements transparent, physically-grounded statistical checks for:
- Impossible values (physical boundaries of precipitation, SST, ONI)
- Sudden changes (month-over-month rate of change exceeding oceanic/atmospheric inertia)
- Missingness and sentinel screening (nulls, NaNs, -999.0, 999.9)
- Timestamp irregularities (non-monotonicity, duplicates, gaps)
- Replayed observations and sensor freezes (telemetry freeze, duplicate blocks)
- Cross-source inconsistencies (divergence between NOAA ONI and NOAA Niño 3.4 SST)

Includes a baseline multivariate anomaly detector (robust Mahalanobis distance)
that improves on 1D checks by detecting subtle joint covariance distortions.

CRITICAL INVARIANT:
Ordinary statistical anomalies are NEVER classified as confirmed malicious activity.
Every detection has is_confirmed_malicious=False and an evidence-based classification
(MEASUREMENT_NOISE, DATA_QUALITY_ANOMALY, SUSPICIOUS_ANOMALY, POTENTIAL_ADVERSARIAL_PERTURBATION).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.stats import chi2

from ml.defense.models import (
    AnomalyClassification,
    AnomalyDetection,
    AnomalySeverity,
    DefenseCheckResult,
    DefensiveInspectionReport,
)

logger = logging.getLogger("enso_ml.defense.detector")

# Physical domain limits based on atmospheric & oceanographic physics
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    # Precipitation in mm/month (cannot be negative; monthly regional max ~1500mm)
    "precip_mm": (0.0, 1500.0),
    "precip_oct_mm": (0.0, 1500.0),
    "precip_sep_mm": (0.0, 1500.0),
    "precip_antecedent_spring_mm": (0.0, 2500.0),
    "seasonal_precip_djf_mm": (0.0, 3000.0),
    "precip_djf_lag1_mm": (0.0, 3000.0),
    # Sea Surface Temperature in degC (tropical Pacific Niño 3.4 range: 15.0C to 35.0C)
    "sst_degc": (15.0, 35.0),
    "nino34_aso_sst_degc": (15.0, 35.0),
    # ONI/SST anomalies in degC (records span ~[-3, +3], physical bounds [-4.5, +4.5])
    "oni_anomaly_degc": (-4.5, 4.5),
    "oni_aso_degc": (-4.5, 4.5),
    "oni_jas_degc": (-4.5, 4.5),
    "oni_jja_degc": (-4.5, 4.5),
    "anomaly_degc": (-5.0, 5.0),
    "nino34_aso_anom_degc": (-5.0, 5.0),
    "nino34_oct_anom_degc": (-5.0, 5.0),
    "nino34_aug_anom_degc": (-5.0, 5.0),
    # Trends in degC
    "oni_trend_aso_jas_degc": (-3.0, 3.0),
    "oni_trend_aso_jja_degc": (-4.0, 4.0),
    "nino34_trend_oct_aug_degc": (-3.5, 3.5),
    # Standardized anomalies (z-scores)
    "seasonal_precip_zscore": (-5.0, 5.0),
    "precip_oct_zscore": (-5.0, 5.0),
}

# Maximum plausible month-over-month rate of change due to physical inertia
MAX_STEP_CHANGE: dict[str, float] = {
    "sst_degc": 2.5,  # degC/month (Pacific ocean thermal inertia)
    "nino34_aso_sst_degc": 2.5,
    "oni_anomaly_degc": 1.2,  # degC/month (smoothed 3-month running mean changes gradually)
    "oni_aso_degc": 1.2,
    "precip_mm": 800.0,  # mm/month
    "precip_oct_mm": 800.0,
    "anomaly_degc": 2.5,
    "nino34_aso_anom_degc": 2.5,
}

# Standard telemetry sentinel values used in environmental sensor networks
TELEMETRY_SENTINELS: set[float] = {
    -999.0,
    -9999.0,
    -99.9,
    -99.0,
    999.9,
    9999.0,
    -99999.0,
    1e20,
    -1e20,
}


class TransparentStatisticalChecker:
    """Transparent, deterministic rule-based checks for climate telemetry integrity."""

    def __init__(
        self,
        bounds: dict[str, tuple[float, float]] | None = None,
        max_step: dict[str, float] | None = None,
        sentinels: set[float] | None = None,
    ) -> None:
        self.bounds = bounds or PHYSICAL_BOUNDS
        self.max_step = max_step or MAX_STEP_CHANGE
        self.sentinels = sentinels or TELEMETRY_SENTINELS

    def check_impossible_values(self, df: pd.DataFrame) -> list[AnomalyDetection]:
        """Check for values outside physically plausible oceanographic and meteorological limits."""
        anomalies: list[AnomalyDetection] = []
        for col, (min_val, max_val) in self.bounds.items():
            if col not in df.columns:
                continue

            series = pd.to_numeric(df[col], errors="coerce")
            violations = series[(series < min_val) | (series > max_val)]

            for idx, val in violations.items():
                ts = str(df.loc[idx, "date"]) if "date" in df.columns else str(idx)
                sev: AnomalySeverity = (
                    "CRITICAL" if (val < min_val - 5.0 or val > max_val + 10.0) else "HIGH"
                )
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=col,
                        observed_value=float(val),
                        expected_range=f"[{min_val}, {max_val}]",
                        anomaly_type="IMPOSSIBLE_VALUE",
                        severity=sev,
                        classification="DATA_QUALITY_ANOMALY"
                        if val in self.sentinels
                        else "SUSPICIOUS_ANOMALY",
                        suspicion_score=0.88,
                        detail=(
                            f"Value {val} for '{col}' violates physical domain bounds "
                            f"[{min_val}, {max_val}]. Physical impossibility indicated."
                        ),
                        is_confirmed_malicious=False,
                    )
                )
        return anomalies

    def check_sudden_changes(self, df: pd.DataFrame) -> list[AnomalyDetection]:
        """Check for sudden step changes exceeding physical thermal/mass transport inertia."""
        anomalies: list[AnomalyDetection] = []
        if len(df) < 2:
            return anomalies

        df_sorted = df.copy()
        if "date" in df_sorted.columns:
            df_sorted = df_sorted.sort_values("date")
        elif "season_year" in df_sorted.columns:
            df_sorted = df_sorted.sort_values("season_year")

        # Determine time scale between records: monthly vs annual
        is_annual = False
        if "season_year" in df_sorted.columns and "month" not in df_sorted.columns:
            is_annual = True
        elif "date" in df_sorted.columns:
            try:
                dts = pd.to_datetime(df_sorted["date"], errors="coerce")
                if len(dts.dropna()) >= 2:
                    median_diff_days = dts.diff().dropna().median().total_seconds() / 86400
                    if median_diff_days > 150:
                        is_annual = True
            except Exception as err:
                logger.debug("Could not parse date intervals: %s", err)

        for col, max_delta in self.max_step.items():
            if col not in df_sorted.columns:
                continue

            # Scale allowable step limit for annual seasonal transitions (e.g. 12-month evolution)
            effective_max_delta = max_delta * 2.8 if is_annual else max_delta

            raw_series = pd.to_numeric(df_sorted[col], errors="coerce")
            # Mask out impossible values and sentinels so recovery steps don't trigger false alarms
            bounds = self.bounds.get(col)
            if bounds:
                valid_mask = (
                    (raw_series >= bounds[0])
                    & (raw_series <= bounds[1])
                    & (~raw_series.isin(self.sentinels))
                )
                series = raw_series.where(valid_mask)
            else:
                series = raw_series.where(~raw_series.isin(self.sentinels))

            diffs = series.diff().abs()
            jumps = diffs[diffs > effective_max_delta]

            for idx, delta in jumps.items():
                ts = (
                    str(df_sorted.loc[idx, "date"])
                    if "date" in df_sorted.columns
                    else str(df_sorted.loc[idx, "season_year"])
                    if "season_year" in df_sorted.columns
                    else str(idx)
                )
                val = float(df_sorted.loc[idx, col])
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=col,
                        observed_value=val,
                        expected_range=f"Step |delta| <= {effective_max_delta:.1f}",
                        anomaly_type="SUDDEN_CHANGE",
                        severity="HIGH" if delta > 2 * effective_max_delta else "MEDIUM",
                        classification="SUSPICIOUS_ANOMALY",
                        suspicion_score=min(0.95, 0.65 + float(delta / effective_max_delta) * 0.1),
                        detail=(
                            f"Step change |delta| = {delta:.2f} in '{col}' "
                            f"exceeds rate limit of {effective_max_delta:.1f}."
                        ),
                        is_confirmed_malicious=False,
                    )
                )
        return anomalies

    def check_missingness(self, df: pd.DataFrame) -> list[AnomalyDetection]:
        """Check for null, NaN, infinite, or known telemetry sentinel values."""
        anomalies: list[AnomalyDetection] = []
        for col in df.columns:
            if col in {
                "date",
                "year",
                "season_year",
                "month",
                "season",
                "split",
                "spatial_region_id",
                "spatial_region_name",
                "forecast_issue_date",
                "target_period",
                "target_start_date",
                "target_end_date",
            }:
                continue

            series = df[col]
            # Check null / NaN
            null_mask = series.isna()
            for idx in series[null_mask].index:
                # Accept expected boundary nulls on lag features for the very first historical row
                if idx == df.index[0] and ("lag" in col.lower()):
                    continue

                ts = (
                    str(df.loc[idx, "date"])
                    if "date" in df.columns
                    else str(df.loc[idx, "season_year"])
                    if "season_year" in df.columns
                    else str(idx)
                )
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=col,
                        observed_value=None,
                        expected_range="Non-null numeric",
                        anomaly_type="MISSING_DATA",
                        severity="MEDIUM",
                        classification="DATA_QUALITY_ANOMALY",
                        suspicion_score=0.45,
                        detail=f"Missing observation (null/NaN) in telemetry column '{col}'.",
                        is_confirmed_malicious=False,
                    )
                )

            # Check sentinel values
            numeric_series = pd.to_numeric(series, errors="coerce")
            sentinel_mask = numeric_series.isin(self.sentinels)
            for idx, val in numeric_series[sentinel_mask].items():
                ts = (
                    str(df.loc[idx, "date"])
                    if "date" in df.columns
                    else str(df.loc[idx, "season_year"])
                    if "season_year" in df.columns
                    else str(idx)
                )
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=col,
                        observed_value=float(val),
                        expected_range="Valid environmental measurement",
                        anomaly_type="MISSING_DATA",
                        severity="HIGH",
                        classification="DATA_QUALITY_ANOMALY",
                        suspicion_score=0.55,
                        detail=f"Telemetry sentinel code {val} detected in column '{col}'.",
                        is_confirmed_malicious=False,
                    )
                )
        return anomalies

    def check_timestamp_irregularities(
        self,
        df: pd.DataFrame,
        date_col: str = "date",
    ) -> list[AnomalyDetection]:
        """Check for non-monotonic timestamps, duplicates, or gaps in calendar series."""
        anomalies: list[AnomalyDetection] = []
        if date_col not in df.columns or len(df) == 0:
            return anomalies

        dates = pd.to_datetime(df[date_col], errors="coerce")

        # Invalid datetime format
        invalid_mask = dates.isna()
        for idx in df[invalid_mask].index:
            anomalies.append(
                AnomalyDetection(
                    timestamp=str(df.loc[idx, date_col]),
                    feature_name=date_col,
                    observed_value=str(df.loc[idx, date_col]),
                    expected_range="Valid ISO YYYY-MM or YYYY-MM-DD",
                    anomaly_type="TIMESTAMP_IRREGULARITY",
                    severity="HIGH",
                    classification="DATA_QUALITY_ANOMALY",
                    suspicion_score=0.60,
                    detail=f"Malformed timestamp string '{df.loc[idx, date_col]}'.",
                    is_confirmed_malicious=False,
                )
            )

        valid_dates = dates.dropna()
        # Duplicate timestamps
        duplicates = valid_dates[valid_dates.duplicated(keep=False)]
        for idx, dt in duplicates.items():
            anomalies.append(
                AnomalyDetection(
                    timestamp=dt.strftime("%Y-%m-%d"),
                    feature_name=date_col,
                    observed_value=dt.strftime("%Y-%m-%d"),
                    expected_range="Unique sequential timestamp",
                    anomaly_type="TIMESTAMP_IRREGULARITY",
                    severity="MEDIUM",
                    classification="DATA_QUALITY_ANOMALY",
                    suspicion_score=0.50,
                    detail=f"Duplicate timestamp {dt.strftime('%Y-%m-%d')} detected at row {idx}.",
                    is_confirmed_malicious=False,
                )
            )

        # Non-monotonicity
        if not valid_dates.is_monotonic_increasing:
            diffs = valid_dates.diff()
            negative_steps = diffs[diffs < pd.Timedelta(0)]
            for idx in negative_steps.index:
                anomalies.append(
                    AnomalyDetection(
                        timestamp=valid_dates.loc[idx].strftime("%Y-%m-%d"),
                        feature_name=date_col,
                        observed_value=valid_dates.loc[idx].strftime("%Y-%m-%d"),
                        expected_range="Strictly monotonic forward progression",
                        anomaly_type="TIMESTAMP_IRREGULARITY",
                        severity="HIGH",
                        classification="SUSPICIOUS_ANOMALY",
                        suspicion_score=0.75,
                        detail="Non-monotonic sequence: timestamp regressed chronologically.",
                        is_confirmed_malicious=False,
                    )
                )

        return anomalies

    def check_replayed_observations(
        self,
        df: pd.DataFrame,
        value_cols: list[str] | None = None,
        min_freeze_len: int = 3,
    ) -> list[AnomalyDetection]:
        """Check for frozen sensors (constant values over multiple months) and replayed blocks.

        In natural dynamic systems like ocean/atmospheric fluid flows, sensor variance is strictly
        positive. Exact duplicate floating point sequences or identical consecutive values over
        >= 3 months indicate frozen telemetry, dead sensor, or temporal replay.
        """
        anomalies: list[AnomalyDetection] = []
        if len(df) < min_freeze_len:
            return anomalies

        if value_cols is None:
            value_cols = [
                c
                for c in df.columns
                if c
                in {
                    "oni_anomaly_degc",
                    "oni_aso_degc",
                    "sst_degc",
                    "precip_mm",
                    "nino34_aso_sst_degc",
                    "anomaly_degc",
                }
            ]

        for col in value_cols:
            series = pd.to_numeric(df[col], errors="coerce")
            # Rolling window variance check for dead sensor / constant telemetry
            is_constant = series.rolling(min_freeze_len).apply(
                lambda w: len(set(w)) == 1, raw=False
            )
            freeze_indices = is_constant[is_constant == 1.0].index

            for idx in freeze_indices:
                ts = str(df.loc[idx, "date"]) if "date" in df.columns else str(idx)
                val = float(series.loc[idx])
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=col,
                        observed_value=val,
                        expected_range=f"Natural variance (no {min_freeze_len}-step freeze)",
                        anomaly_type="REPLAY_OBSERVATION",
                        severity="HIGH",
                        classification="SUSPICIOUS_ANOMALY",
                        suspicion_score=0.82,
                        detail=(
                            f"Sensor freeze or replay detected: '{col}' remained identical "
                            f"({val}) for >= {min_freeze_len} consecutive periods."
                        ),
                        is_confirmed_malicious=False,
                    )
                )

        # Replay sequence check: look for identical blocks of 3+ rows matching historical windows
        if len(df) >= 12 and len(value_cols) >= 1:
            check_col = value_cols[0]
            values = pd.to_numeric(df[check_col], errors="coerce").values
            window_size = 4
            seen_windows: dict[tuple[float, ...], int] = {}
            for i in range(len(values) - window_size + 1):
                window = tuple(np.round(values[i : i + window_size], 4))
                if any(np.isnan(window)):
                    continue
                if window in seen_windows:
                    orig_idx = seen_windows[window]
                    ts = str(df.iloc[i]["date"]) if "date" in df.columns else str(i)
                    anomalies.append(
                        AnomalyDetection(
                            timestamp=ts,
                            feature_name=check_col,
                            observed_value=list(window),
                            expected_range="Original non-replayed sequence",
                            anomaly_type="REPLAY_OBSERVATION",
                            severity="HIGH",
                            classification="SUSPICIOUS_ANOMALY",
                            suspicion_score=0.85,
                            detail=(
                                f"Sequence replay attack detected: {window_size}-period window "
                                f"at index {i} matches historical window at index {orig_idx}."
                            ),
                            is_confirmed_malicious=False,
                        )
                    )
                else:
                    seen_windows[window] = i

        return anomalies

    def check_cross_source_inconsistencies(
        self,
        df_oni: pd.DataFrame,
        df_nino34: pd.DataFrame,
        max_discrepancy: float = 0.50,
    ) -> list[AnomalyDetection]:
        """Check for inconsistencies between NOAA ONI and NOAA Niño 3.4 SST anomaly.

        By meteorological definition, ONI is the 3-month running mean of ERSST.v5 Niño 3.4 SST
        anomalies. When clean, |ONI_t - Mean(Niño3.4_{t-1..t+1})| <= 0.35 degC.
        A divergence > 0.50 degC reveals selective data poisoning, calibration drift, or spoofing.
        """
        anomalies: list[AnomalyDetection] = []
        if "date" not in df_oni.columns or "date" not in df_nino34.columns:
            return anomalies

        oni_sub = df_oni[["date", "oni_anomaly_degc"]].dropna().copy()
        nino_col = "anomaly_degc" if "anomaly_degc" in df_nino34.columns else "sst_degc"
        nino_sub = df_nino34[["date", nino_col]].dropna().copy()

        merged = pd.merge(oni_sub, nino_sub, on="date", how="inner").sort_values("date")
        if len(merged) < 3:
            return anomalies

        # Compute 3-month centered rolling mean of Niño 3.4 anomaly
        rolling_nino = merged[nino_col].rolling(3, center=True).mean()
        discrepancy = (merged["oni_anomaly_degc"] - rolling_nino).abs()

        divergent = discrepancy[discrepancy > max_discrepancy]
        for idx, diff in divergent.items():
            dt = str(merged.loc[idx, "date"])
            oni_val = float(merged.loc[idx, "oni_anomaly_degc"])
            nino_val = float(rolling_nino.loc[idx])
            anomalies.append(
                AnomalyDetection(
                    timestamp=dt,
                    feature_name="oni_vs_nino34_teleconnection",
                    observed_value={"oni": oni_val, "nino34_rolling3": round(nino_val, 3)},
                    expected_range=f"|ONI - Niño3.4| <= {max_discrepancy} degC",
                    anomaly_type="CROSS_SOURCE_INCONSISTENCY",
                    severity="CRITICAL" if diff > 1.0 else "HIGH",
                    classification="POTENTIAL_ADVERSARIAL_PERTURBATION"
                    if diff > 1.0
                    else "SUSPICIOUS_ANOMALY",
                    suspicion_score=min(0.98, 0.75 + float(diff) * 0.15),
                    detail=(
                        f"Cross-sensor teleconnection inconsistency: ONI anomaly ({oni_val:.2f}C) "
                        f"diverges from 3-month Niño 3.4 mean ({nino_val:.2f}C) by {diff:.2f}C, "
                        f"violating physical cross-source coherence limit ({max_discrepancy}C)."
                    ),
                    is_confirmed_malicious=False,
                )
            )

        return anomalies


class BaselineAnomalyDetector:
    """Robust multivariate anomaly detector based on Mahalanobis distance.

    Fits on clean historical training feature distributions to capture the joint
    covariance structure between teleconnection signals (ONI, SST, antecedent rainfall).
    Triggers an anomaly only if an observation violates joint multivariate covariance,
    identifying subtle stealthy perturbations that evade univariate 1D thresholds.
    """

    def __init__(self, critical_quantile: float = 0.99) -> None:
        self.critical_quantile = critical_quantile
        self.mean_: np.ndarray | None = None
        self.inv_cov_: np.ndarray | None = None
        self.feature_names_: list[str] = []
        self.threshold_: float = 0.0

    def fit(self, df_train: pd.DataFrame, feature_cols: list[str]) -> BaselineAnomalyDetector:
        """Fit empirical mean vector and robust inverted covariance matrix on clean baseline."""
        self.feature_names_ = [f for f in feature_cols if f in df_train.columns]
        if not self.feature_names_:
            raise ValueError(
                f"None of requested feature columns {feature_cols} found in train dataframe."
            )

        x = df_train[self.feature_names_].dropna().values.astype(float)
        if len(x) < len(self.feature_names_):
            # Not enough samples for full rank covariance; use ridge regularized diagonal
            self.mean_ = np.mean(x, axis=0)
            cov = np.cov(x, rowvar=False) if len(x) > 1 else np.eye(len(self.feature_names_))
            cov = cov + 1e-4 * np.eye(len(self.feature_names_))
            self.inv_cov_ = np.linalg.pinv(cov)
        else:
            self.mean_ = np.mean(x, axis=0)
            cov = np.cov(x, rowvar=False) + 1e-4 * np.eye(len(self.feature_names_))
            self.inv_cov_ = np.linalg.pinv(cov)

        p = len(self.feature_names_)
        # Chi-Square critical threshold with p degrees of freedom at quantile (e.g. 0.99)
        self.threshold_ = float(chi2.ppf(self.critical_quantile, df=p))
        logger.info(
            "BaselineAnomalyDetector fitted on %d samples, %d features. Chi2 threshold: %.2f",
            len(x),
            p,
            self.threshold_,
        )
        return self

    def compute_mahalanobis_distance(self, x: np.ndarray) -> np.ndarray:
        """Compute squared Mahalanobis distance D_M^2 for feature vectors."""
        if self.mean_ is None or self.inv_cov_ is None:
            raise RuntimeError("BaselineAnomalyDetector must be fitted before computing distances.")

        diff = x - self.mean_
        dm2 = np.sum((diff @ self.inv_cov_) * diff, axis=1)
        return dm2

    def detect_anomalies(self, df: pd.DataFrame) -> list[AnomalyDetection]:
        """Detect multivariate covariance anomalies in candidate dataset."""
        anomalies: list[AnomalyDetection] = []
        if self.mean_ is None or self.inv_cov_ is None:
            return anomalies

        valid_df = df[self.feature_names_].copy()
        valid_df_numeric = valid_df.apply(pd.to_numeric, errors="coerce")
        has_nans = valid_df_numeric.isna().any(axis=1)

        clean_indices = valid_df_numeric[~has_nans].index
        if len(clean_indices) == 0:
            return anomalies

        x = valid_df_numeric.loc[clean_indices].values.astype(float)
        dm2_values = self.compute_mahalanobis_distance(x)

        for idx, dm2 in zip(clean_indices, dm2_values, strict=False):
            if dm2 > self.threshold_:
                ts = str(df.loc[idx, "date"]) if "date" in df.columns else str(idx)
                p_val = 1.0 - float(chi2.cdf(dm2, df=len(self.feature_names_)))
                suspicion = min(0.96, 0.70 + float(dm2 / (2 * self.threshold_)) * 0.15)
                anomalies.append(
                    AnomalyDetection(
                        timestamp=ts,
                        feature_name=f"multivariate_covariance_{len(self.feature_names_)}d",
                        observed_value=round(float(dm2), 2),
                        expected_range=f"D_M^2 <= {self.threshold_:.2f} (Chi2 p=0.01)",
                        anomaly_type="MULTIVARIATE_OUTLIER",
                        severity="HIGH" if dm2 > 2 * self.threshold_ else "MEDIUM",
                        classification="POTENTIAL_ADVERSARIAL_PERTURBATION",
                        suspicion_score=round(suspicion, 3),
                        detail=(
                            f"Multivariate outlier: D_M^2={dm2:.2f} > {self.threshold_:.2f} "
                            f"(p={p_val:.2e}). Joint teleconnection covariance violated."
                        ),
                        is_confirmed_malicious=False,
                    )
                )

        return anomalies


class DefensiveInspectionEngine:
    """Master defensive data-anomaly inspection engine for ENSO Shield.

    Coordinates transparent statistical checks and baseline multivariate detection.
    Aggregates findings, assigns calibrated suspicion scores, and guarantees that
    unconfirmed anomalies are never labelled as malicious.
    """

    def __init__(
        self,
        checker: TransparentStatisticalChecker | None = None,
        baseline_detector: BaselineAnomalyDetector | None = None,
    ) -> None:
        self.checker = checker or TransparentStatisticalChecker()
        self.baseline_detector = baseline_detector

    def inspect_dataset(
        self,
        df: pd.DataFrame,
        series_id: str = "telemetry_stream",
        df_cross_reference: pd.DataFrame | None = None,
    ) -> DefensiveInspectionReport:
        """Run all transparent statistical checks and optional baseline detector on dataset."""
        all_anomalies: list[AnomalyDetection] = []
        check_summaries: list[DefenseCheckResult] = []

        # 1. Impossible values
        anom_impossible = self.checker.check_impossible_values(df)
        all_anomalies.extend(anom_impossible)
        check_summaries.append(
            DefenseCheckResult(
                check_name="Impossible Values Check",
                passed=len(anom_impossible) == 0,
                anomaly_count=len(anom_impossible),
                anomalies=anom_impossible,
            )
        )

        # 2. Sudden changes
        anom_sudden = self.checker.check_sudden_changes(df)
        all_anomalies.extend(anom_sudden)
        check_summaries.append(
            DefenseCheckResult(
                check_name="Sudden Physical Change Limits",
                passed=len(anom_sudden) == 0,
                anomaly_count=len(anom_sudden),
                anomalies=anom_sudden,
            )
        )

        # 3. Missingness & sentinels
        anom_missing = self.checker.check_missingness(df)
        all_anomalies.extend(anom_missing)
        check_summaries.append(
            DefenseCheckResult(
                check_name="Missingness and Sentinel Screening",
                passed=len(anom_missing) == 0,
                anomaly_count=len(anom_missing),
                anomalies=anom_missing,
            )
        )

        # 4. Timestamp irregularities
        anom_ts = self.checker.check_timestamp_irregularities(df)
        all_anomalies.extend(anom_ts)
        check_summaries.append(
            DefenseCheckResult(
                check_name="Timestamp Monotonicity and Continuity",
                passed=len(anom_ts) == 0,
                anomaly_count=len(anom_ts),
                anomalies=anom_ts,
            )
        )

        # 5. Replayed observations & telemetry freezes
        anom_replay = self.checker.check_replayed_observations(df)
        all_anomalies.extend(anom_replay)
        check_summaries.append(
            DefenseCheckResult(
                check_name="Sensor Freeze and Sequence Replay Check",
                passed=len(anom_replay) == 0,
                anomaly_count=len(anom_replay),
                anomalies=anom_replay,
            )
        )

        # 6. Cross-source inconsistencies (if companion source provided)
        if df_cross_reference is not None:
            anom_cross = self.checker.check_cross_source_inconsistencies(df, df_cross_reference)
            all_anomalies.extend(anom_cross)
            check_summaries.append(
                DefenseCheckResult(
                    check_name="Cross-Source Teleconnection Consistency",
                    passed=len(anom_cross) == 0,
                    anomaly_count=len(anom_cross),
                    anomalies=anom_cross,
                )
            )

        # 7. Baseline multivariate detector (if configured and fitted)
        baseline_score: float | None = None
        if self.baseline_detector is not None:
            anom_baseline = self.baseline_detector.detect_anomalies(df)
            # Only add multivariate anomalies if they improve / provide evidence beyond 1D checks
            all_anomalies.extend(anom_baseline)
            baseline_score = float(len(anom_baseline))
            check_summaries.append(
                DefenseCheckResult(
                    check_name="Baseline Multivariate Covariance Detector",
                    passed=len(anom_baseline) == 0,
                    anomaly_count=len(anom_baseline),
                    anomalies=anom_baseline,
                )
            )

        # Determine overall calibrated classification
        overall_classification: AnomalyClassification = "CLEAN_BENCHMARK"
        if all_anomalies:
            classifications = [a.classification for a in all_anomalies]
            if "POTENTIAL_ADVERSARIAL_PERTURBATION" in classifications:
                overall_classification = "POTENTIAL_ADVERSARIAL_PERTURBATION"
            elif "SUSPICIOUS_ANOMALY" in classifications:
                overall_classification = "SUSPICIOUS_ANOMALY"
            elif "DATA_QUALITY_ANOMALY" in classifications:
                overall_classification = "DATA_QUALITY_ANOMALY"
            else:
                overall_classification = "MEASUREMENT_NOISE"

        passed = len(all_anomalies) == 0
        summary = (
            f"Defensive screening passed for '{series_id}' ({len(check_summaries)} checks clean)."
            if passed
            else (
                f"Defensive screening flagged {len(all_anomalies)} anomalies in '{series_id}'. "
                f"Overall status: {overall_classification}. "
                "Notice: unconfirmed anomalies are not labelled as confirmed attack."
            )
        )

        return DefensiveInspectionReport(
            series_id=series_id,
            total_records=len(df),
            passed=passed,
            anomaly_count=len(all_anomalies),
            anomalies=all_anomalies,
            check_summaries=check_summaries,
            baseline_detector_score=baseline_score,
            overall_classification=overall_classification,
            summary=summary,
        )
