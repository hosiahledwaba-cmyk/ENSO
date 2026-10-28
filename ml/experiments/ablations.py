"""Systematic feature ablation benchmarking for climate prediction models."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from ml.evaluation.metrics import compute_probabilistic_metrics
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import DEFAULT_PREDICTOR_FEATURES, TrainingConfig
from ml.training.models import LogisticRegressionPredictor, XGBoostPredictor

logger = logging.getLogger("enso_ml.experiments.ablations")

# Standard feature ablation subsets
STANDARD_ABLATION_SUITES: dict[str, list[str]] = {
    "full_features": list(DEFAULT_PREDICTOR_FEATURES),
    "enso_macro_only": [
        "oni_aso_degc",
        "oni_trend_aso_jas_degc",
        "oni_trend_aso_jja_degc",
        "nino34_aso_sst_degc",
        "nino34_aso_anom_degc",
        "nino34_oct_anom_degc",
        "nino34_trend_oct_aug_degc",
    ],
    "local_precip_only": [
        "precip_oct_mm",
        "precip_oct_zscore",
        "precip_antecedent_spring_mm",
    ],
    "parsimonious_teleconnection": [
        "oni_aso_degc",
        "precip_oct_zscore",
    ],
    "sst_anomalies_only": [
        "oni_aso_degc",
        "nino34_aso_anom_degc",
        "nino34_oct_anom_degc",
    ],
    "no_oni_macro": [f for f in DEFAULT_PREDICTOR_FEATURES if not f.startswith("oni_")],
    "no_local_precip": [f for f in DEFAULT_PREDICTOR_FEATURES if not f.startswith("precip_")],
}


class AblationResultRecord(BaseModel):
    """Performance evaluation for a specific feature subset."""

    ablation_id: str
    feature_count: int
    features: list[str]
    brier_score_logistic: float
    bss_logistic: float
    brier_score_xgboost: float
    bss_xgboost: float
    delta_bs_vs_full_logistic: float = Field(
        description="Negative implies improvement over full feature set."
    )
    delta_bs_vs_full_xgboost: float = Field(
        description="Negative implies improvement over full feature set."
    )
    superior_architecture: str = Field(
        description="Model architecture achieving lower Brier score on this subset."
    )


class FeatureAblationReport(BaseModel):
    """Machine-readable summary of feature ablation experiments."""

    dataset_fingerprint: str
    sample_size: int
    target_column: str
    ablation_records: list[AblationResultRecord]
    optimal_subset_logistic: str
    optimal_subset_xgboost: str
    key_findings: list[str]


def run_feature_ablation_suite(
    df: pd.DataFrame,
    target_col: str = "target_drought_p20",
    dataset_fingerprint: str = "unknown",
    suites: dict[str, list[str]] | None = None,
    min_train_seasons: int = 5,
    random_seed: int = 42,
) -> FeatureAblationReport:
    """Run rolling-origin cross-validation across systematic feature ablation subsets."""
    ablation_suites = suites or STANDARD_ABLATION_SUITES
    df_sorted = df.sort_values("season_year").reset_index(drop=True)
    total_seasons = len(df_sorted)
    initial_window = min(min_train_seasons, max(2, total_seasons - 2))

    records: list[AblationResultRecord] = []
    full_bs_logistic = 1.0
    full_bs_xgboost = 1.0

    for suite_name, feat_cols in ablation_suites.items():
        # Verify columns exist
        available_cols = [c for c in feat_cols if c in df_sorted.columns]
        if not available_cols:
            logger.warning("Skipping ablation '%s': no matching features in dataset.", suite_name)
            continue

        oof_records: list[dict[str, Any]] = []

        for t in range(initial_window, total_seasons):
            train_fold = df_sorted.iloc[:t]
            test_row = df_sorted.iloc[t : t + 1]

            y_train = train_fold[target_col].to_numpy(dtype=int)
            y_test = int(test_row[target_col].iloc[0])

            # 1. Climatological baseline
            base_model = ClimatologyBaseline().fit(y_train)
            p_base = float(base_model.predict_proba(1)[0, 1])

            # 2. Logistic Regression
            cfg_lr = TrainingConfig(
                target_column=target_col,
                feature_columns=available_cols,
                random_seed=random_seed,
            )
            lr_model = LogisticRegressionPredictor().fit(
                X=train_fold[available_cols],
                y=y_train,
                config=cfg_lr,
            )
            p_lr = float(lr_model.predict_proba(test_row[available_cols])[0, 1])

            # 3. XGBoost
            xgb_model = XGBoostPredictor(
                feature_names=available_cols,
                random_seed=random_seed,
            ).fit(
                X=train_fold[available_cols],
                y=y_train,
            )
            p_xgb = float(xgb_model.predict_proba(test_row[available_cols])[0, 1])

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

        m_lr = compute_probabilistic_metrics(y_true, y_lr, y_prob_reference=y_base)
        m_xgb = compute_probabilistic_metrics(y_true, y_xgb, y_prob_reference=y_base)

        bs_lr = m_lr.brier_score
        bss_lr = m_lr.brier_skill_score or 0.0
        bs_xgb = m_xgb.brier_score
        bss_xgb = m_xgb.brier_skill_score or 0.0

        if suite_name == "full_features":
            full_bs_logistic = bs_lr
            full_bs_xgboost = bs_xgb

        delta_lr = round(bs_lr - full_bs_logistic, 5)
        delta_xgb = round(bs_xgb - full_bs_xgboost, 5)

        sup_arch = "LogisticRegression" if bs_lr <= bs_xgb else "XGBoost"

        records.append(
            AblationResultRecord(
                ablation_id=suite_name,
                feature_count=len(available_cols),
                features=available_cols,
                brier_score_logistic=round(bs_lr, 5),
                bss_logistic=round(bss_lr, 4),
                brier_score_xgboost=round(bs_xgb, 5),
                bss_xgboost=round(bss_xgb, 4),
                delta_bs_vs_full_logistic=delta_lr,
                delta_bs_vs_full_xgboost=delta_xgb,
                superior_architecture=sup_arch,
            )
        )

    best_lr = min(records, key=lambda r: r.brier_score_logistic)
    best_xgb = min(records, key=lambda r: r.brier_score_xgboost)

    findings: list[str] = [
        (
            f"Optimal subset for Logistic Regression: '{best_lr.ablation_id}' "
            f"(BS={best_lr.brier_score_logistic:.5f}, BSS={best_lr.bss_logistic:+.4f})."
        ),
        (
            f"Optimal subset for XGBoost: '{best_xgb.ablation_id}' "
            f"(BS={best_xgb.brier_score_xgboost:.5f}, BSS={best_xgb.bss_xgboost:+.4f})."
        ),
    ]

    return FeatureAblationReport(
        dataset_fingerprint=dataset_fingerprint,
        sample_size=total_seasons,
        target_column=target_col,
        ablation_records=records,
        optimal_subset_logistic=best_lr.ablation_id,
        optimal_subset_xgboost=best_xgb.ablation_id,
        key_findings=findings,
    )
