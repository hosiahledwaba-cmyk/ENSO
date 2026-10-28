"""End-to-end climate model training experiment and holdout evaluation orchestrator."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ml.data.provenance.tracker import compute_sha256
from ml.evaluation.metrics import compute_probabilistic_metrics
from ml.registry.manifest import FeatureSchemaEntry, ModelManifest
from ml.training.baseline import ClimatologyBaseline
from ml.training.config import TrainingConfig
from ml.training.cross_validation import RollingOriginEvaluator
from ml.training.models import LogisticRegressionPredictor

logger = logging.getLogger("enso_ml.training.experiment")


class ClimateModelExperiment:
    """Orchestrates model fitting, rolling-origin CV, holdout testing, and manifest generation."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()
        self.rolling_evaluator = RollingOriginEvaluator(self.config)

    def run(
        self,
        features_csv_path: Path | str,
        output_model_dir: Path | str,
        holdout_seasons_count: int = 2,
    ) -> tuple[LogisticRegressionPredictor, ClimatologyBaseline, ModelManifest]:
        """Execute full training and evaluation protocol.

        Parameters
        ----------
        features_csv_path : Path | str
            Path to labelled feature dataset CSV.
        output_model_dir : Path | str
            Directory to persist fitted models, evaluation summaries, and manifest.
        holdout_seasons_count : int, default 2
            Number of recent seasons reserved as untouched holdout when 'split' is not configured.

        Returns
        -------
        tuple[LogisticRegressionPredictor, ClimatologyBaseline, ModelManifest]
            Trained logistic model, baseline, and populated model manifest.
        """
        feat_path = Path(features_csv_path)
        out_dir = Path(output_model_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not feat_path.is_file():
            raise FileNotFoundError(f"Feature dataset not found: {feat_path}")

        df = pd.read_csv(feat_path)
        dataset_sha = compute_sha256(feat_path)

        cfg = self.config
        target_col = cfg.target_column
        feature_cols = cfg.feature_columns

        # Verify required columns exist
        missing_features = [c for c in feature_cols if c not in df.columns]
        if missing_features:
            raise ValueError(f"Features CSV missing required columns: {missing_features}")
        if target_col not in df.columns:
            raise ValueError(f"Features CSV missing target column: '{target_col}'")

        # Separate training partition and untouched holdout partition
        df_sorted = df.sort_values("season_year").reset_index(drop=True)

        # Check if 'split' column indicates holdout (e.g. 'test')
        if "split" in df_sorted.columns and "test" in df_sorted["split"].values:
            train_df = df_sorted[df_sorted["split"] != "test"].copy()
            holdout_df = df_sorted[df_sorted["split"] == "test"].copy()
        else:
            # Fallback: reserve final holdout_seasons_count seasons as untouched holdout
            if len(df_sorted) <= cfg.min_train_seasons:
                raise ValueError(
                    f"Insufficient seasons (N={len(df_sorted)}) to reserve holdout period."
                )
            n_holdout = min(holdout_seasons_count, max(1, len(df_sorted) - cfg.min_train_seasons))
            split_idx = len(df_sorted) - n_holdout
            train_df = df_sorted.iloc[:split_idx].copy()
            holdout_df = df_sorted.iloc[split_idx:].copy()

        train_seasons = sorted(int(s) for s in train_df["season_year"].tolist())
        holdout_seasons = sorted(int(s) for s in holdout_df["season_year"].tolist())

        logger.info(
            "Partitioning: Train %d seasons (%s), Holdout %d seasons (%s)",
            len(train_seasons),
            train_seasons,
            len(holdout_seasons),
            holdout_seasons,
        )

        # 1. Execute Chronological Rolling-Origin Evaluation over Training Partition
        _oof_df, _rolling_base_metrics, rolling_model_metrics = self.rolling_evaluator.evaluate(
            train_df
        )

        # 2. Fit Final Climatological Baseline strictly on Training Partition
        y_train = train_df[target_col].to_numpy(dtype=int)
        baseline = ClimatologyBaseline().fit(y_train)

        # 3. Fit Final Logistic Regression Classifier strictly on Training Partition
        model = LogisticRegressionPredictor().fit(
            X=train_df[feature_cols],
            y=y_train,
            config=cfg,
        )

        # 4. Evaluate Final Models once on Untouched Holdout Partition
        y_holdout = holdout_df[target_col].to_numpy(dtype=int)
        p_base_holdout = baseline.predict_proba(len(holdout_df))[:, 1]
        p_model_holdout = model.predict_proba(holdout_df[feature_cols])[:, 1]

        holdout_base_metrics = compute_probabilistic_metrics(
            y_true=y_holdout,
            y_prob=p_base_holdout,
            y_prob_reference=p_base_holdout,
            decision_threshold=cfg.decision_threshold,
        )

        holdout_model_metrics = compute_probabilistic_metrics(
            y_true=y_holdout,
            y_prob=p_model_holdout,
            y_prob_reference=p_base_holdout,
            decision_threshold=cfg.decision_threshold,
        )

        # 5. Scientific Assessment: Does Model Beat Baseline on Holdout?
        # A lower Brier score indicates superior probabilistic accuracy.
        beats_baseline = bool(holdout_model_metrics.brier_score < holdout_base_metrics.brier_score)
        holdout_bss = holdout_model_metrics.brier_skill_score

        if beats_baseline:
            logger.info(
                "Model OUTPERFORMS baseline on holdout: BS_model=%.4f vs BS_base=%.4f (BSS=+%.4f)",
                holdout_model_metrics.brier_score,
                holdout_base_metrics.brier_score,
                holdout_bss or 0.0,
            )
        else:
            logger.warning(
                "Model DOES NOT beat baseline on holdout: BS_model=%.4f vs BS_base=%.4f (BSS=%.4f)",
                holdout_model_metrics.brier_score,
                holdout_base_metrics.brier_score,
                holdout_bss or 0.0,
            )

        # 6. Build Feature Schema Entries
        schema_entries = [
            FeatureSchemaEntry(
                name=f,
                dtype="float",
                unit="dimensionless" if "zscore" in f else ("degC" if "degc" in f else "mm"),
                mean_training=model.scaler_mean.get(f),
                scale_training=model.scaler_scale.get(f),
            )
            for f in feature_cols
        ]

        # 7. Persist model weights and baseline first to establish immutable artefacts
        with open(out_dir / "baseline.json", "w", encoding="utf-8") as f:
            json.dump(baseline.to_dict(), f, indent=2)
        with open(out_dir / "logistic_regression.json", "w", encoding="utf-8") as f:
            json.dump(model.to_dict(), f, indent=2)

        # 8. Compute cryptographic SHA-256 artefact digest
        import hashlib

        hasher = hashlib.sha256()
        with open(out_dir / "logistic_regression.json", "rb") as fb:
            while chunk := fb.read(65536):
                hasher.update(chunk)
        artefact_sha = hasher.hexdigest()

        summary = {
            "model_id": f"enso_logistic_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            "target": target_col,
            "training_seasons": train_seasons,
            "holdout_seasons": holdout_seasons,
            "rolling_origin_brier_score": rolling_model_metrics.brier_score,
            "rolling_origin_bss": rolling_model_metrics.brier_skill_score,
            "holdout_baseline_brier_score": holdout_base_metrics.brier_score,
            "holdout_model_brier_score": holdout_model_metrics.brier_score,
            "holdout_bss": holdout_bss,
            "beats_baseline_on_holdout": beats_baseline,
        }
        with open(out_dir / "evaluation_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # 9. Construct and Persist Reproducible Model Manifest v2.0
        now_utc = datetime.now(UTC).isoformat()
        manifest = ModelManifest(
            manifest_version="2.0",
            model_id=summary["model_id"],
            model_version="1.0.0",
            model_type="regularized_logistic_regression",
            approval_status="APPROVED",
            created_at_utc=now_utc,
            training_config=cfg.model_dump(),
            dataset_id="enso_rainfall_features_labelled",
            dataset_version="1.0-features",
            dataset_sha256=dataset_sha,
            training_data_fingerprint=dataset_sha,
            training_seasons=train_seasons,
            holdout_seasons=holdout_seasons,
            target_variable=target_col,
            artefact_digest=artefact_sha,
            artefact_relpath="logistic_regression.json",
            feature_schema=schema_entries,
            scaler_means=model.scaler_mean,
            scaler_scales=model.scaler_scale,
            intercept=model.intercept,
            coefficients=model.coefficients,
            fallback_base_rate=model.fallback_base_rate,
            rolling_origin_metrics=rolling_model_metrics,
            holdout_metrics=holdout_model_metrics,
            baseline_holdout_metrics=holdout_base_metrics,
            beats_baseline_on_holdout=beats_baseline,
            holdout_bss=holdout_bss,
            evaluation_report=summary,
        )

        manifest.to_json(out_dir / "model_manifest.json")

        return model, baseline, manifest
