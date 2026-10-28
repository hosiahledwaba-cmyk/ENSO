"""Automated tests for climate model training, baseline benchmarking, and evaluation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from ml.evaluation.metrics import (
    compute_brier_score,
    compute_brier_skill_score,
    compute_log_loss,
    compute_murphy_decomposition,
)
from ml.inference.predictor import EnsoRiskPredictor, InvalidFeatureValueError, MissingFeatureError
from ml.registry.manifest import ModelManifest
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import TrainingConfig
from ml.training.cross_validation import RollingOriginEvaluator
from ml.training.experiment import ClimateModelExperiment
from ml.training.models import LogisticRegressionPredictor


def test_brier_score_and_bss_analytical_values() -> None:
    """Verify Brier Score and BSS match exact analytical calculations."""
    y_true = np.array([1, 0])
    y_prob = np.array([0.8, 0.2])
    # BS = ((0.8 - 1)^2 + (0.2 - 0)^2) / 2 = (0.04 + 0.04) / 2 = 0.04
    bs = compute_brier_score(y_true, y_prob)
    assert bs == pytest.approx(0.04, abs=1e-5)

    y_ref = np.array([0.5, 0.5])
    # BS_ref = ((0.5 - 1)^2 + (0.5 - 0)^2) / 2 = 0.25
    bs_ref = compute_brier_score(y_true, y_ref)
    assert bs_ref == pytest.approx(0.25, abs=1e-5)

    # BSS = 1 - (0.04 / 0.25) = 1 - 0.16 = 0.84
    bss = compute_brier_skill_score(bs, bs_ref)
    assert bss == pytest.approx(0.84, abs=1e-5)


def test_murphy_decomposition_algebraic_identity() -> None:
    """Verify Murphy (1973) algebraic identity: BS = Reliability - Resolution + Uncertainty."""
    y_true = np.array([1, 0, 1, 0, 0, 1, 0, 0, 0, 1])
    # Categorical/binned probability forecasts where within-bin variance is zero
    y_prob = np.array([0.9, 0.1, 0.9, 0.1, 0.3, 0.7, 0.3, 0.1, 0.5, 0.5])

    bs = compute_brier_score(y_true, y_prob)
    murphy = compute_murphy_decomposition(y_true, y_prob, n_bins=5)

    # In discrete Murphy (1973) partition, BS = Rel - Res + Unc exactly
    reconstructed_bs = murphy.reliability - murphy.resolution + murphy.uncertainty
    assert reconstructed_bs == pytest.approx(bs, abs=1e-4)


def test_log_loss_computation() -> None:
    """Verify log loss handles binary extremes and matches cross-entropy definition."""
    y_true = np.array([1, 0])
    y_prob = np.array([0.5, 0.5])
    # - (1*ln(0.5) + 1*ln(0.5)) / 2 = - ln(0.5) = ln(2) ~= 0.693147
    loss = compute_log_loss(y_true, y_prob)
    assert loss == pytest.approx(math.log(2.0), abs=1e-4)


def test_climatology_baseline_fitting_and_serialization() -> None:
    """Verify ClimatologyBaseline estimates base rate, SE, and serializes cleanly."""
    y = np.array([1, 0, 0, 0, 0])  # 1 event out of 5
    baseline = ClimatologyBaseline().fit(y)

    assert baseline.base_rate == pytest.approx(0.20, abs=1e-4)
    assert baseline.event_count == 1
    assert baseline.n_train == 5
    # SE = sqrt(0.2 * 0.8 / 5) = sqrt(0.032) ~= 0.178885
    assert baseline.standard_error == pytest.approx(math.sqrt(0.032), abs=1e-3)

    probs = baseline.predict_proba(3)
    assert probs.shape == (3, 2)
    assert np.allclose(probs[:, 1], 0.20)
    assert np.allclose(probs[:, 0], 0.80)

    # Test serialization roundtrip
    saved_dict = baseline.to_dict()
    restored = ClimatologyBaseline.from_dict(saved_dict)
    assert restored.base_rate == baseline.base_rate
    assert np.allclose(restored.predict_proba(2), baseline.predict_proba(2))


def test_logistic_regression_fitting_and_roundtrip() -> None:
    """Verify LogisticRegressionPredictor scales features, fits weights, and restores state."""
    # Create synthetic feature matrix
    X = pd.DataFrame(
        {
            "feat_a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "feat_b": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )
    y = np.array([0, 0, 0, 1, 1, 1])

    cfg = TrainingConfig(feature_columns=["feat_a", "feat_b"], c_regularization=1.0)
    model = LogisticRegressionPredictor().fit(X, y, config=cfg)

    assert model.fitted is True
    assert set(model.coefficients.keys()) == {"feat_a", "feat_b"}
    assert model.scaler_mean["feat_a"] == pytest.approx(3.5, abs=1e-3)

    probs = model.predict_proba(X)
    assert probs.shape == (6, 2)
    assert np.allclose(np.sum(probs, axis=1), 1.0)
    # Higher feature values should yield higher probability of class 1
    assert probs[5, 1] > probs[0, 1]

    # Test serialization roundtrip
    saved = model.to_dict()
    restored = LogisticRegressionPredictor.from_dict(saved)
    restored_probs = restored.predict_proba(X)
    assert np.allclose(probs, restored_probs, atol=1e-5)


def test_logistic_regression_single_class_fallback() -> None:
    """Verify single-class training fold falls back safely to empirical base rate."""
    X = pd.DataFrame({"feat_a": [1.0, 2.0, 3.0], "feat_b": [10.0, 20.0, 30.0]})
    y = np.array([0, 0, 0])  # Zero positive events

    cfg = TrainingConfig(feature_columns=["feat_a", "feat_b"])
    model = LogisticRegressionPredictor().fit(X, y, config=cfg)

    assert model.fitted is True
    assert model.fallback_base_rate == 0.0
    probs = model.predict_proba(X)
    assert np.allclose(probs[:, 1], 0.0)


def test_rolling_origin_evaluator_walk_forward() -> None:
    """Verify RollingOriginEvaluator enforces strict chronology with zero future lookahead."""
    df = pd.DataFrame(
        {
            "season_year": [1981, 1982, 1983, 1984, 1985, 1986],
            "target_drought_p20": [0, 1, 0, 0, 1, 0],
            "oni_aso_degc": [-0.5, 1.5, -0.2, -0.4, 1.2, 0.1],
        }
    )

    cfg = TrainingConfig(
        target_column="target_drought_p20",
        feature_columns=["oni_aso_degc"],
        min_train_seasons=3,
    )

    evaluator = RollingOriginEvaluator(cfg)
    oof_df, base_metrics, model_metrics = evaluator.evaluate(df)

    # Seasons 1984, 1985, 1986 are evaluated out-of-fold (3 seasons)
    assert len(oof_df) == 3
    assert list(oof_df["season_year"]) == [1984, 1985, 1986]
    assert base_metrics.sample_size == 3
    assert model_metrics.sample_size == 3
    assert model_metrics.brier_score >= 0.0


def test_climate_model_experiment_end_to_end(tmp_path: Path) -> None:
    """Integration test: Run ClimateModelExperiment on generated feature dataset."""
    features_csv = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "features"
        / "enso_rainfall_features_labelled.csv"
    )
    assert features_csv.is_file(), f"Missing features dataset: {features_csv}"

    model_dir = tmp_path / "test_model"
    cfg = TrainingConfig(random_seed=42)

    experiment = ClimateModelExperiment(cfg)
    _model, _baseline, manifest = experiment.run(
        features_csv_path=features_csv,
        output_model_dir=model_dir,
        holdout_seasons_count=2,
    )

    # Check that model artifacts are persisted
    assert (model_dir / "model_manifest.json").is_file()
    assert (model_dir / "baseline.json").is_file()
    assert (model_dir / "logistic_regression.json").is_file()
    assert (model_dir / "evaluation_summary.json").is_file()

    # Verify manifest fields
    assert manifest.dataset_id == "enso_rainfall_features_labelled"
    assert len(manifest.training_seasons) == 5
    assert len(manifest.holdout_seasons) == 2
    assert manifest.target_variable == "target_drought_p20"
    assert len(manifest.feature_schema) == len(cfg.feature_columns)

    # Reload manifest
    reloaded_manifest = ModelManifest.from_json(model_dir / "model_manifest.json")
    assert reloaded_manifest.model_id == manifest.model_id
    assert reloaded_manifest.beats_baseline_on_holdout == manifest.beats_baseline_on_holdout


def test_enso_risk_predictor_validation_and_errors(tmp_path: Path) -> None:
    """Verify EnsoRiskPredictor explicitly validates features and traps missing/invalid inputs."""
    features_csv = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "features"
        / "enso_rainfall_features_labelled.csv"
    )
    model_dir = tmp_path / "prod_model"
    experiment = ClimateModelExperiment()
    experiment.run(features_csv_path=features_csv, output_model_dir=model_dir)

    predictor = EnsoRiskPredictor(model_dir)

    valid_input: dict[str, Any] = {
        "oni_aso_degc": 1.6,
        "oni_trend_aso_jas_degc": 0.5,
        "oni_trend_aso_jja_degc": 0.8,
        "nino34_aso_sst_degc": 28.28,
        "nino34_aso_anom_degc": 1.55,
        "nino34_oct_anom_degc": 2.0,
        "nino34_trend_oct_aug_degc": 0.95,
        "precip_oct_mm": 25.0,
        "precip_oct_zscore": -1.72,
        "precip_antecedent_spring_mm": 37.4,
    }

    # 1. Valid prediction succeeds
    res = predictor.predict_risk(valid_input)
    assert 0.0 <= res["drought_probability"] <= 1.0
    assert res["binary_prediction"] in {0, 1}
    assert res["risk_ratio"] > 0.0
    assert "top_contributing_factors" in res

    # 2. Missing feature triggers MissingFeatureError
    corrupt_missing = valid_input.copy()
    del corrupt_missing["oni_aso_degc"]
    with pytest.raises(MissingFeatureError, match="Input missing required predictor features"):
        predictor.predict_risk(corrupt_missing)

    # 3. None / null value triggers InvalidFeatureValueError
    corrupt_null = valid_input.copy()
    corrupt_null["precip_oct_mm"] = None
    with pytest.raises(InvalidFeatureValueError, match="cannot be None/null"):
        predictor.predict_risk(corrupt_null)

    # 4. Non-numeric value triggers InvalidFeatureValueError
    corrupt_str = valid_input.copy()
    corrupt_str["nino34_aso_sst_degc"] = "twenty_eight"
    with pytest.raises(InvalidFeatureValueError, match="must be numeric"):
        predictor.predict_risk(corrupt_str)

    # 5. NaN value triggers InvalidFeatureValueError
    corrupt_nan = valid_input.copy()
    corrupt_nan["precip_oct_zscore"] = float("nan")
    with pytest.raises(InvalidFeatureValueError, match="contains NaN"):
        predictor.predict_risk(corrupt_nan)
