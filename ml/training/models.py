"""Probabilistic climate classifiers and regularized logistic regression models."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, cast

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.training.config import TrainingConfig

logger = logging.getLogger("enso_ml.training.models")


@dataclass
class LogisticRegressionPredictor:
    """L2-regularized logistic regression classifier with integrated feature standardization.

    Guarantees:
    * Standard scaler fitted strictly on training data (no lookahead leakage).
    * Bounded probabilities P(y=1 | x) in [0.0, 1.0].
    * Interpretable feature coefficients w and intercept b.
    * Graceful handling of degenerate single-class training subsets.
    """

    feature_names: list[str] = field(default_factory=list)
    scaler_mean: dict[str, float] = field(default_factory=dict)
    scaler_scale: dict[str, float] = field(default_factory=dict)
    coefficients: dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    c_regularization: float = 1.0
    random_seed: int = 42
    fallback_base_rate: float | None = None
    fitted: bool = False

    def __post_init__(self) -> None:
        self._scaler = StandardScaler()
        self._model = LogisticRegression(
            C=self.c_regularization,
            solver="lbfgs",
            max_iter=1000,
            random_state=self.random_seed,
        )

    def fit(
        self,
        X: pd.DataFrame,
        y: np.ndarray | list[int],
        config: TrainingConfig | None = None,
    ) -> LogisticRegressionPredictor:
        """Fit scaler and regularized logistic regression strictly on training partition records.

        Parameters
        ----------
        X : pd.DataFrame
            Feature matrix with columns matching feature_names.
        y : np.ndarray | list[int]
            Binary target labels in {0, 1}.
        config : TrainingConfig, optional
            Training hyperparameters.

        Returns
        -------
        LogisticRegressionPredictor
            Fitted classifier.
        """
        cfg = config or TrainingConfig()
        self.feature_names = list(cfg.feature_columns)
        self.c_regularization = cfg.c_regularization
        self.random_seed = cfg.random_seed

        missing_cols = [c for c in self.feature_names if c not in X.columns]
        if missing_cols:
            raise ValueError(f"Input DataFrame is missing required feature columns: {missing_cols}")

        X_mat = X[self.feature_names].to_numpy(dtype=float)
        y_arr = np.asarray(y, dtype=int)

        if len(X_mat) != len(y_arr):
            raise ValueError(f"Length mismatch: X ({len(X_mat)}) != y ({len(y_arr)})")

        if np.isnan(X_mat).any():
            raise ValueError(
                "Feature matrix contains NaN/missing values. Imputation is prohibited."
            )

        # Fit feature standardizer strictly on training data
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X_mat)

        self.scaler_mean = {
            col: round(float(m), 5)
            for col, m in zip(self.feature_names, self._scaler.mean_, strict=True)
        }
        self.scaler_scale = {
            col: round(float(s), 5)
            for col, s in zip(self.feature_names, self._scaler.scale_, strict=True)
        }

        unique_classes = np.unique(y_arr)
        if len(unique_classes) < 2:
            # Degenerate case (e.g. small initial window with 0 events)
            # Fall back to empirical base rate prediction
            self.fallback_base_rate = float(np.mean(y_arr))
            self.coefficients = {col: 0.0 for col in self.feature_names}
            self.intercept = 0.0
            self.fitted = True
            logger.warning(
                "Training data contains only 1 class (%s). Using fallback base rate: %.3f",
                unique_classes,
                self.fallback_base_rate,
            )
            return self

        self.fallback_base_rate = None
        self._model = LogisticRegression(
            C=cfg.c_regularization,
            solver=cfg.solver,
            max_iter=cfg.max_iter,
            random_state=cfg.random_seed,
        )
        self._model.fit(X_scaled, y_arr)

        coefs = self._model.coef_[0]
        self.coefficients = {
            col: round(float(w), 5) for col, w in zip(self.feature_names, coefs, strict=True)
        }
        self.intercept = round(float(self._model.intercept_[0]), 5)
        self.fitted = True

        logger.info(
            "Fitted LogisticRegression (N=%d, C=%.2f): Intercept=%.4f, Top Features: %s",
            len(y_arr),
            self.c_regularization,
            self.intercept,
            sorted(self.coefficients.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3],
        )
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Produce predicted probability array of shape (N, 2)."""
        if not self.fitted:
            raise RuntimeError("LogisticRegressionPredictor must be fitted before predict_proba.")

        missing_cols = [c for c in self.feature_names if c not in X.columns]
        if missing_cols:
            raise ValueError(f"Input DataFrame is missing required feature columns: {missing_cols}")

        X_mat = X[self.feature_names].to_numpy(dtype=float)
        if np.isnan(X_mat).any():
            raise ValueError("Input feature matrix contains NaN/missing values.")

        if self.fallback_base_rate is not None:
            p1 = np.full(len(X_mat), self.fallback_base_rate, dtype=float)
            p0 = 1.0 - p1
            return np.column_stack([p0, p1])

        # Apply frozen training scaler
        X_scaled = self._scaler.transform(X_mat)
        return cast(np.ndarray, self._model.predict_proba(X_scaled))

    def predict(self, X: pd.DataFrame, threshold: float = 0.5) -> np.ndarray:
        """Produce binary predictions at given decision threshold."""
        p1 = self.predict_proba(X)[:, 1]
        return (p1 >= threshold).astype(int)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogisticRegressionPredictor:
        """Reconstruct model from dictionary and restore internal scaler/weights."""
        inst = cls(
            feature_names=data.get("feature_names", list(data.get("coefficients", {}).keys())),
            scaler_mean=data["scaler_mean"],
            scaler_scale=data["scaler_scale"],
            coefficients=data["coefficients"],
            intercept=data["intercept"],
            c_regularization=data.get("c_regularization", 1.0),
            random_seed=data.get("random_seed", 42),
            fallback_base_rate=data.get("fallback_base_rate"),
            fitted=data.get("fitted", True),
        )

        # Restore scikit-learn standard scaler
        if inst.scaler_mean and inst.scaler_scale:
            means = np.array([inst.scaler_mean[f] for f in inst.feature_names], dtype=float)
            scales = np.array([inst.scaler_scale[f] for f in inst.feature_names], dtype=float)
            inst._scaler = StandardScaler()
            inst._scaler.mean_ = means
            inst._scaler.scale_ = scales
            inst._scaler.var_ = scales**2
            inst._scaler.n_features_in_ = len(inst.feature_names)

        # Restore scikit-learn logistic regression weights
        if inst.fitted and inst.fallback_base_rate is None and inst.coefficients:
            inst._model = LogisticRegression(
                C=inst.c_regularization,
                solver="lbfgs",
                max_iter=1000,
                random_state=inst.random_seed,
            )
            inst._model.classes_ = np.array([0, 1])
            inst._model.coef_ = np.array(
                [[inst.coefficients[f] for f in inst.feature_names]], dtype=float
            )
            inst._model.intercept_ = np.array([inst.intercept], dtype=float)

        return inst


@dataclass
class XGBoostPredictor:
    """CPU-friendly nonlinear gradient boosted decision tree classifier.

    Designed for seasonal climate prediction:
    * Shallow tree depth (default max_depth=2) to prevent overfitting on small seasonal samples.
    * Conservative shrinkage (learning_rate=0.05) and subsampling (subsample=0.8).
    * Explicit L1/L2 leaf regularization (reg_alpha=0.1, reg_lambda=1.0).
    * Deterministic single-thread/multi-thread CPU execution.
    * Fallback to empirical base rate for degenerate single-class training folds.
    """

    feature_names: list[str] = field(default_factory=list)
    n_estimators: int = 50
    max_depth: int = 2
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    random_seed: int = 42
    fallback_base_rate: float | None = None
    fitted: bool = False
    feature_importances: dict[str, float] = field(default_factory=dict)
    booster_raw_json: str | None = None

    def __post_init__(self) -> None:
        self._model: xgb.XGBClassifier | None = None

    def fit(
        self,
        X: pd.DataFrame,
        y: np.ndarray | list[int],
        config: TrainingConfig | None = None,
    ) -> XGBoostPredictor:
        """Fit regularized XGBoost classifier on training data."""
        if config is not None:
            self.feature_names = list(config.feature_columns)
            self.random_seed = config.random_seed
        elif not self.feature_names:
            self.feature_names = list(X.columns)

        missing_cols = [c for c in self.feature_names if c not in X.columns]
        if missing_cols:
            raise ValueError(f"Input DataFrame is missing required features: {missing_cols}")

        X_mat = X[self.feature_names].to_numpy(dtype=float)
        y_arr = np.asarray(y, dtype=int)

        if len(X_mat) != len(y_arr):
            raise ValueError(f"Length mismatch: X ({len(X_mat)}) != y ({len(y_arr)})")

        if np.isnan(X_mat).any():
            raise ValueError("Feature matrix contains NaN/missing values. Imputation prohibited.")

        unique_classes = np.unique(y_arr)
        if len(unique_classes) < 2:
            self.fallback_base_rate = float(np.mean(y_arr))
            self.feature_importances = {col: 0.0 for col in self.feature_names}
            self.fitted = True
            logger.warning(
                "Training fold contains only 1 class (%s). Fallback base rate=%.4f.",
                unique_classes,
                self.fallback_base_rate,
            )
            return self

        self.fallback_base_rate = None
        self._model = xgb.XGBClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=self.subsample,
            colsample_bytree=self.colsample_bytree,
            reg_alpha=self.reg_alpha,
            reg_lambda=self.reg_lambda,
            eval_metric="logloss",
            random_state=self.random_seed,
            n_jobs=1,
        )
        self._model.fit(X_mat, y_arr)

        default_imp = np.zeros(len(self.feature_names))
        importances = getattr(self._model, "feature_importances_", default_imp)
        self.feature_importances = {
            col: round(float(imp), 5)
            for col, imp in zip(self.feature_names, importances, strict=True)
        }
        booster = self._model.get_booster()
        self.booster_raw_json = booster.save_raw(raw_format="json").decode("utf-8")
        self.fitted = True

        logger.info(
            "Fitted XGBoostPredictor (N=%d, trees=%d, depth=%d): top feature=%s",
            len(y_arr),
            self.n_estimators,
            self.max_depth,
            max(self.feature_importances.items(), key=lambda kv: kv[1]),
        )
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Produce predicted probability array of shape (N, 2)."""
        if not self.fitted:
            raise RuntimeError("Model must be fitted before predict_proba.")

        missing_cols = [c for c in self.feature_names if c not in X.columns]
        if missing_cols:
            raise ValueError(f"Input DataFrame is missing required features: {missing_cols}")

        X_mat = X[self.feature_names].to_numpy(dtype=float)
        if np.isnan(X_mat).any():
            raise ValueError("Input feature matrix contains NaN/missing values.")

        if self.fallback_base_rate is not None:
            p1 = np.full(len(X_mat), self.fallback_base_rate, dtype=float)
            p0 = 1.0 - p1
            return np.column_stack([p0, p1])

        if self._model is None:
            raise RuntimeError("Internal XGBoost model instance is uninitialized.")

        return self._model.predict_proba(X_mat)

    def predict(self, X: pd.DataFrame, threshold: float = 0.5) -> np.ndarray:
        """Produce binary predictions at given decision threshold."""
        p1 = self.predict_proba(X)[:, 1]
        return (p1 >= threshold).astype(int)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> XGBoostPredictor:
        """Reconstruct XGBoost model from serialized dictionary."""
        inst = cls(
            feature_names=data["feature_names"],
            n_estimators=data.get("n_estimators", 50),
            max_depth=data.get("max_depth", 2),
            learning_rate=data.get("learning_rate", 0.05),
            subsample=data.get("subsample", 0.8),
            colsample_bytree=data.get("colsample_bytree", 0.8),
            reg_alpha=data.get("reg_alpha", 0.1),
            reg_lambda=data.get("reg_lambda", 1.0),
            random_seed=data.get("random_seed", 42),
            fallback_base_rate=data.get("fallback_base_rate"),
            fitted=data.get("fitted", True),
            feature_importances=data.get("feature_importances", {}),
            booster_raw_json=data.get("booster_raw_json"),
        )

        if inst.fitted and inst.fallback_base_rate is None and inst.booster_raw_json:
            inst._model = xgb.XGBClassifier(
                n_estimators=inst.n_estimators,
                max_depth=inst.max_depth,
                learning_rate=inst.learning_rate,
                subsample=inst.subsample,
                colsample_bytree=inst.colsample_bytree,
                reg_alpha=inst.reg_alpha,
                reg_lambda=inst.reg_lambda,
                eval_metric="logloss",
                random_state=inst.random_seed,
                n_jobs=1,
            )
            inst._model.load_model(bytearray(inst.booster_raw_json.encode("utf-8")))

        return inst
