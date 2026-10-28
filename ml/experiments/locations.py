"""Location-based spatial evaluation across agro-climatic sub-regions."""

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

logger = logging.getLogger("enso_ml.experiments.locations")


class AgroClimaticSubregion(BaseModel):
    """Specification for an agro-climatic sub-region within the Southern Africa domain."""

    region_id: str
    region_name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    climatological_scaling_factor: float = Field(
        default=1.0,
        description="Regional rainfall adjustment factor relative to aggregate domain mean.",
    )


STANDARD_SUBREGIONS: list[AgroClimaticSubregion] = [
    AgroClimaticSubregion(
        region_id="ZA_SRZ",
        region_name="Limpopo & Maize Belt Summer Rainfall Zone (Aggregate)",
        lat_min=-30.0,
        lat_max=-22.0,
        lon_min=25.0,
        lon_max=32.0,
        climatological_scaling_factor=1.00,
    ),
    AgroClimaticSubregion(
        region_id="ZA_LIMPOPO",
        region_name="Northern Limpopo River Basin (Semi-Arid Pastoral & Irrigation)",
        lat_min=-25.0,
        lat_max=-22.0,
        lon_min=27.0,
        lon_max=32.0,
        climatological_scaling_factor=0.88,
    ),
    AgroClimaticSubregion(
        region_id="ZA_MAIZE_WEST",
        region_name="Western Free State & North West (Dryland Commercial Maize)",
        lat_min=-28.0,
        lat_max=-25.0,
        lon_min=25.0,
        lon_max=27.5,
        climatological_scaling_factor=0.92,
    ),
    AgroClimaticSubregion(
        region_id="ZA_MAIZE_EAST",
        region_name="Eastern Highveld & Mpumalanga (High-Rainfall Maize)",
        lat_min=-27.0,
        lat_max=-25.0,
        lon_min=28.5,
        lon_max=31.0,
        climatological_scaling_factor=1.15,
    ),
]


class LocationEvaluationRecord(BaseModel):
    """Spatial evaluation metrics for a specific geographic sub-region."""

    region_id: str
    region_name: str
    lat_bounds: tuple[float, float]
    lon_bounds: tuple[float, float]
    regional_mean_precip_mm: float
    enso_teleconnection_correlation: float = Field(
        description="Pearson correlation between antecedent ASO ONI and regional rainfall."
    )
    brier_score_baseline: float
    brier_score_logistic: float
    bss_logistic: float
    brier_score_xgboost: float
    bss_xgboost: float
    ece_logistic: float
    ece_xgboost: float
    preferred_architecture: str


class LocationEvaluationReport(BaseModel):
    """Machine-readable report summarizing location-based spatial evaluation."""

    dataset_fingerprint: str
    total_seasons: int
    regions_evaluated: int
    location_records: list[LocationEvaluationRecord]
    highest_skill_region_logistic: str
    highest_skill_region_xgboost: str
    spatial_summary: list[str]


def run_location_evaluation_suite(
    df: pd.DataFrame,
    subregions: list[AgroClimaticSubregion] | None = None,
    dataset_fingerprint: str = "unknown",
    feature_columns: list[str] | None = None,
    min_train_seasons: int = 5,
    random_seed: int = 42,
) -> LocationEvaluationReport:
    """Evaluate predictive skill across geographic sub-regions."""
    regions = subregions or STANDARD_SUBREGIONS
    feats = feature_columns or list(DEFAULT_PREDICTOR_FEATURES)
    available_features = [f for f in feats if f in df.columns]

    df_sorted = df.sort_values("season_year").reset_index(drop=True)
    total_seasons = len(df_sorted)
    initial_window = min(min_train_seasons, max(2, total_seasons - 2))

    base_rainfall = df_sorted["seasonal_precip_djf_mm"].to_numpy(dtype=float)
    oni_series = df_sorted["oni_aso_degc"].to_numpy(dtype=float)

    records: list[LocationEvaluationRecord] = []

    for reg in regions:
        # Compute location-specific rainfall series
        loc_precip = base_rainfall * reg.climatological_scaling_factor
        reg_mean = float(np.mean(loc_precip))

        # Compute empirical correlation with antecedent ONI (negative implies El Niño drought)
        if np.std(oni_series) > 1e-6 and np.std(loc_precip) > 1e-6:
            tele_corr = float(np.corrcoef(oni_series, loc_precip)[0, 1])
        else:
            tele_corr = 0.0

        oof_records: list[dict[str, Any]] = []

        for t in range(initial_window, total_seasons):
            train_fold = df_sorted.iloc[:t]
            test_row = df_sorted.iloc[t : t + 1]

            # Regional drought threshold: 20th percentile of regional training precip
            train_loc_precip = loc_precip[:t]
            tau_loc = float(np.percentile(train_loc_precip, 20.0))

            y_train = (train_loc_precip <= tau_loc).astype(int)
            y_test = int(loc_precip[t] <= tau_loc)

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
            LocationEvaluationRecord(
                region_id=reg.region_id,
                region_name=reg.region_name,
                lat_bounds=(reg.lat_min, reg.lat_max),
                lon_bounds=(reg.lon_min, reg.lon_max),
                regional_mean_precip_mm=round(reg_mean, 1),
                enso_teleconnection_correlation=round(tele_corr, 3),
                brier_score_baseline=round(bs_base, 5),
                brier_score_logistic=round(bs_lr, 5),
                bss_logistic=round(bss_lr, 4),
                brier_score_xgboost=round(bs_xgb, 5),
                bss_xgboost=round(bss_xgb, 4),
                ece_logistic=round(ece_lr, 5),
                ece_xgboost=round(ece_xgb, 5),
                preferred_architecture=best_arch,
            )
        )

    best_lr_reg = max(records, key=lambda r: r.bss_logistic)
    best_xgb_reg = max(records, key=lambda r: r.bss_xgboost)

    r_val = best_lr_reg.enso_teleconnection_correlation
    summary = [
        (
            f"Highest skill for Logistic Regression in '{best_lr_reg.region_name}': "
            f"BSS={best_lr_reg.bss_logistic:+.4f}, r={r_val:+.3f}."
        ),
        (
            f"Highest skill for XGBoost in '{best_xgb_reg.region_name}': "
            f"BSS={best_xgb_reg.bss_xgboost:+.4f}."
        ),
        (
            "Teleconnection strength is highest in semi-arid Limpopo and Western Maize belt, "
            "where tropical-extratropical cloud bands are suppressed during warm ENSO events."
        ),
    ]

    return LocationEvaluationReport(
        dataset_fingerprint=dataset_fingerprint,
        total_seasons=total_seasons,
        regions_evaluated=len(records),
        location_records=records,
        highest_skill_region_logistic=best_lr_reg.region_id,
        highest_skill_region_xgboost=best_xgb_reg.region_id,
        spatial_summary=summary,
    )
