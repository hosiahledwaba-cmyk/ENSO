"""Tests for defensive data-anomaly detection module and transparent statistical checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.defense.detector import (
    BaselineAnomalyDetector,
    DefensiveInspectionEngine,
    TransparentStatisticalChecker,
)


@pytest.fixture
def clean_monthly_series() -> pd.DataFrame:
    """Fixture providing clean monthly series with valid physical ranges."""
    dates = pd.date_range("2020-01-01", periods=12, freq="MS").strftime("%Y-%m").tolist()
    return pd.DataFrame(
        {
            "date": dates,
            "sst_degc": [26.1, 26.3, 26.7, 27.2, 27.5, 27.3, 26.9, 26.6, 26.5, 26.4, 26.5, 26.6],
            "oni_anomaly_degc": [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.1, 0.0, -0.1, -0.2, -0.2, -0.1],
            "precip_mm": [120.5, 95.2, 60.1, 30.0, 10.5, 5.0, 2.0, 4.5, 15.0, 45.0, 85.0, 110.0],
        }
    )


def test_clean_series_passes_all_checks(clean_monthly_series: pd.DataFrame) -> None:
    """Clean reference series must produce 0 false alarms."""
    engine = DefensiveInspectionEngine()
    report = engine.inspect_dataset(clean_monthly_series, series_id="clean_test")

    assert report.passed is True
    assert report.anomaly_count == 0
    assert report.overall_classification == "CLEAN_BENCHMARK"
    assert len(report.anomalies) == 0


def test_impossible_values_detected(clean_monthly_series: pd.DataFrame) -> None:
    """Detect impossible values (negative rain, extreme SST, out-of-range ONI)."""
    df = clean_monthly_series.copy()
    df.loc[2, "precip_mm"] = -25.0  # Physically impossible negative precipitation
    df.loc[5, "sst_degc"] = 42.0  # Physically impossible ocean surface temperature
    df.loc[8, "oni_anomaly_degc"] = 6.5  # Impossible ONI anomaly

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_impossible_values(df)

    assert len(anomalies) == 3
    features = [a.feature_name for a in anomalies]
    assert "precip_mm" in features
    assert "sst_degc" in features
    assert "oni_anomaly_degc" in features

    # Critical invariant: must NEVER be marked confirmed malicious
    for a in anomalies:
        assert a.is_confirmed_malicious is False
        assert a.anomaly_type == "IMPOSSIBLE_VALUE"
        assert a.severity in {"HIGH", "CRITICAL"}


def test_sudden_step_change_detected(clean_monthly_series: pd.DataFrame) -> None:
    """Detect sudden month-over-month jumps that violate physical thermal inertia."""
    df = clean_monthly_series.copy()
    # Normal SST month-to-month change is ~0.3 C; jump 4.0 C in 1 month is physically impossible
    df.loc[4, "sst_degc"] = 31.8

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_sudden_changes(df)

    assert len(anomalies) >= 1
    assert any(
        a.feature_name == "sst_degc" and a.anomaly_type == "SUDDEN_CHANGE" for a in anomalies
    )
    for a in anomalies:
        assert a.is_confirmed_malicious is False
        assert a.classification == "SUSPICIOUS_ANOMALY"


def test_missingness_and_telemetry_sentinels(clean_monthly_series: pd.DataFrame) -> None:
    """Detect null/NaN values and environmental telemetry sentinels like -999.0."""
    df = clean_monthly_series.copy()
    df.loc[1, "precip_mm"] = np.nan
    df.loc[6, "sst_degc"] = -999.0  # Standard environmental sentinel code

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_missingness(df)

    assert len(anomalies) == 2
    types = [a.anomaly_type for a in anomalies]
    assert all(t == "MISSING_DATA" for t in types)
    for a in anomalies:
        assert a.is_confirmed_malicious is False
        assert a.classification == "DATA_QUALITY_ANOMALY"


def test_timestamp_irregularities(clean_monthly_series: pd.DataFrame) -> None:
    """Detect non-monotonic dates, duplicate timestamps, and malformed strings."""
    df = clean_monthly_series.copy()
    # Duplicate timestamp
    df.loc[3, "date"] = df.loc[2, "date"]
    # Non-monotonic regression
    df.loc[7, "date"] = "2019-01"

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_timestamp_irregularities(df)

    assert len(anomalies) >= 2
    for a in anomalies:
        assert a.anomaly_type == "TIMESTAMP_IRREGULARITY"
        assert a.is_confirmed_malicious is False


def test_replayed_observations_and_sensor_freeze() -> None:
    """Detect sensor freeze where telemetry flatlines identically across multiple periods."""
    dates = pd.date_range("2021-01-01", periods=6, freq="MS").strftime("%Y-%m").tolist()
    # Sensor flatlined at exactly 27.12 C for 4 months (variance = 0)
    df = pd.DataFrame(
        {
            "date": dates,
            "sst_degc": [26.8, 27.12, 27.12, 27.12, 27.12, 26.9],
        }
    )

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_replayed_observations(df, min_freeze_len=3)

    assert len(anomalies) >= 1
    assert any(a.anomaly_type == "REPLAY_OBSERVATION" for a in anomalies)
    for a in anomalies:
        assert a.is_confirmed_malicious is False
        assert a.classification == "SUSPICIOUS_ANOMALY"


def test_cross_source_inconsistency_detected() -> None:
    """Detect divergence between NOAA ONI anomaly and NOAA Niño 3.4 SST anomaly."""
    dates = pd.date_range("2021-01-01", periods=6, freq="MS").strftime("%Y-%m").tolist()
    # ONI indicates strong El Niño (+1.8C), but local Niño 3.4 anomaly is cool (-0.6C)
    # Divergence > 0.5C indicates teleconnection breakdown or selective spoofing
    df_oni = pd.DataFrame({"date": dates, "oni_anomaly_degc": [0.2, 0.4, 1.8, 1.9, 1.7, 1.2]})
    df_nino = pd.DataFrame({"date": dates, "anomaly_degc": [0.1, 0.3, -0.6, -0.5, 0.0, 0.2]})

    checker = TransparentStatisticalChecker()
    anomalies = checker.check_cross_source_inconsistencies(df_oni, df_nino, max_discrepancy=0.50)

    assert len(anomalies) >= 1
    assert any(a.anomaly_type == "CROSS_SOURCE_INCONSISTENCY" for a in anomalies)
    for a in anomalies:
        assert a.is_confirmed_malicious is False
        assert a.classification in {"SUSPICIOUS_ANOMALY", "POTENTIAL_ADVERSARIAL_PERTURBATION"}


def test_baseline_multivariate_detector_improves_detection() -> None:
    """Verify that BaselineAnomalyDetector flags subtle joint covariance distortions.

    Even when individual features stay within 1D univariate physical bounds,
    an unnatural combination (e.g. extreme high SST + extreme negative ONI)
    violates multivariate Mahalanobis distance.
    """
    # Fit baseline on correlated clean data
    rng = np.random.default_rng(42)
    n = 30
    oni = rng.normal(0.0, 0.8, n)
    # Natural physical correlation: SST anomaly is strongly correlated with ONI
    sst_anom = oni + rng.normal(0.0, 0.15, n)
    df_train = pd.DataFrame({"oni": oni, "sst_anom": sst_anom})

    detector = BaselineAnomalyDetector(critical_quantile=0.99)
    detector.fit(df_train, feature_cols=["oni", "sst_anom"])

    # Test clean sample (conforms to covariance)
    df_test_clean = pd.DataFrame({"oni": [0.5], "sst_anom": [0.52]})
    anom_clean = detector.detect_anomalies(df_test_clean)
    assert len(anom_clean) == 0

    # Test unnatural anti-correlated perturbation (both within 1D bounds [-3, +3] but jointly discordant)
    df_test_poisoned = pd.DataFrame({"oni": [2.2], "sst_anom": [-2.1]})
    anom_poisoned = detector.detect_anomalies(df_test_poisoned)

    assert len(anom_poisoned) == 1
    assert anom_poisoned[0].anomaly_type == "MULTIVARIATE_OUTLIER"
    assert anom_poisoned[0].is_confirmed_malicious is False
    assert anom_poisoned[0].classification == "POTENTIAL_ADVERSARIAL_PERTURBATION"
