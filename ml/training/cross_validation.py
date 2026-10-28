"""Chronological rolling-origin evaluation without lookahead leakage."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ml.evaluation.metrics import compute_probabilistic_metrics
from ml.evaluation.models import ProbabilisticMetrics
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import TrainingConfig
from ml.training.models import LogisticRegressionPredictor

logger = logging.getLogger("enso_ml.training.cross_validation")


class RollingOriginEvaluator:
    """Executes walk-forward rolling-origin evaluation over chronological climate seasons.

    Guarantees:
    * Preprocessing, scaling, and models are fitted strictly on past seasons [1..t].
    * Step t+1 is evaluated out-of-sample with zero future lookahead.
    * No shuffling or random k-fold cross-validation is permitted.
    """

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def evaluate(
        self,
        df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, ProbabilisticMetrics, ProbabilisticMetrics]:
        """Perform expanding-window walk-forward evaluation across chronological seasons.

        Parameters
        ----------
        df : pd.DataFrame
            Dataset containing 'season_year', target_column, and feature_columns.

        Returns
        -------
        tuple[pd.DataFrame, ProbabilisticMetrics, ProbabilisticMetrics]
            Out-of-fold predictions DataFrame, baseline metrics, and model metrics.
        """
        cfg = self.config
        target_col = cfg.target_column
        feature_cols = cfg.feature_columns

        # Enforce chronological ordering
        df_sorted = df.sort_values("season_year").reset_index(drop=True)
        total_seasons = len(df_sorted)
        if total_seasons < 3:
            raise ValueError(
                f"Insufficient seasons (N={total_seasons}) for rolling-origin CV (minimum: 3)."
            )

        initial_window = min(cfg.min_train_seasons, max(2, total_seasons - 2))
        oof_records: list[dict[str, Any]] = []

        logger.info(
            "Starting rolling-origin evaluation: %d seasons, initial window=%d seasons",
            total_seasons,
            initial_window,
        )

        for t in range(initial_window, total_seasons):
            # Training window: [0 .. t-1]
            train_fold = df_sorted.iloc[:t]
            # Test step: season at index t
            test_row = df_sorted.iloc[t : t + 1]

            target_year = int(test_row["season_year"].iloc[0])
            y_train = train_fold[target_col].to_numpy(dtype=int)
            y_test = int(test_row[target_col].iloc[0])

            # 1. Fit Baseline strictly on past seasons
            baseline = ClimatologyBaseline().fit(y_train)
            p_baseline = float(baseline.predict_proba(1)[0, 1])

            # 2. Fit Logistic Regression strictly on past seasons
            model = LogisticRegressionPredictor().fit(
                X=train_fold[feature_cols],
                y=y_train,
                config=cfg,
            )
            p_model = float(model.predict_proba(test_row[feature_cols])[0, 1])

            oof_records.append(
                {
                    "season_year": target_year,
                    "y_true": y_test,
                    "prob_baseline": round(p_baseline, 4),
                    "prob_model": round(p_model, 4),
                }
            )

        oof_df = pd.DataFrame(oof_records)
        y_true = oof_df["y_true"].to_numpy(dtype=int)
        y_base = oof_df["prob_baseline"].to_numpy(dtype=float)
        y_model = oof_df["prob_model"].to_numpy(dtype=float)

        # Compute evaluation metrics over aggregated out-of-fold predictions
        metrics_base = compute_probabilistic_metrics(
            y_true=y_true,
            y_prob=y_base,
            y_prob_reference=y_base,
            decision_threshold=cfg.decision_threshold,
        )

        metrics_model = compute_probabilistic_metrics(
            y_true=y_true,
            y_prob=y_model,
            y_prob_reference=y_base,
            decision_threshold=cfg.decision_threshold,
        )

        logger.info(
            "Rolling-origin complete (%d seasons): Baseline BS=%.4f, Model BS=%.4f (BSS=%.4f)",
            len(oof_df),
            metrics_base.brier_score,
            metrics_model.brier_score,
            metrics_model.brier_skill_score or 0.0,
        )
        return oof_df, metrics_base, metrics_model
