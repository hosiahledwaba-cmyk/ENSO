"""Calibration curve analysis, reliability diagrams, and expected calibration error."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, Field

from ml.evaluation.metrics import compute_murphy_decomposition

logger = logging.getLogger("enso_ml.evaluation.calibration")


class CalibrationBinRecord(BaseModel):
    """Metrics for an individual forecast probability bin."""

    bin_index: int
    bin_lower: float
    bin_upper: float
    sample_count: int
    mean_predicted_prob: float
    observed_event_rate: float
    calibration_error: float = Field(
        description="Absolute deviation |mean_predicted_prob - observed_event_rate|."
    )


class CalibrationAnalysisReport(BaseModel):
    """Detailed probabilistic calibration and reliability assessment."""

    model_name: str
    sample_size: int
    expected_calibration_error: float = Field(
        description="Sample-weighted average calibration error across non-empty bins."
    )
    max_calibration_error: float = Field(
        description="Maximum calibration error observed in any individual bin."
    )
    murphy_reliability: float = Field(
        description="Murphy (1973) reliability component (weighted squared error)."
    )
    mean_forecast_probability: float
    observed_base_rate: float
    overconfidence_bias: float = Field(
        description="mean_forecast_probability - observed_base_rate (> 0 implies overconfidence)."
    )
    mean_prediction_entropy: float = Field(
        description="Mean Shannon binary entropy of predicted probabilities in [0.0, 1.0]."
    )
    bins: list[CalibrationBinRecord] = Field(default_factory=list)
    verdict: str = Field(description="Qualitative summary of calibration quality.")


def compute_prediction_entropy(y_prob: np.ndarray) -> float:
    """Compute mean binary Shannon entropy in bits for predicted probabilities."""
    eps = 1e-12
    p = np.clip(y_prob, eps, 1.0 - eps)
    entropy = -(p * np.log2(p) + (1.0 - p) * np.log2(1.0 - p))
    return float(np.mean(entropy))


def analyze_calibration(
    y_true: Sequence[int] | np.ndarray,
    y_prob: Sequence[float] | np.ndarray,
    model_name: str = "model",
    n_bins: int = 5,
) -> CalibrationAnalysisReport:
    """Perform detailed binned calibration and reliability diagram analysis.

    Parameters
    ----------
    y_true : Sequence[int] | np.ndarray
        True binary climate event outcomes in {0, 1}.
    y_prob : Sequence[float] | np.ndarray
        Predicted event probabilities in [0.0, 1.0].
    model_name : str, default "model"
        Identifier for the evaluated model architecture.
    n_bins : int, default 5
        Number of equal-width probability bins between 0.0 and 1.0.

    Returns
    -------
    CalibrationAnalysisReport
        Structured calibration report with bin records, ECE, MCE, and reliability metrics.
    """
    y_t = np.asarray(y_true, dtype=int)
    y_p = np.asarray(y_prob, dtype=float)
    n = len(y_t)

    if n == 0:
        return CalibrationAnalysisReport(
            model_name=model_name,
            sample_size=0,
            expected_calibration_error=0.0,
            max_calibration_error=0.0,
            murphy_reliability=0.0,
            mean_forecast_probability=0.0,
            observed_base_rate=0.0,
            overconfidence_bias=0.0,
            mean_prediction_entropy=0.0,
            bins=[],
            verdict="Empty evaluation set.",
        )

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_p, bin_edges[1:-1])

    bin_records: list[CalibrationBinRecord] = []
    ece_sum = 0.0
    mce = 0.0

    for k in range(n_bins):
        mask = bin_indices == k
        n_k = int(np.sum(mask))
        b_low = round(float(bin_edges[k]), 2)
        b_high = round(float(bin_edges[k + 1]), 2)

        if n_k > 0:
            f_k = float(np.mean(y_p[mask]))
            o_k = float(np.mean(y_t[mask]))
            err = abs(f_k - o_k)
            ece_sum += n_k * err
            mce = max(mce, err)

            bin_records.append(
                CalibrationBinRecord(
                    bin_index=k,
                    bin_lower=b_low,
                    bin_upper=b_high,
                    sample_count=n_k,
                    mean_predicted_prob=round(f_k, 4),
                    observed_event_rate=round(o_k, 4),
                    calibration_error=round(err, 4),
                )
            )
        else:
            bin_records.append(
                CalibrationBinRecord(
                    bin_index=k,
                    bin_lower=b_low,
                    bin_upper=b_high,
                    sample_count=0,
                    mean_predicted_prob=round((b_low + b_high) / 2.0, 4),
                    observed_event_rate=0.0,
                    calibration_error=0.0,
                )
            )

    ece = float(ece_sum / n)
    murphy = compute_murphy_decomposition(y_t, y_p, n_bins=n_bins)
    mean_f = float(np.mean(y_p))
    base_o = float(np.mean(y_t))
    bias = mean_f - base_o
    entropy = compute_prediction_entropy(y_p)

    if ece < 0.05:
        verdict = f"Excellent calibration (ECE={ece:.3f} < 0.05)."
    elif ece < 0.15:
        verdict = f"Moderate calibration (ECE={ece:.3f})."
    else:
        verdict = f"Poor calibration (ECE={ece:.3f} >= 0.15), risk of overconfidence."

    return CalibrationAnalysisReport(
        model_name=model_name,
        sample_size=n,
        expected_calibration_error=round(ece, 5),
        max_calibration_error=round(mce, 5),
        murphy_reliability=murphy.reliability,
        mean_forecast_probability=round(mean_f, 5),
        observed_base_rate=round(base_o, 5),
        overconfidence_bias=round(bias, 5),
        mean_prediction_entropy=round(entropy, 4),
        bins=bin_records,
        verdict=verdict,
    )
