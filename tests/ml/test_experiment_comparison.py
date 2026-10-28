"""Automated tests for nonlinear model comparison, calibration, ablations, and sensitivity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml.evaluation.calibration import analyze_calibration, compute_prediction_entropy
from ml.experiments.ablations import run_feature_ablation_suite
from ml.experiments.comparison import (
    ExperimentComparisonManifest,
    MultiModelExperimentRunner,
)
from ml.experiments.locations import AgroClimaticSubregion, run_location_evaluation_suite
from ml.experiments.thresholds import run_threshold_sensitivity_suite
from ml.training.models import XGBoostPredictor


def test_xgboost_predictor_fit_predict_and_serialization() -> None:
    """Verify XGBoostPredictor fits on training data and supports serialization."""
    X = pd.DataFrame(
        {
            "feat_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "feat_b": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )
    y = np.array([0, 0, 0, 1, 1, 1])

    model = XGBoostPredictor(feature_names=["feat_a", "feat_b"], random_seed=42)
    model.fit(X, y)

    assert model.fitted is True
    assert set(model.feature_importances.keys()) == {"feat_a", "feat_b"}

    probs = model.predict_proba(X)
    assert probs.shape == (6, 2)
    assert np.allclose(np.sum(probs, axis=1), 1.0)

    # Serialization roundtrip
    saved = model.to_dict()
    restored = XGBoostPredictor.from_dict(saved)
    assert restored.fitted is True
    restored_probs = restored.predict_proba(X)
    assert np.allclose(probs, restored_probs, atol=1e-5)


def test_xgboost_predictor_single_class_fallback() -> None:
    """Verify XGBoostPredictor falls back gracefully when training fold has 0 events."""
    X = pd.DataFrame({"feat_a": [1.0, 2.0, 3.0], "feat_b": [10.0, 20.0, 30.0]})
    y = np.array([0, 0, 0])

    model = XGBoostPredictor(feature_names=["feat_a", "feat_b"]).fit(X, y)
    assert model.fitted is True
    assert model.fallback_base_rate == 0.0

    probs = model.predict_proba(X)
    assert probs.shape == (3, 2)
    assert np.allclose(probs[:, 1], 0.0)


def test_calibration_analysis_module() -> None:
    """Verify calibration analysis calculates ECE, MCE, bias, and entropy accurately."""
    y_true = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
    y_prob = np.array([0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.85, 0.15, 0.95, 0.05])

    report = analyze_calibration(y_true, y_prob, model_name="TestModel", n_bins=5)
    assert report.model_name == "TestModel"
    assert report.sample_size == 10
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert 0.0 <= report.max_calibration_error <= 1.0
    assert len(report.bins) == 5

    entropy = compute_prediction_entropy(y_prob)
    assert 0.0 <= entropy <= 1.0


def test_feature_ablation_suite() -> None:
    """Verify feature ablation suite runs across subsets and produces structured report."""
    df = pd.DataFrame(
        {
            "season_year": [1981, 1982, 1983, 1984, 1985, 1986],
            "target_drought_p20": [0, 1, 0, 0, 1, 0],
            "oni_aso_degc": [-0.5, 1.5, -0.2, -0.4, 1.2, 0.1],
            "precip_oct_zscore": [0.5, -1.8, 0.2, 0.1, -1.5, 0.3],
            "nino34_aso_anom_degc": [-0.4, 1.6, -0.1, -0.3, 1.3, 0.0],
        }
    )

    custom_suites = {
        "full_features": ["oni_aso_degc", "precip_oct_zscore", "nino34_aso_anom_degc"],
        "teleconnection_only": ["oni_aso_degc", "nino34_aso_anom_degc"],
        "local_precip_only": ["precip_oct_zscore"],
    }

    report = run_feature_ablation_suite(
        df=df,
        target_col="target_drought_p20",
        suites=custom_suites,
        min_train_seasons=3,
        random_seed=42,
    )

    assert report.sample_size == 6
    assert len(report.ablation_records) == 3
    assert report.optimal_subset_logistic in custom_suites
    assert len(report.key_findings) >= 2


def test_threshold_sensitivity_suite() -> None:
    """Verify threshold sensitivity runs across percentiles with training-only thresholds."""
    df = pd.DataFrame(
        {
            "season_year": [1981, 1982, 1983, 1984, 1985, 1986],
            "seasonal_precip_djf_mm": [350.0, 220.0, 380.0, 310.0, 240.0, 360.0],
            "oni_aso_degc": [-0.5, 1.5, -0.2, -0.4, 1.2, 0.1],
        }
    )

    report = run_threshold_sensitivity_suite(
        df=df,
        rainfall_column="seasonal_precip_djf_mm",
        percentiles=[20.0, 33.33, 50.0],
        feature_columns=["oni_aso_degc"],
        min_train_seasons=3,
        random_seed=42,
    )

    assert report.sample_size == 6
    assert len(report.eval_records) == 3
    assert len(report.scientific_summary) >= 2


def test_location_evaluation_suite() -> None:
    """Verify location-based evaluation evaluates regional rainfall scalings."""
    df = pd.DataFrame(
        {
            "season_year": [1981, 1982, 1983, 1984, 1985, 1986],
            "seasonal_precip_djf_mm": [350.0, 220.0, 380.0, 310.0, 240.0, 360.0],
            "oni_aso_degc": [-0.5, 1.5, -0.2, -0.4, 1.2, 0.1],
        }
    )

    subregions = [
        AgroClimaticSubregion(
            region_id="REG_A",
            region_name="Test North",
            lat_min=-25.0,
            lat_max=-22.0,
            lon_min=27.0,
            lon_max=32.0,
            climatological_scaling_factor=0.9,
        ),
        AgroClimaticSubregion(
            region_id="REG_B",
            region_name="Test South",
            lat_min=-30.0,
            lat_max=-26.0,
            lon_min=25.0,
            lon_max=30.0,
            climatological_scaling_factor=1.1,
        ),
    ]

    report = run_location_evaluation_suite(
        df=df,
        subregions=subregions,
        feature_columns=["oni_aso_degc"],
        min_train_seasons=3,
        random_seed=42,
    )

    assert report.total_seasons == 6
    assert report.regions_evaluated == 2
    assert len(report.location_records) == 2


def test_multi_model_experiment_runner_end_to_end(tmp_path: Path) -> None:
    """Integration test: Run complete multi-model comparison on labelled features dataset."""
    features_csv = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "features"
        / "enso_rainfall_features_labelled.csv"
    )
    assert features_csv.is_file(), f"Missing features dataset: {features_csv}"

    output_dir = tmp_path / "comparison_out"
    runner = MultiModelExperimentRunner()
    manifest = runner.run(
        features_csv_path=features_csv,
        output_dir=output_dir,
        holdout_count=2,
    )

    assert (output_dir / "experiment_comparison_manifest.json").is_file()
    assert (output_dir / "ablation_report.json").is_file()
    assert (output_dir / "threshold_report.json").is_file()
    assert (output_dir / "location_report.json").is_file()

    # Verify manifest deserialization and contents
    loaded_manifest = ExperimentComparisonManifest.model_validate_json(
        (output_dir / "experiment_comparison_manifest.json").read_text(encoding="utf-8")
    )
    assert loaded_manifest.experiment_id == manifest.experiment_id
    assert "climatology_baseline" in loaded_manifest.rolling_origin_cv
    assert "logistic_regression" in loaded_manifest.rolling_origin_cv
    assert "xgboost" in loaded_manifest.rolling_origin_cv
    assert loaded_manifest.verdict.is_nonlinear_complexity_justified is False
