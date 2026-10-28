"""Sensitivity analysis across alternative rainfall-deficit drought thresholds."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ml.evaluation.metrics import compute_expected_calibration_error, compute_probabilistic_metrics
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import DEFAULT_PREDICTOR_FEATURES, TrainingConfig
from ml.training.models import LogisticRegressionPredictor, XGBoostPredictor

logger = logging.getLogger("enso_ml.experiments.thresholds")

DEFAULT_THRESHOLD_PERCENTILES: list[float] = [10.0, 15.0, 20.0, 25.0, 33.33, 50.0]


class ThresholdSensitivityRecord(BaseModel):
    """Performance evaluation for an alternative rainfall-deficit threshold."""

    percentile: float
    threshold_rainfall_mm: float
    event_count: int
    empirical_base_rate: float
    brier_score_baseline: float
    brier_score_logistic: float
    bss_logistic: float
    brier_score_xgboost: float
    bss_xgboost: float
    ece_logistic: float
    ece_xgboost: float
    best_performing_architecture: str


class ThresholdSensitivityReport(BaseModel):
    """Machine-readable report summarizing threshold sensitivity analysis."""

    dataset_fingerprint: str
    sample_size: int
    eval_records: list[ThresholdSensitivityRecord]
    highest_skill_threshold_logistic: float = Field(
        description="Percentile threshold yielding highest BSS for Logistic Regression."
    )
    highest_skill_threshold_xgboost: float = Field(
        description="Percentile threshold yielding highest BSS for XGBoost."
    )
    scientific_summary: list[str]


def run_threshold_sensitivity_suite(
    df: pd.DataFrame,
    rainfall_column: str = "seasonal_precip_djf_mm",
    percentiles: list[float] | None = None,
    dataset_fingerprint: str = "unknown",
    feature_columns: list[str] | None = None,
    min_train_seasons: int = 5,
    random_seed: int = 42,
) -> ThresholdSensitivityReport:
    """Evaluate model performance across a spectrum of rainfall deficit percentiles."""
    eval_percentiles = percentiles or DEFAULT_THRESHOLD_PERCENTILES
    feats = feature_columns or list(DEFAULT_PREDICTOR_FEATURES)
    available_features = [f for f in feats if f in df.columns]

    df_sorted = df.sort_values("season_year").reset_index(drop=True)
    total_seasons = len(df_sorted)
    initial_window = min(min_train_seasons, max(2, total_seasons - 2))

    records: list[ThresholdSensitivityRecord] = []

    for pct in eval_percentiles:
        # 1. Compute threshold strictly on training data window
        train_slice = df_sorted.iloc[:initial_window]
        thresh_mm = float(np.percentile(train_slice[rainfall_column], pct))

        # 2. Formulate binary target for this threshold
        y_all = (df_sorted[rainfall_column] <= thresh_mm).astype(int).to_numpy()
        event_cnt = int(np.sum(y_all))
        base_rate = float(np.mean(y_all))

        oof_records: list[dict[str, Any]] = []

        for t in range(initial_window, total_seasons):
            train_fold = df_sorted.iloc[:t]
            test_row = df_sorted.iloc[t : t + 1]

            # Re-estimate threshold strictly on past seasons
            train_precip = train_fold[rainfall_column].to_numpy(dtype=float)
            fold_thresh = float(np.percentile(train_precip, pct))

            y_train = (train_precip <= fold_thresh).astype(int)
            y_test = int(test_row[rainfall_column].iloc[0] <= fold_thresh)

            # Baseline
            base_model = ClimatologyBaseline().fit(y_train)
            p_base = float(base_model.predict_proba(1)[0, 1])

            # Logistic Regression
            cfg_lr = TrainingConfig(
                target_column="temp_target",
                feature_columns=available_features,
                random_seed=random_seed,
            )
            lr_model = LogisticRegressionPredictor().fit(
                X=train_fold[available_features],
                y=y_train,
                config=cfg_lr,
            )
            p_lr = float(lr_model.predict_proba(test_row[available_features])[0, 1])

            # XGBoost
            xgb_model = XGBoostPredictor(
                feature_names=available_features,
                random_seed=random_seed,
            ).fit(
                X=train_fold[available_features],
                y=y_train,
            )
            p_xgb = float(xgb_model.predict_proba(test_row[available_features])[0, 1])

            oof_records.append(
                {
                    "y_true": y_test,
                    "prob_base": p_base,
                    "prob_lr": p_lr,
                    "prob_xgb": p_xgb,
                }
            )

        oof_df = pd.DataFrame(oof_records)
        y_true = oof_df["y_true"].to_numpy(dtype=int)
        y_base = oof_df["prob_base"].to_numpy(dtype=float)
        y_lr = oof_df["prob_lr"].to_numpy(dtype=float)
        y_xgb = oof_df["prob_xgb"].to_numpy(dtype=float)

        m_base = compute_probabilistic_metrics(y_true, y_base, y_prob_reference=y_base)
        m_lr = compute_probabilistic_metrics(y_true, y_lr, y_prob_reference=y_base)
        m_xgb = compute_probabilistic_metrics(y_true, y_xgb, y_prob_reference=y_base)

        ece_lr = compute_expected_calibration_error(y_true, y_lr)
        ece_xgb = compute_expected_calibration_error(y_true, y_xgb)

        bs_base = m_base.brier_score
        bs_lr = m_lr.brier_score
        bss_lr = m_lr.brier_skill_score or 0.0
        bs_xgb = m_xgb.brier_score
        bss_xgb = m_xgb.brier_skill_score or 0.0

        if bs_lr <= bs_xgb and bs_lr <= bs_base:
            best_arch = "LogisticRegression"
        elif bs_xgb <= bs_lr and bs_xgb <= bs_base:
            best_arch = "XGBoost"
        else:
            best_arch = "ClimatologyBaseline"

        records.append(
            ThresholdSensitivityRecord(
                percentile=round(pct, 2),
                threshold_rainfall_mm=round(thresh_mm, 2),
                event_count=event_cnt,
                empirical_base_rate=round(base_rate, 4),
                brier_score_baseline=round(bs_base, 5),
                brier_score_logistic=round(bs_lr, 5),
                bss_logistic=round(bss_lr, 4),
                brier_score_xgboost=round(bs_xgb, 5),
                bss_xgboost=round(bss_xgb, 4),
                ece_logistic=round(ece_lr, 5),
                ece_xgboost=round(ece_xgb, 5),
                best_performing_architecture=best_arch,
            )
        )

    best_lr_rec = max(records, key=lambda r: r.bss_logistic)
    best_xgb_rec = max(records, key=lambda r: r.bss_xgboost)

    t_lr = best_lr_rec.threshold_rainfall_mm
    t_xgb = best_xgb_rec.threshold_rainfall_mm
    summary = [
        (
            f"Highest BSS for Logistic Regression is at {best_lr_rec.percentile}th percentile: "
            f"BSS={best_lr_rec.bss_logistic:+.4f} (thresh={t_lr:.1f}mm)."
        ),
        (
            f"Highest BSS for XGBoost is at {best_xgb_rec.percentile}th percentile: "
            f"BSS={best_xgb_rec.bss_xgboost:+.4f} (thresh={t_xgb:.1f}mm)."
        ),
        (
            "Predictive skill generally diminishes at extreme tails due to severe sample rarity, "
            "while tercile and median deficit formulations exhibit higher sample support."
        ),
    ]

    return ThresholdSensitivityReport(
        dataset_fingerprint=dataset_fingerprint,
        sample_size=total_seasons,
        eval_records=records,
        highest_skill_threshold_logistic=best_lr_rec.percentile,
        highest_skill_threshold_xgboost=best_xgb_rec.percentile,
        scientific_summary=summary,
    )
