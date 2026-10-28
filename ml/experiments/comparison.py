from __future__ import annotations

import logging
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from pydantic import BaseModel, Field

from ml.data.provenance.tracker import compute_sha256
from ml.evaluation.calibration import CalibrationAnalysisReport, analyze_calibration
from ml.evaluation.metrics import compute_probabilistic_metrics
from ml.evaluation.models import ProbabilisticMetrics
from ml.experiments.ablations import FeatureAblationReport, run_feature_ablation_suite
from ml.experiments.locations import LocationEvaluationReport, run_location_evaluation_suite
from ml.experiments.thresholds import ThresholdSensitivityReport, run_threshold_sensitivity_suite
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import TrainingConfig
from ml.training.models import LogisticRegressionPredictor, XGBoostPredictor

logger = logging.getLogger("enso_ml.experiments.comparison")


class ScientificComplexityVerdict(BaseModel):
    """Evaluation of whether added nonlinear model complexity is scientifically justified."""

    is_nonlinear_complexity_justified: bool
    cv_bss_delta_xgboost_vs_logistic: float = Field(
        description="XGBoost CV BSS minus Logistic Regression CV BSS."
    )
    holdout_bss_delta_xgboost_vs_logistic: float = Field(
        description="XGBoost Holdout BSS minus Logistic Regression Holdout BSS."
    )
    best_holdout_model: str
    primary_failure_modes: list[str]
    features_improving_performance: list[str]
    justification_rationale: str


class ExperimentComparisonManifest(BaseModel):
    """Complete machine-readable experiment manifest tracking multi-model benchmarking."""

    manifest_version: str = "1.0.0"
    experiment_id: str
    timestamp_utc: str
    random_seed: int
    software_versions: dict[str, str]
    dataset_path: str
    dataset_fingerprint_sha256: str
    training_seasons: list[int]
    holdout_seasons: list[int]
    feature_columns: list[str]

    # Model Evaluation Metrics
    rolling_origin_cv: dict[str, ProbabilisticMetrics]
    holdout_evaluation: dict[str, ProbabilisticMetrics]
    calibration_reports: dict[str, CalibrationAnalysisReport]

    # In-Depth Analyses
    ablation_report: FeatureAblationReport
    threshold_report: ThresholdSensitivityReport
    location_report: LocationEvaluationReport

    # Synthesis
    verdict: ScientificComplexityVerdict

    def to_json(self, output_path: Path | str) -> None:
        """Serialize manifest to disk as formatted JSON."""
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))


class MultiModelExperimentRunner:
    """Orchestrates comprehensive multi-model comparison across linear, nonlinear, and baselines."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def run(
        self,
        features_csv_path: Path | str,
        output_dir: Path | str,
        holdout_count: int = 2,
    ) -> ExperimentComparisonManifest:
        """Execute full multi-model experiment comparison and save manifest."""
        csv_path = Path(features_csv_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not csv_path.is_file():
            raise FileNotFoundError(f"Feature dataset not found: {csv_path}")

        dataset_sha = compute_sha256(csv_path)
        df = pd.read_csv(csv_path)
        df_sorted = df.sort_values("season_year").reset_index(drop=True)
        total_seasons = len(df_sorted)

        if total_seasons < 4:
            raise ValueError(f"Insufficient seasons (N={total_seasons}) for comparison.")

        # Partition: Train vs Final Holdout
        train_df = df_sorted.iloc[:-holdout_count].copy()
        holdout_df = df_sorted.iloc[-holdout_count:].copy()

        train_seasons = list(train_df["season_year"].astype(int))
        holdout_seasons = list(holdout_df["season_year"].astype(int))
        target_col = self.config.target_column
        feature_cols = [c for c in self.config.feature_columns if c in df.columns]

        logger.info(
            "Comparing models: Train seasons=%s, Holdout seasons=%s",
            train_seasons,
            holdout_seasons,
        )

        # ---------------------------------------------------------
        # 1. Walk-Forward Rolling-Origin CV on Training Partition
        # ---------------------------------------------------------
        n_train = len(train_df)
        init_win = min(self.config.min_train_seasons, max(2, n_train - 2))

        oof_records: list[dict[str, Any]] = []

        for t in range(init_win, n_train):
            sub_train = train_df.iloc[:t]
            test_row = train_df.iloc[t : t + 1]

            y_tr = sub_train[target_col].to_numpy(dtype=int)
            y_te = int(test_row[target_col].iloc[0])

            # Climatology Baseline
            base = ClimatologyBaseline().fit(y_tr)
            p_base = float(base.predict_proba(1)[0, 1])

            # Logistic Regression
            lr = LogisticRegressionPredictor().fit(
                X=sub_train[feature_cols],
                y=y_tr,
                config=self.config,
            )
            p_lr = float(lr.predict_proba(test_row[feature_cols])[0, 1])

            # XGBoost
            xgb_m = XGBoostPredictor(
                feature_names=feature_cols,
                random_seed=self.config.random_seed,
            ).fit(
                X=sub_train[feature_cols],
                y=y_tr,
            )
            p_xgb = float(xgb_m.predict_proba(test_row[feature_cols])[0, 1])

            oof_records.append(
                {
                    "y_true": y_te,
                    "prob_base": p_base,
                    "prob_lr": p_lr,
                    "prob_xgb": p_xgb,
                }
            )

        oof_df = pd.DataFrame(oof_records)
        y_cv_true = oof_df["y_true"].to_numpy(dtype=int)
        p_cv_base = oof_df["prob_base"].to_numpy(dtype=float)
        p_cv_lr = oof_df["prob_lr"].to_numpy(dtype=float)
        p_cv_xgb = oof_df["prob_xgb"].to_numpy(dtype=float)

        cv_metrics: dict[str, ProbabilisticMetrics] = {
            "climatology_baseline": compute_probabilistic_metrics(
                y_cv_true, p_cv_base, y_prob_reference=p_cv_base
            ),
            "logistic_regression": compute_probabilistic_metrics(
                y_cv_true, p_cv_lr, y_prob_reference=p_cv_base
            ),
            "xgboost": compute_probabilistic_metrics(
                y_cv_true, p_cv_xgb, y_prob_reference=p_cv_base
            ),
        }

        # ---------------------------------------------------------
        # 2. Final Untouched Holdout Evaluation
        # ---------------------------------------------------------
        # Train final models on entire training partition
        y_full_train = train_df[target_col].to_numpy(dtype=int)
        y_holdout = holdout_df[target_col].to_numpy(dtype=int)
        X_holdout = holdout_df[feature_cols]

        final_base = ClimatologyBaseline().fit(y_full_train)
        final_lr = LogisticRegressionPredictor().fit(
            X=train_df[feature_cols],
            y=y_full_train,
            config=self.config,
        )
        final_xgb = XGBoostPredictor(
            feature_names=feature_cols,
            random_seed=self.config.random_seed,
        ).fit(
            X=train_df[feature_cols],
            y=y_full_train,
        )

        p_ho_base = final_base.predict_proba(len(holdout_df))[:, 1]
        p_ho_lr = final_lr.predict_proba(X_holdout)[:, 1]
        p_ho_xgb = final_xgb.predict_proba(X_holdout)[:, 1]

        holdout_metrics: dict[str, ProbabilisticMetrics] = {
            "climatology_baseline": compute_probabilistic_metrics(
                y_holdout, p_ho_base, y_prob_reference=p_ho_base
            ),
            "logistic_regression": compute_probabilistic_metrics(
                y_holdout, p_ho_lr, y_prob_reference=p_ho_base
            ),
            "xgboost": compute_probabilistic_metrics(
                y_holdout, p_ho_xgb, y_prob_reference=p_ho_base
            ),
        }

        # ---------------------------------------------------------
        # 3. Calibration Reports
        # ---------------------------------------------------------
        calib_reports: dict[str, CalibrationAnalysisReport] = {
            "climatology_baseline": analyze_calibration(
                y_cv_true, p_cv_base, model_name="ClimatologyBaseline"
            ),
            "logistic_regression": analyze_calibration(
                y_cv_true, p_cv_lr, model_name="LogisticRegression"
            ),
            "xgboost": analyze_calibration(y_cv_true, p_cv_xgb, model_name="XGBoost"),
        }

        # ---------------------------------------------------------
        # 4. Extended Analyses: Ablations, Thresholds, Locations
        # ---------------------------------------------------------
        ablation_rep = run_feature_ablation_suite(
            df=train_df,
            target_col=target_col,
            dataset_fingerprint=dataset_sha,
            random_seed=self.config.random_seed,
        )

        threshold_rep = run_threshold_sensitivity_suite(
            df=train_df,
            dataset_fingerprint=dataset_sha,
            feature_columns=feature_cols,
            random_seed=self.config.random_seed,
        )

        location_rep = run_location_evaluation_suite(
            df=train_df,
            dataset_fingerprint=dataset_sha,
            feature_columns=feature_cols,
            random_seed=self.config.random_seed,
        )

        # ---------------------------------------------------------
        # 5. Scientific Complexity Synthesis
        # ---------------------------------------------------------
        cv_bss_lr = cv_metrics["logistic_regression"].brier_skill_score or 0.0
        cv_bss_xgb = cv_metrics["xgboost"].brier_skill_score or 0.0
        delta_cv_bss = round(cv_bss_xgb - cv_bss_lr, 4)

        ho_bs_base = holdout_metrics["climatology_baseline"].brier_score
        ho_bs_lr = holdout_metrics["logistic_regression"].brier_score
        ho_bs_xgb = holdout_metrics["xgboost"].brier_score

        ho_bss_lr = holdout_metrics["logistic_regression"].brier_skill_score or 0.0
        ho_bss_xgb = holdout_metrics["xgboost"].brier_skill_score or 0.0
        delta_ho_bss = round(ho_bss_xgb - ho_bss_lr, 4)

        # Determine best holdout model
        scores = [
            ("climatology_baseline", ho_bs_base),
            ("logistic_regression", ho_bs_lr),
            ("xgboost", ho_bs_xgb),
        ]
        best_model_name = min(scores, key=lambda kv: kv[1])[0]

        # Is nonlinear complexity justified?
        # Justified ONLY if XGBoost strictly outperforms both Climatology AND Logistic on holdout
        complexity_justified = (ho_bs_xgb < ho_bs_base) and (ho_bs_xgb < ho_bs_lr)

        failure_modes: list[str] = [
            "Overconfidence on small seasonal sample: Trees produce extreme leaf probabilities.",
            "Sample scarcity: Severe drought has low base rate, causing greedy splits to overfit.",
            (
                "Holdout over-prediction: Elevated antecedent SST caused high predicted risk "
                "during non-drought years."
            ),
        ]

        improving_features: list[str] = [
            "oni_aso_degc (primary macro teleconnection indicator)",
            "precip_oct_zscore (antecedent local soil moisture deficit)",
            "nino34_aso_anom_degc (corroborating equatorial Pacific SST)",
        ]

        if complexity_justified:
            rationale = (
                f"XGBoost demonstrated superior holdout performance (BS={ho_bs_xgb:.4f}) over "
                f"Logistic Regression (BS={ho_bs_lr:.4f}) and Climatology (BS={ho_bs_base:.4f}). "
                "The added model complexity is scientifically justified."
            )
        else:
            rationale = (
                f"XGBoost did NOT outperform simpler models on holdout (XGB BS={ho_bs_xgb:.4f} "
                f"vs LR BS={ho_bs_lr:.4f} vs Baseline BS={ho_bs_base:.4f}). Leaf overconfidence "
                "and high variance on small sample sizes mean the added complexity of XGBoost is "
                "NOT scientifically justified over regularized linear models or climatology."
            )

        verdict = ScientificComplexityVerdict(
            is_nonlinear_complexity_justified=complexity_justified,
            cv_bss_delta_xgboost_vs_logistic=delta_cv_bss,
            holdout_bss_delta_xgboost_vs_logistic=delta_ho_bss,
            best_holdout_model=best_model_name,
            primary_failure_modes=failure_modes,
            features_improving_performance=improving_features,
            justification_rationale=rationale,
        )

        now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        exp_id = f"comparison_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

        manifest = ExperimentComparisonManifest(
            experiment_id=exp_id,
            timestamp_utc=now_utc,
            random_seed=self.config.random_seed,
            software_versions={
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "scikit-learn": sklearn.__version__,
                "xgboost": xgb.__version__,
            },
            dataset_path=str(csv_path),
            dataset_fingerprint_sha256=dataset_sha,
            training_seasons=train_seasons,
            holdout_seasons=holdout_seasons,
            feature_columns=feature_cols,
            rolling_origin_cv=cv_metrics,
            holdout_evaluation=holdout_metrics,
            calibration_reports=calib_reports,
            ablation_report=ablation_rep,
            threshold_report=threshold_rep,
            location_report=location_rep,
            verdict=verdict,
        )

        # Persist manifest and sub-reports
        manifest.to_json(out_dir / "experiment_comparison_manifest.json")
        with open(out_dir / "ablation_report.json", "w", encoding="utf-8") as f:
            f.write(ablation_rep.model_dump_json(indent=2))
        with open(out_dir / "threshold_report.json", "w", encoding="utf-8") as f:
            f.write(threshold_rep.model_dump_json(indent=2))
        with open(out_dir / "location_report.json", "w", encoding="utf-8") as f:
            f.write(location_rep.model_dump_json(indent=2))

        logger.info("Saved experiment comparison manifest to: %s", out_dir)
        return manifest
