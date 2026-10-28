"""Probabilistic evaluation metrics and calibration scoring for climate forecasts."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.evaluation.models import MurphyDecomposition, ProbabilisticMetrics

logger = logging.getLogger("enso_ml.evaluation.metrics")


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Compute mean squared probability error: BS = 1/N * sum((f_i - o_i)^2)."""
    return float(np.mean((y_prob - y_true) ** 2))


def compute_brier_skill_score(bs_model: float, bs_reference: float) -> float:
    """Compute Brier Skill Score: BSS = 1 - (BS_model / BS_ref).

    * BSS > 0: Model outperforms reference climatology.
    * BSS = 0: Model performs identically to reference.
    * BSS < 0: Model performs worse than reference.
    """
    if bs_reference <= 0.0:
        return 0.0 if bs_model <= 0.0 else -float("inf")
    return float(1.0 - (bs_model / bs_reference))


def compute_log_loss(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-15) -> float:
    """Compute cross-entropy loss bounded by eps to prevent log(0)."""
    clipped = np.clip(y_prob, eps, 1.0 - eps)
    loss = -(y_true * np.log(clipped) + (1.0 - y_true) * np.log(1.0 - clipped))
    return float(np.mean(loss))


def compute_murphy_decomposition(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 5,
) -> MurphyDecomposition:
    """Compute Murphy (1973) algebraic decomposition: BS = Reliability - Resolution + Uncertainty.

    Parameters
    ----------
    y_true : np.ndarray
        Binary observational outcomes in {0, 1}.
    y_prob : np.ndarray
        Predicted event probabilities in [0, 1].
    n_bins : int, default 5
        Number of probability bins for calibration grouping.

    Returns
    -------
    MurphyDecomposition
        Reliability, resolution, and uncertainty components.
    """
    n = len(y_true)
    if n == 0:
        return MurphyDecomposition(reliability=0.0, resolution=0.0, uncertainty=0.0)

    o_bar = float(np.mean(y_true))
    uncertainty = float(o_bar * (1.0 - o_bar))

    # Equal-width bins between 0.0 and 1.0
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Assign each forecast to a bin
    bin_indices = np.digitize(y_prob, bin_edges[1:-1])

    reliability_sum = 0.0
    resolution_sum = 0.0
    within_bin_var_sum = 0.0

    for k in range(n_bins):
        mask = bin_indices == k
        n_k = int(np.sum(mask))
        if n_k > 0:
            f_k = float(np.mean(y_prob[mask]))
            o_k = float(np.mean(y_true[mask]))
            reliability_sum += n_k * ((f_k - o_k) ** 2)
            resolution_sum += n_k * ((o_k - o_bar) ** 2)
            within_bin_var_sum += float(np.sum((y_prob[mask] - f_k) ** 2))

    reliability = float(reliability_sum / n)
    resolution = float(resolution_sum / n)
    within_bin_variance = float(within_bin_var_sum / n)

    return MurphyDecomposition(
        reliability=round(reliability, 5),
        resolution=round(resolution, 5),
        uncertainty=round(uncertainty, 5),
        within_bin_variance=round(within_bin_variance, 5),
    )


def compute_expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 5,
) -> float:
    """Compute Expected Calibration Error (ECE): ECE = sum(N_k / N * |f_bar_k - o_bar_k|)."""
    n = len(y_true)
    if n == 0:
        return 0.0

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bin_edges[1:-1])
    ece_sum = 0.0

    for k in range(n_bins):
        mask = bin_indices == k
        n_k = int(np.sum(mask))
        if n_k > 0:
            f_k = float(np.mean(y_prob[mask]))
            o_k = float(np.mean(y_true[mask]))
            ece_sum += n_k * abs(f_k - o_k)

    return float(round(ece_sum / n, 5))


def compute_probabilistic_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_prob: Sequence[float] | np.ndarray,
    y_prob_reference: Sequence[float] | np.ndarray | None = None,
    decision_threshold: float = 0.5,
    n_bins: int = 5,
) -> ProbabilisticMetrics:
    """Calculate comprehensive evaluation metrics for probabilistic binary forecasts.

    Parameters
    ----------
    y_true : Sequence[int] | np.ndarray
        Ground-truth binary labels in {0, 1}.
    y_prob : Sequence[float] | np.ndarray
        Model predicted event probabilities in [0.0, 1.0].
    y_prob_reference : Sequence[float] | np.ndarray, optional
        Reference probabilities (e.g. historical climatology) for BSS computation.
    decision_threshold : float, default 0.5
        Threshold for binary classification metrics (precision, recall, f1).
    n_bins : int, default 5
        Bin count for calibration and Murphy decomposition.

    Returns
    -------
    ProbabilisticMetrics
        Full metrics container.
    """
    y_t = np.asarray(y_true, dtype=int)
    y_p = np.asarray(y_prob, dtype=float)

    if len(y_t) != len(y_p):
        raise ValueError(f"Length mismatch: y_true ({len(y_t)}) != y_prob ({len(y_p)})")

    n = len(y_t)
    if n == 0:
        raise ValueError("Cannot compute metrics on empty arrays.")

    event_count = int(np.sum(y_t))
    o_bar = float(np.mean(y_t))
    f_bar = float(np.mean(y_p))
    pred_std = float(np.std(y_p))

    # Probabilistic error metrics
    brier = compute_brier_score(y_t, y_p)
    loss = compute_log_loss(y_t, y_p)

    bss: float | None = None
    if y_prob_reference is not None:
        y_ref = np.asarray(y_prob_reference, dtype=float)
        brier_ref = compute_brier_score(y_t, y_ref)
        bss = round(compute_brier_skill_score(brier, brier_ref), 4)

    # Classification metrics at decision threshold
    y_pred_binary = (y_p >= decision_threshold).astype(int)
    prec = float(precision_score(y_t, y_pred_binary, zero_division=0))
    rec = float(recall_score(y_t, y_pred_binary, zero_division=0))
    f1 = float(f1_score(y_t, y_pred_binary, zero_division=0))

    # ROC-AUC and PR-AUC require at least one sample in each class
    roc_auc: float | None = None
    pr_auc: float | None = None
    if len(np.unique(y_t)) > 1:
        try:
            roc_auc = float(round(roc_auc_score(y_t, y_p), 4))
        except ValueError:
            roc_auc = None

        try:
            pr_auc = float(round(average_precision_score(y_t, y_p), 4))
        except ValueError:
            pr_auc = None

    # Calibration & Murphy decomposition
    murphy = compute_murphy_decomposition(y_t, y_p, n_bins=n_bins)
    ece = compute_expected_calibration_error(y_t, y_p, n_bins=n_bins)

    return ProbabilisticMetrics(
        sample_size=n,
        event_count=event_count,
        observed_base_rate=round(o_bar, 4),
        mean_forecast_probability=round(f_bar, 4),
        brier_score=round(brier, 5),
        brier_skill_score=bss,
        log_loss=round(loss, 5),
        roc_auc=roc_auc,
        pr_auc=pr_auc,
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
        murphy=murphy,
        expected_calibration_error=ece,
        prediction_uncertainty_std=round(pred_std, 4),
    )
