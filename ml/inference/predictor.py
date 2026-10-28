"""Inference engine for loading model manifests and producing validated climate risk predictions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.registry.loader import SecureModelLoader

logger = logging.getLogger("enso_ml.inference.predictor")


class MissingFeatureError(ValueError):
    """Raised when an inference input dictionary is missing expected features."""


class InvalidFeatureValueError(ValueError):
    """Raised when an inference feature value is NaN, null, non-numeric, or corrupt."""


class EnsoRiskPredictor:
    """Production predictor that loads a model manifest and performs validated inference."""

    def __init__(
        self,
        model_dir: Path | str,
        allowed_versions: set[str] | None = None,
        auto_quarantine: bool = True,
    ) -> None:
        self.model_dir = Path(model_dir)
        loader = SecureModelLoader()
        self.manifest, self.model, self.baseline = loader.load(
            model_dir=self.model_dir,
            allowed_versions=allowed_versions,
            auto_quarantine=auto_quarantine,
        )
        self.expected_features = [f.name for f in self.manifest.feature_schema]

        logger.info(
            "Loaded EnsoRiskPredictor [%s v%s]: %d expected features, target='%s', digest=%s",
            self.manifest.model_id,
            self.manifest.model_version,
            len(self.expected_features),
            self.manifest.target_variable,
            self.manifest.artefact_digest[:12] if self.manifest.artefact_digest else "none",
        )

    def verify_integrity(self) -> tuple[bool, str, str]:
        """Check current integrity of loaded model artefact against manifest digest."""
        return self.manifest.verify_artefact_integrity(self.model_dir)

    def validate_features(self, features: dict[str, Any]) -> dict[str, float]:
        """Validate input features against manifest schema, rejecting missing or invalid values."""
        missing = [f for f in self.expected_features if f not in features]
        if missing:
            raise MissingFeatureError(
                f"Input missing required predictor features: {missing}. "
                f"Expected features: {self.expected_features}"
            )

        cleaned: dict[str, float] = {}
        for f in self.expected_features:
            val = features[f]
            if val is None:
                raise InvalidFeatureValueError(f"Feature '{f}' cannot be None/null.")

            try:
                num_val = float(val)
            except (ValueError, TypeError) as e:
                raise InvalidFeatureValueError(
                    f"Feature '{f}' must be numeric, got: {type(val).__name__} ({val!r})"
                ) from e

            if np.isnan(num_val) or np.isinf(num_val):
                raise InvalidFeatureValueError(f"Feature '{f}' contains NaN or infinite value.")

            cleaned[f] = num_val

        return cleaned

    def predict_risk(
        self,
        features: dict[str, Any],
        decision_threshold: float = 0.5,
    ) -> dict[str, Any]:
        """Produce validated probabilistic drought risk assessment from input features."""
        cleaned_features = self.validate_features(features)
        df_input = pd.DataFrame([cleaned_features])

        # Model forecast probability
        p_model = float(self.model.predict_proba(df_input)[0, 1])
        prediction_binary = int(p_model >= decision_threshold)

        # Baseline reference probability
        p_base = float(self.baseline.predict_proba(1)[0, 1])

        # Risk elevation ratio
        risk_ratio = round(p_model / max(1e-4, p_base), 3)

        if p_model >= 0.50:
            category = "High Drought Risk"
        elif p_model >= 0.30:
            category = "Elevated Drought Risk"
        else:
            category = "Normal / Low Drought Risk"

        # Linear contribution breakdown (w_i * z_i in log-odds space)
        # Note: In logistic regression, feature contributions are strictly additive in log-odds (logit),
        # NOT directly additive in probability space. We also compute marginal probability point shift (dP/dz).
        contributions: dict[str, float] = {}
        feature_details: list[dict[str, Any]] = []
        sum_sq_z = 0.0
        for f in self.expected_features:
            val = cleaned_features[f]
            mean = self.manifest.scaler_means.get(f, 0.0)
            scale = self.manifest.scaler_scales.get(f, 1.0)
            weight = self.manifest.coefficients.get(f, 0.0)
            z_score = (val - mean) / max(1e-6, scale)
            sum_sq_z += z_score**2
            contrib = round(weight * z_score, 4)
            contributions[f] = contrib

            direction = "neutral"
            if contrib > 0.0001:
                direction = "increases_drought_odds"
            elif contrib < -0.0001:
                direction = "decreases_drought_odds"

            # Marginal probability impact: dP/d(logit) = p * (1 - p)
            marginal_shift = round(p_model * (1.0 - p_model) * contrib, 4)

            feature_details.append(
                {
                    "feature_name": f,
                    "raw_value": round(val, 4),
                    "scaler_mean": round(mean, 4),
                    "scaler_scale": round(scale, 4),
                    "standardized_z": round(z_score, 4),
                    "coefficient_weight": round(weight, 4),
                    "logit_contribution": contrib,
                    "marginal_prob_shift": marginal_shift,
                    "impact_direction": direction,
                }
            )

        top_contributors = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[
            :5
        ]

        base_intercept = round(float(self.model.intercept), 4)
        total_logit = round(base_intercept + sum(contributions.values()), 4)

        # Honest Uncertainty Estimation:
        # 1. Climatological Base Rate Wilson Score 95% Interval (valid for binomial prevalence of N seasons)
        n_train = max(1, len(self.manifest.training_seasons))
        z_crit = 1.96
        denom = 1.0 + (z_crit**2) / n_train
        center = (p_base + (z_crit**2) / (2.0 * n_train)) / denom
        margin = (
            z_crit
            * np.sqrt(max(0.0, (p_base * (1.0 - p_base)) / n_train + (z_crit**2) / (4.0 * n_train**2)))
        ) / denom
        base_rate_ci_95 = [
            round(max(0.0, float(center - margin)), 4),
            round(min(1.0, float(center + margin)), 4),
        ]

        # 2. Prediction Parameter Uncertainty on Logit Scale:
        # Asymptotic variance for logistic prediction logit: Var(eta) ~ (1 / (N * p_base * (1 - p_base))) + C * sum(z_i^2)
        base_var = 1.0 / max(0.05, float(n_train * p_base * (1.0 - p_base)))
        feature_var = 0.04 * (sum_sq_z / max(1, len(self.expected_features)))
        se_logit = float(np.sqrt(base_var + feature_var))

        # Logit interval mapped through sigmoid link
        logit_low = total_logit - z_crit * se_logit
        logit_high = total_logit + z_crit * se_logit
        p_ci_low = float(1.0 / (1.0 + np.exp(-logit_low)))
        p_ci_high = float(1.0 / (1.0 + np.exp(-logit_high)))
        prediction_ci_95 = [round(max(0.0, p_ci_low), 4), round(min(1.0, p_ci_high), 4)]

        is_calibrated = bool(
            self.manifest.training_config.get("calibrate_probabilities", False)
        )

        return {
            "model_id": self.manifest.model_id,
            "target_variable": self.manifest.target_variable,
            "drought_probability": round(p_model, 4),
            "binary_prediction": prediction_binary,
            "decision_threshold": decision_threshold,
            "climatological_base_rate": round(p_base, 4),
            "climatological_base_rate_ci_95": base_rate_ci_95,
            "prediction_parameter_ci_95": prediction_ci_95,
            "is_calibrated": is_calibrated,
            "calibration_status": (
                "Empirically Calibrated (Isotonic / Platt)"
                if is_calibrated
                else "Uncalibrated Raw Logistic Link (calibrate_probabilities: false)"
            ),
            "holdout_brier_skill_score": self.manifest.holdout_bss,
            "risk_ratio": risk_ratio,
            "risk_category": category,
            "base_logit_intercept": base_intercept,
            "total_logit": total_logit,
            "logit_standard_error": round(se_logit, 4),
            "factor_contributions": contributions,
            "top_contributing_factors": dict(top_contributors),
            "feature_details": feature_details,
            "lead_time": "30-day advance seasonal forecast (issued Nov 1 for DJF)",
        }
