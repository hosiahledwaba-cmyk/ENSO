"""Seasonal climatological reference forecast baseline."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("enso_ml.training.baseline")


@dataclass
class ClimatologyBaseline:
    """Historical climatological reference benchmark.

    Issues the empirical event frequency of the training partition:
    f_Y = o_bar_train = (1 / N_train) * sum(y_i)
    Serves as the zero-skill anchor for Brier Skill Score calculation (RD-001, RD-002).
    """

    base_rate: float = 0.20
    n_train: int = 0
    event_count: int = 0
    standard_error: float = 0.0
    ci_lower_95: float = 0.0
    ci_upper_95: float = 0.0
    fitted: bool = False

    def fit(self, y: np.ndarray | list[int]) -> ClimatologyBaseline:
        """Fit climatological base rate strictly from training target series."""
        y_arr = np.asarray(y, dtype=int)
        n = len(y_arr)
        if n == 0:
            raise ValueError("Cannot fit ClimatologyBaseline on empty target array.")

        events = int(np.sum(y_arr))
        base_rate = float(events / n)

        # Standard error of the sample proportion
        se = float(np.sqrt((base_rate * (1.0 - base_rate)) / n)) if n > 1 else 0.0
        ci_lower = max(0.0, base_rate - 1.96 * se)
        ci_upper = min(1.0, base_rate + 1.96 * se)

        self.base_rate = round(base_rate, 4)
        self.n_train = n
        self.event_count = events
        self.standard_error = round(se, 4)
        self.ci_lower_95 = round(ci_lower, 4)
        self.ci_upper_95 = round(ci_upper, 4)
        self.fitted = True

        logger.info(
            "Fitted ClimatologyBaseline (N=%d): base_rate=%.4f (SE=%.4f, 95%% CI=[%.4f, %.4f])",
            self.n_train,
            self.base_rate,
            self.standard_error,
            self.ci_lower_95,
            self.ci_upper_95,
        )
        return self

    def predict_proba(self, n_samples: int) -> np.ndarray:
        """Return constant climatological probabilities of shape (n_samples, 2).

        Column 0: P(y=0) = 1 - base_rate
        Column 1: P(y=1) = base_rate
        """
        if not self.fitted:
            raise RuntimeError("ClimatologyBaseline must be fitted before predict_proba.")

        p1 = np.full(n_samples, self.base_rate, dtype=float)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def predict(self, n_samples: int, threshold: float = 0.5) -> np.ndarray:
        """Return binary predictions at given decision threshold."""
        p1 = self.predict_proba(n_samples)[:, 1]
        return (p1 >= threshold).astype(int)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClimatologyBaseline:
        """Reconstruct baseline from dictionary."""
        return cls(**data)
