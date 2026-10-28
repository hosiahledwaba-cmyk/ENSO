"""Evaluation metric data structures and probabilistic verification models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MurphyDecomposition(BaseModel):
    """Murphy (1973) partition of Brier score: BS = Reliability - Resolution + Uncertainty."""

    reliability: float = Field(description="Calibration error (lower is better, optimal=0.0).")
    resolution: float = Field(description="Discriminatory resolution (higher is better).")
    uncertainty: float = Field(
        description="Inherent variance of the observational outcome o*(1-o)."
    )
    within_bin_variance: float = Field(
        default=0.0,
        description="Forecast variance within bins (non-zero for binned continuous forecasts).",
    )


class ProbabilisticMetrics(BaseModel):
    """Comprehensive performance metrics for probabilistic binary climate forecasts."""

    sample_size: int = Field(description="Total number of evaluated forecast seasons.")
    event_count: int = Field(description="Observed number of drought events in evaluation set.")
    observed_base_rate: float = Field(description="Observed empirical frequency (o_bar).")
    mean_forecast_probability: float = Field(
        description="Average predicted forecast probability (f_bar)."
    )

    # Primary Probabilistic Error
    brier_score: float = Field(
        description="Mean squared probability error (optimal=0.0, worst=1.0)."
    )
    brier_skill_score: float | None = Field(
        default=None,
        description="Skill over climatological reference (BSS = 1 - BS_model / BS_clim).",
    )
    log_loss: float = Field(description="Cross-entropy error (bounded to avoid log(0)).")

    # Classification & Discrimination
    roc_auc: float | None = Field(
        default=None, description="Receiver Operating Characteristic AUC."
    )
    pr_auc: float | None = Field(
        default=None, description="Precision-Recall Area Under Curve / AP."
    )
    precision: float = Field(description="Precision at default 0.5 decision threshold.")
    recall: float = Field(description="Recall (hit rate) at default 0.5 decision threshold.")
    f1_score: float = Field(description="Harmonic mean of precision and recall.")

    # Calibration & Uncertainty
    murphy: MurphyDecomposition | None = Field(
        default=None, description="Murphy decomposition of Brier Score."
    )
    expected_calibration_error: float | None = Field(
        default=None, description="Binned expected calibration error (ECE)."
    )
    prediction_uncertainty_std: float = Field(
        description="Standard deviation of predicted probabilities across evaluation set."
    )


class ExperimentEvaluationSummary(BaseModel):
    """Comparison summary between the climatological baseline and trained ML models."""

    model_name: str
    target_variable: str
    rolling_origin_metrics: ProbabilisticMetrics
    holdout_metrics: ProbabilisticMetrics
    beats_baseline_on_holdout: bool = Field(
        description="True if holdout Brier Score is strictly lower than baseline Brier Score."
    )
    holdout_bss: float | None = Field(
        description="Brier Skill Score achieved on the holdout test set relative to climatology."
    )
