"""Automated tests for feature engineering, reference distribution, and leakage guards."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.features.config import TargetConfig
from ml.features.data_dictionary import FEATURE_DATA_DICTIONARY, generate_data_dictionary_markdown
from ml.features.generator import FeatureGenerator
from ml.features.leakage import (
    PartitionOverlapError,
    TargetLeakageDetector,
    TargetLeakageError,
    TemporalOrderViolationError,
)
from ml.features.pipeline import FeaturePipeline
from ml.features.target import ReferenceDistribution, TargetComputationError


@pytest.fixture
def synthetic_climate_records() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate 10 years (1980-1989, 120 months) of synthetic climate time series with known values.

    Deterministic formulation:
    * Month m in year y (y in 1980..1989, m in 1..12)
    * Precipitation:
      - Summer months (Dec, Jan, Feb): high rainfall (100.0 + (y - 1980) * 10.0) mm/month
      - October: (30.0 + (y - 1980) * 2.0) mm/month
      - September: 15.0 mm/month
      - Other months: 5.0 mm/month
    * NOAA ONI:
      - Seasonal anomaly = 0.2 * (y - 1980) - 0.8
    * NOAA Nino 3.4:
      - Monthly SST = 26.0 + 0.1 * (y - 1980)
      - Monthly anomaly = 0.15 * (y - 1980) - 0.6
    """
    precip_rows = []
    oni_rows = []
    nino_rows = []

    seasons_order = [
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

    for y in range(1980, 1990):
        y_idx = y - 1980
        for m in range(1, 13):
            # Monthly precipitation
            if m in (12, 1, 2):
                p = 100.0 + y_idx * 10.0
            elif m == 10:
                p = 30.0 + y_idx * 2.0
            elif m == 9:
                p = 15.0
            else:
                p = 5.0

            precip_rows.append(
                {
                    "year": y,
                    "month": m,
                    "date": f"{y}-{m:02d}",
                    "precip_mm": float(p),
                    "lat_min": -30.0,
                    "lat_max": -22.0,
                    "lon_min": 25.0,
                    "lon_max": 32.0,
                }
            )

            # ONI
            seas = seasons_order[m - 1]
            oni_val = round(0.2 * y_idx - 0.8, 2)
            oni_rows.append(
                {
                    "year": y,
                    "month": m,
                    "date": f"{y}-{m:02d}",
                    "season": seas,
                    "oni_anomaly_degc": float(oni_val),
                }
            )

            # Nino 3.4
            sst_val = round(26.0 + 0.1 * y_idx, 2)
            anom_val = round(0.15 * y_idx - 0.6, 2)
            nino_rows.append(
                {
                    "year": y,
                    "month": m,
                    "date": f"{y}-{m:02d}",
                    "sst_degc": float(sst_val),
                    "anomaly_degc": float(anom_val),
                }
            )

    df_p = pd.DataFrame(precip_rows)
    df_oni = pd.DataFrame(oni_rows)
    df_nino = pd.DataFrame(nino_rows)
    return df_p, df_oni, df_nino


def test_feature_generator_exact_analytical_values(
    synthetic_climate_records: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    """Verify that FeatureGenerator matches exact analytical mathematical values."""
    df_p, df_oni, df_nino = synthetic_climate_records
    generator = FeatureGenerator()
    df_features = generator.extract_seasonal_features(df_p, df_oni, df_nino)

    # Seasons should span 1981 to 1989 (9 seasons)
    assert len(df_features) == 9
    assert list(df_features["season_year"]) == list(range(1981, 1990))

    # Test Season 1985 (Y=1985, prior_y=1984, y_idx=4):
    row_1985 = df_features[df_features["season_year"] == 1985].iloc[0]

    # Predictors are evaluated at Year Y-1 = 1984 (y_idx = 4)
    # ONI: 0.2 * 4 - 0.8 = 0.0
    assert row_1985["oni_aso_degc"] == pytest.approx(0.0, abs=1e-3)
    assert row_1985["oni_jas_degc"] == pytest.approx(0.0, abs=1e-3)
    assert row_1985["oni_trend_aso_jas_degc"] == pytest.approx(0.0, abs=1e-3)

    # Nino 3.4 SST in 1984: 26.0 + 0.1 * 4 = 26.4
    assert row_1985["nino34_aso_sst_degc"] == pytest.approx(26.4, abs=1e-3)

    # Nino 3.4 Anomaly in 1984: 0.15 * 4 - 0.6 = 0.0
    assert row_1985["nino34_aso_anom_degc"] == pytest.approx(0.0, abs=1e-3)
    assert row_1985["nino34_oct_anom_degc"] == pytest.approx(0.0, abs=1e-3)

    # October rainfall in 1984 (y_idx=4): 30.0 + 4 * 2.0 = 38.0 mm
    assert row_1985["precip_oct_mm"] == pytest.approx(38.0, abs=1e-3)
    assert row_1985["precip_sep_mm"] == pytest.approx(15.0, abs=1e-3)
    assert row_1985["precip_antecedent_spring_mm"] == pytest.approx(53.0, abs=1e-3)

    # Target DJF for Season 1985:
    # Dec 1984 (y_idx=4): 100.0 + 4 * 10 = 140.0 mm
    # Jan 1985 (y_idx=5): 100.0 + 5 * 10 = 150.0 mm
    # Feb 1985 (y_idx=5): 100.0 + 5 * 10 = 150.0 mm
    # Total DJF = 140 + 150 + 150 = 440.0 mm
    assert row_1985["seasonal_precip_djf_mm"] == pytest.approx(440.0, abs=1e-3)

    # Timeline verification
    assert row_1985["forecast_issue_date"] == "1984-11-01"
    assert row_1985["target_period"] == "1984-12_to_1985-02"
    assert row_1985["lead_time_days"] == 30


def test_reference_distribution_training_only_fitting() -> None:
    """Verify ReferenceDistribution computes statistics strictly on training data."""
    # Create 5 synthetic training seasons with known linear rainfall
    # DJF: [200, 250, 300, 350, 400], Mean: 300.0, Var (ddof=1): 25000/4 = 6250
    # Std: sqrt(6250) = 79.05694...
    train_df = pd.DataFrame(
        {
            "season_year": [1982, 1983, 1984, 1985, 1986],
            "seasonal_precip_djf_mm": [200.0, 250.0, 300.0, 350.0, 400.0],
            "precip_oct_mm": [20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )

    ref = ReferenceDistribution.fit(train_df, TargetConfig(drought_quantile=0.20))
    assert ref.n_train == 5
    assert ref.mean_seasonal_precip_mm == pytest.approx(300.0, abs=1e-3)
    assert ref.std_seasonal_precip_mm == pytest.approx(math.sqrt(6250.0), abs=1e-3)
    assert ref.median_seasonal_precip_mm == pytest.approx(300.0, abs=1e-3)
    assert ref.min_seasonal_precip_mm == 200.0
    assert ref.max_seasonal_precip_mm == 400.0

    # Test transform on unseen test data
    test_df = pd.DataFrame(
        {
            "season_year": [1987, 1988],
            "seasonal_precip_djf_mm": [210.0, 500.0],
            "precip_oct_mm": [40.0, 40.0],
        }
    )

    transformed = ref.transform(test_df)
    # Verify standardization uses training mu=300 and sigma=79.057
    expected_z_1987 = (210.0 - 300.0) / math.sqrt(6250.0)
    assert transformed.iloc[0]["seasonal_precip_zscore"] == pytest.approx(expected_z_1987, abs=1e-3)

    # 500mm is non-drought (target_drought_p20 = 0)
    assert transformed.iloc[1]["target_drought_p20"] == 0


def test_reference_invariance_against_future_data_tampering() -> None:
    """Verify perturbing future/test data produces zero change in training thresholds."""
    train_df = pd.DataFrame(
        {
            "season_year": [1982, 1983, 1984, 1985, 1986],
            "seasonal_precip_djf_mm": [220.0, 280.0, 310.0, 340.0, 390.0],
            "precip_oct_mm": [30.0, 35.0, 40.0, 45.0, 50.0],
        }
    )
    test_df = pd.DataFrame(
        {
            "season_year": [1987, 1988],
            "seasonal_precip_djf_mm": [250.0, 450.0],
            "precip_oct_mm": [25.0, 55.0],
        }
    )

    is_invariant = TargetLeakageDetector.verify_climatology_leakage_absence(
        train_df=train_df,
        future_df=test_df,
        fit_fn=ReferenceDistribution.fit,
    )
    assert is_invariant is True


def test_timeline_integrity_rejects_lookahead_violation() -> None:
    """Verify that issue date occurring after or on target onset raises error."""
    # Lookahead violation: issue date is 1982-12-05, while target period begins 1982-12-01!
    corrupt_df = pd.DataFrame(
        {
            "forecast_issue_date": ["1982-12-05"],
            "target_period": ["1982-12_to_1983-02"],
        }
    )
    with pytest.raises(TemporalOrderViolationError, match="Lookahead violation"):
        TargetLeakageDetector.validate_timeline_integrity(corrupt_df)


def test_predictor_isolation_rejects_target_leakage() -> None:
    """Verify that including target variables in predictor features triggers TargetLeakageError."""
    # Attempting to use seasonal DJF rainfall or binary target as predictor
    predictors_with_leak = ["oni_aso_degc", "nino34_oct_anom_degc", "target_drought_p20"]
    with pytest.raises(TargetLeakageError, match="Target leakage detected"):
        TargetLeakageDetector.validate_predictor_feature_isolation(predictors_with_leak)

    clean_predictors = ["oni_aso_degc", "nino34_oct_anom_degc", "precip_oct_mm"]
    TargetLeakageDetector.validate_predictor_feature_isolation(clean_predictors)


def test_partition_isolation_detects_overlap_and_ordering() -> None:
    """Verify that partition isolation rejects overlapping or inverted chronological splits."""
    # Case 1: Overlapping season (1985 in both train and val)
    overlap_df = pd.DataFrame(
        {
            "season_year": [1982, 1983, 1984, 1985, 1985, 1986],
            "split": ["train", "train", "train", "train", "val", "val"],
        }
    )
    with pytest.raises(PartitionOverlapError, match="Overlap detected"):
        TargetLeakageDetector.validate_partition_isolation(overlap_df)

    # Case 2: Inverted chronological order (train has 1990 while val has 1986)
    inverted_df = pd.DataFrame(
        {
            "season_year": [1982, 1990, 1986, 1987],
            "split": ["train", "train", "val", "val"],
        }
    )
    with pytest.raises(PartitionOverlapError, match="Chronological violation"):
        TargetLeakageDetector.validate_partition_isolation(inverted_df)


def test_missing_data_prohibits_silent_imputation(
    synthetic_climate_records: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    """Verify that missing observations are not silently imputed and prevent corrupted records."""
    df_p, df_oni, df_nino = synthetic_climate_records

    # Inject NaN into October rainfall for year 1984
    df_p_corrupt = df_p.copy()
    mask = (df_p_corrupt["year"] == 1984) & (df_p_corrupt["month"] == 10)
    df_p_corrupt.loc[mask, "precip_mm"] = np.nan

    generator = FeatureGenerator()
    df_features = generator.extract_seasonal_features(df_p_corrupt, df_oni, df_nino)

    # Season 1985 (which depends on October 1984) must be excluded, NOT filled with 0.0 or mean!
    assert 1985 not in df_features["season_year"].tolist()


def test_negative_precipitation_rejected() -> None:
    """Verify that negative rainfall values trigger TargetComputationError."""
    corrupt_train_df = pd.DataFrame(
        {
            "season_year": [1982, 1983, 1984],
            "seasonal_precip_djf_mm": [300.0, -50.0, 350.0],
            "precip_oct_mm": [40.0, 30.0, 20.0],
        }
    )
    with pytest.raises(TargetComputationError, match="negative rainfall"):
        ReferenceDistribution.fit(corrupt_train_df)


def test_data_dictionary_completeness() -> None:
    """Verify that every defined variable has a complete specification in the data dictionary."""
    assert len(FEATURE_DATA_DICTIONARY) >= 20

    roles = {v.role for v in FEATURE_DATA_DICTIONARY}
    assert "identifier" in roles
    assert "metadata" in roles
    assert "predictor" in roles
    assert "target" in roles
    assert "partition" in roles

    md_text = generate_data_dictionary_markdown()
    assert "# ENSO Shield: Feature and Target Data Dictionary" in md_text
    assert "oni_aso_degc" in md_text
    assert "target_drought_p20" in md_text
    assert "Zero Lookahead" in md_text


def test_end_to_end_pipeline_with_real_fixtures(tmp_path: Path) -> None:
    """Integration test: Execute full pipeline from cleaned fixtures to labelled output."""
    cleaned_dir = Path(__file__).resolve().parents[2] / "data" / "cleaned"
    output_dir = tmp_path / "features"
    manifest_dir = tmp_path / "provenance"

    pipeline = FeaturePipeline()
    df_labelled, ref_dist, manifest = pipeline.run(
        cleaned_dir=cleaned_dir,
        output_dir=output_dir,
        manifest_dir=manifest_dir,
    )

    # Check output dataset and fitted reference distribution
    assert len(df_labelled) == 7
    assert ref_dist.n_train == 7
    assert ref_dist.tau_drought_p20_mm > 0.0
    assert "target_drought_p20" in df_labelled.columns
    assert "target_below_normal_p33" in df_labelled.columns
    assert "seasonal_precip_zscore" in df_labelled.columns
    assert "precip_oct_zscore" in df_labelled.columns

    # Verify binary target values are strictly in {0, 1}
    assert set(df_labelled["target_drought_p20"].unique()).issubset({0, 1})
    assert set(df_labelled["target_below_normal_p33"].unique()).issubset({0, 1})

    # Verify 1983 (1982/83 Super El Nino drought) is flagged as drought
    row_1983 = df_labelled[df_labelled["season_year"] == 1983].iloc[0]
    assert row_1983["target_drought_p20"] == 1
    assert row_1983["target_below_normal_p33"] == 1
    assert row_1983["seasonal_precip_zscore"] < -1.5

    # Check persisted files
    assert (output_dir / "enso_rainfall_features_labelled.csv").is_file()
    assert (output_dir / "climatology_reference_distribution.json").is_file()
    assert (output_dir / "DATA_DICTIONARY.md").is_file()
    assert (manifest_dir / "enso_rainfall_features_provenance.json").is_file()

    # Verify manifest integrity
    assert manifest.validation_status == "PASSED"
    assert manifest.record_count == 7
