"""Target definition, historical reference distribution, and drought classification."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.features.config import TargetConfig

logger = logging.getLogger("enso_ml.features.target")


class TargetComputationError(ValueError):
    """Raised when target computation fails validation or encounters invalid data."""


@dataclass(frozen=True)
class ReferenceDistribution:
    """Historical baseline reference distribution fitted exclusively on training-period data.

    Eliminates lookahead bias by freezing climatological normal parameters (mu, sigma)
    and empirical quantile thresholds (tau_20, tau_33) on the training partition (RD-001).
    Validation and test sets are evaluated strictly against this frozen baseline.
    """

    train_seasons: list[int]
    n_train: int
    mean_seasonal_precip_mm: float
    std_seasonal_precip_mm: float
    median_seasonal_precip_mm: float
    min_seasonal_precip_mm: float
    max_seasonal_precip_mm: float
    tau_drought_p20_mm: float
    tau_below_normal_p33_mm: float
    mean_october_precip_mm: float
    std_october_precip_mm: float
    quantile_method: str

    @classmethod
    def fit(
        cls,
        train_df: pd.DataFrame,
        config: TargetConfig | None = None,
    ) -> ReferenceDistribution:
        """Fit baseline distribution parameters strictly on training partition records.

        Parameters
        ----------
        train_df : pd.DataFrame
            DataFrame containing training-period records with 'seasonal_precip_djf_mm'
            and 'precip_oct_mm'.
        config : TargetConfig, optional
            Target quantile configuration. Defaults to TargetConfig().

        Returns
        -------
        ReferenceDistribution
            Frozen baseline reference parameters.
        """
        cfg = config or TargetConfig()
        required_cols = ["season_year", "seasonal_precip_djf_mm", "precip_oct_mm"]
        missing = [c for c in required_cols if c not in train_df.columns]
        if missing:
            raise TargetComputationError(
                f"Cannot fit ReferenceDistribution. Missing required columns: {missing}"
            )

        if len(train_df) < 3:
            raise TargetComputationError(
                f"Training set has insufficient records (N={len(train_df)}) for reference fitting."
            )

        # Enforce no missing data - prohibit silent imputation
        precip_djf = train_df["seasonal_precip_djf_mm"].to_numpy(dtype=float)
        precip_oct = train_df["precip_oct_mm"].to_numpy(dtype=float)

        if np.isnan(precip_djf).any() or np.isnan(precip_oct).any():
            raise TargetComputationError(
                "Training precipitation records contain NaN/missing values. "
                "Imputation is prohibited."
            )

        if (precip_djf < 0.0).any() or (precip_oct < 0.0).any():
            raise TargetComputationError(
                "Training precipitation records contain negative rainfall depths."
            )

        # Estimate seasonal distribution statistics (sample std with ddof=1)
        mean_djf = float(np.mean(precip_djf))
        std_djf = float(np.std(precip_djf, ddof=1))
        if std_djf <= 0.0:
            raise TargetComputationError("Degenerate training rainfall series with zero variance.")

        median_djf = float(np.median(precip_djf))
        min_djf = float(np.min(precip_djf))
        max_djf = float(np.max(precip_djf))

        # Quantiles for drought thresholds
        try:
            tau_20 = float(
                np.quantile(precip_djf, cfg.drought_quantile, method=cfg.quantile_method)
            )
            tau_33 = float(
                np.quantile(precip_djf, cfg.below_normal_quantile, method=cfg.quantile_method)
            )
        except (ValueError, TypeError):
            # Fallback to linear method if method unsupported
            tau_20 = float(np.quantile(precip_djf, cfg.drought_quantile, method="linear"))
            tau_33 = float(np.quantile(precip_djf, cfg.below_normal_quantile, method="linear"))

        # October antecedent statistics
        mean_oct = float(np.mean(precip_oct))
        std_oct = float(np.std(precip_oct, ddof=1))
        if std_oct <= 0.0:
            std_oct = 1.0  # Guard against constant October rainfall in tiny fixtures

        seasons = sorted(int(s) for s in train_df["season_year"].tolist())

        ref = cls(
            train_seasons=seasons,
            n_train=len(seasons),
            mean_seasonal_precip_mm=round(mean_djf, 4),
            std_seasonal_precip_mm=round(std_djf, 4),
            median_seasonal_precip_mm=round(median_djf, 4),
            min_seasonal_precip_mm=round(min_djf, 4),
            max_seasonal_precip_mm=round(max_djf, 4),
            tau_drought_p20_mm=round(tau_20, 4),
            tau_below_normal_p33_mm=round(tau_33, 4),
            mean_october_precip_mm=round(mean_oct, 4),
            std_october_precip_mm=round(std_oct, 4),
            quantile_method=cfg.quantile_method,
        )
        logger.info(
            "Fitted baseline (%d seasons, %d-%d): mu=%.1f, sigma=%.1f, tau_20=%.1f mm",
            ref.n_train,
            ref.train_seasons[0],
            ref.train_seasons[-1],
            ref.mean_seasonal_precip_mm,
            ref.std_seasonal_precip_mm,
            ref.tau_drought_p20_mm,
        )
        return ref

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply frozen baseline parameters to calculate standardized anomalies and binary targets.

        Outputs:
        * seasonal_precip_zscore: (P_Y - mu_train) / sigma_train
        * precip_oct_zscore: (P_oct - mu_oct_train) / sigma_oct_train
        * target_drought_p20: 1 if P_Y <= tau_20 else 0
        * target_below_normal_p33: 1 if P_Y <= tau_33 else 0
        """
        required_cols = ["seasonal_precip_djf_mm", "precip_oct_mm"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise TargetComputationError(f"Cannot transform. Missing columns: {missing}")

        out = df.copy()
        precip_djf = out["seasonal_precip_djf_mm"].to_numpy(dtype=float)
        precip_oct = out["precip_oct_mm"].to_numpy(dtype=float)

        if np.isnan(precip_djf).any() or np.isnan(precip_oct).any():
            raise TargetComputationError(
                "Encountered NaN in precipitation values during transform."
            )

        # Standardized anomalies relative to frozen training baseline
        out["seasonal_precip_zscore"] = np.round(
            (precip_djf - self.mean_seasonal_precip_mm) / self.std_seasonal_precip_mm, 4
        )
        out["precip_oct_zscore"] = np.round(
            (precip_oct - self.mean_october_precip_mm) / self.std_october_precip_mm, 4
        )

        # Binary targets (1 = event occurs, 0 = does not occur)
        # Event: seasonal rainfall <= threshold
        out["target_drought_p20"] = (precip_djf <= self.tau_drought_p20_mm).astype(int)
        out["target_below_normal_p33"] = (precip_djf <= self.tau_below_normal_p33_mm).astype(int)

        return out

    def to_dict(self) -> dict[str, Any]:
        """Convert reference distribution to a dictionary."""
        return asdict(self)

    def to_json(self, filepath: Path | str) -> None:
        """Persist reference distribution to JSON file for auditability."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, filepath: Path | str) -> ReferenceDistribution:
        """Load reference distribution from persisted JSON file."""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
