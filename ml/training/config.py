"""Configuration models for climate model training and rolling-origin evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_PREDICTOR_FEATURES: list[str] = [
    "oni_aso_degc",
    "oni_trend_aso_jas_degc",
    "oni_trend_aso_jja_degc",
    "nino34_aso_sst_degc",
    "nino34_aso_anom_degc",
    "nino34_oct_anom_degc",
    "nino34_trend_oct_aug_degc",
    "precip_oct_mm",
    "precip_oct_zscore",
    "precip_antecedent_spring_mm",
]


class TrainingConfig(BaseModel):
    """Hyperparameters and configuration for baseline and logistic regression training."""

    target_column: str = Field(
        default="target_drought_p20",
        description="Target variable ('target_drought_p20' or 'target_below_normal_p33').",
    )
    feature_columns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_PREDICTOR_FEATURES),
        description="List of predictor feature column names.",
    )
    c_regularization: float = Field(
        default=1.0,
        gt=0.0,
        description="Inverse regularization strength C (smaller values imply stronger L2 penalty).",
    )
    penalty: str = Field(default="l2", description="Regularization penalty norm ('l2').")
    solver: str = Field(default="lbfgs", description="Optimization solver ('lbfgs').")
    max_iter: int = Field(default=1000, ge=100, description="Maximum iterations for solver.")
    random_seed: int = Field(default=42, description="Random seed for reproducibility.")

    # Rolling origin evaluation parameters
    min_train_seasons: int = Field(
        default=5,
        ge=3,
        description="Minimum number of seasons in initial training window for walk-forward CV.",
    )
    decision_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Binary decision threshold for classification metrics.",
    )
    calibrate_probabilities: bool = Field(
        default=False,
        description="Whether to apply probability calibration (Platt scaling) on training folds.",
    )
