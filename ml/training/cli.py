"""Command-line interface for climate model training and evaluation experiments."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ml.training.config import TrainingConfig
from ml.training.experiment import ClimateModelExperiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enso_ml.training.cli")


def cmd_train(args: argparse.Namespace) -> int:
    """Execute model training experiment, rolling-origin CV, and holdout evaluation."""
    features_path = Path(args.features_path)
    model_dir = Path(args.model_dir)

    # If features file is missing, automatically generate from fixtures if requested
    if not features_path.is_file():
        if args.use_fixtures:
            logger.info("Features dataset missing. Running feature pipeline with fixtures...")
            from ml.features.cli import cmd_generate

            gen_args = argparse.Namespace(
                use_fixtures=True,
                cleaned_dir="data/cleaned",
                output_dir="data/features",
                manifest_dir="data/provenance",
                include_lag1=False,
            )
            gen_code = cmd_generate(gen_args)
            if gen_code != 0:
                logger.error("Feature pipeline failed.")
                return gen_code
        else:
            logger.error("Features dataset not found: %s", features_path)
            return 1

    cfg = TrainingConfig(
        target_column=args.target,
        c_regularization=args.c_reg,
        random_seed=args.seed,
    )

    experiment = ClimateModelExperiment(cfg)
    try:
        _model, _baseline, manifest = experiment.run(
            features_csv_path=features_path,
            output_model_dir=model_dir,
            holdout_seasons_count=args.holdout_count,
        )

        ro_metrics = manifest.rolling_origin_metrics
        ho_metrics = manifest.holdout_metrics
        base_ho_metrics = manifest.baseline_holdout_metrics

        bss_cv = (ro_metrics.brier_skill_score or 0.0) if ro_metrics else 0.0
        bss_holdout = manifest.holdout_bss or 0.0
        unc_std = ro_metrics.prediction_uncertainty_std if ro_metrics else 0.0

        print("\n" + "=" * 76)
        print("Climate Model Experiment Completed Successfully!")
        print("=" * 76)
        print(f"Model ID:              {manifest.model_id}")
        print(f"Target Variable:       {manifest.target_variable}")
        print(f"Training Seasons (N={len(manifest.training_seasons)}): {manifest.training_seasons}")
        print(f"Holdout Seasons (N={len(manifest.holdout_seasons)}):  {manifest.holdout_seasons}")
        print("-" * 76)
        print("1. ROLLING-ORIGIN CROSS-VALIDATION RESULTS (Expanding Window):")
        if ro_metrics:
            print(f"   * Brier Score (BS):        {ro_metrics.brier_score:.5f}")
            print(f"   * Brier Skill Score (BSS): {bss_cv:+.4f}")
            base_rate_cv = ro_metrics.observed_base_rate
            print(f"   * Event Frequency:         {base_rate_cv:.3f}")
            print(f"   * Prediction Uncertainty:  {unc_std:.4f}")
            if ro_metrics.murphy:
                m = ro_metrics.murphy
                print(
                    f"   * Murphy Decomposition:    "
                    f"Rel={m.reliability:.5f}, Res={m.resolution:.5f}, Unc={m.uncertainty:.5f}"
                )
        print("-" * 76)
        print("2. FINAL UNTOUCHED HOLDOUT EVALUATION:")
        if base_ho_metrics:
            print(f"   * Baseline Holdout BS:     {base_ho_metrics.brier_score:.5f}")
        if ho_metrics:
            print(f"   * Model Holdout BS:        {ho_metrics.brier_score:.5f}")
            print(f"   * Holdout BSS:             {bss_holdout:+.4f}")
            print(f"   * Holdout Log Loss:        {ho_metrics.log_loss:.5f}")
        print("-" * 76)
        print("3. SCIENTIFIC VERDICT ON HOLDOUT PERFORMANCE:")
        if manifest.beats_baseline_on_holdout:
            print("   [+] SUPERIORITY CONFIRMED:")
            print("       The regularized logistic model beat the historical climatology")
            print(f"       reference on the holdout period (BSS = {bss_holdout:+.4f}).")
        else:
            print("   [-] HONEST SCIENTIFIC REPORTING (NO SUPERIORITY):")
            print("       The regularized logistic regression model DID NOT outperform")
            print(f"       climatological baseline on holdout (BSS = {bss_holdout:+.4f}).")
            print("       The historical climatology reference remains superior or equal.")
        print("-" * 76)
        print(f"Fitted Model Manifest: {model_dir / 'model_manifest.json'}")
        print(f"Evaluation Summary:    {model_dir / 'evaluation_summary.json'}")
        print("=" * 76)
        return 0
    except Exception as e:
        logger.exception("Experiment execution failed: %s", e)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for training CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.training.cli",
        description="ENSO Shield climate model training and evaluation CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="Train baseline and logistic regression.")
    train_parser.add_argument(
        "--features-path",
        default="data/features/enso_rainfall_features_labelled.csv",
        help="Path to labelled feature dataset CSV.",
    )
    train_parser.add_argument(
        "--model-dir",
        default="models/logistic_regression_baseline",
        help="Directory to save trained model artifacts.",
    )
    train_parser.add_argument(
        "--target",
        default="target_drought_p20",
        help="Target column ('target_drought_p20' or 'target_below_normal_p33').",
    )
    train_parser.add_argument(
        "--c-reg",
        type=float,
        default=1.0,
        help="Inverse regularization strength C (default: 1.0).",
    )
    train_parser.add_argument(
        "--holdout-count",
        type=int,
        default=2,
        help="Number of seasons to hold out as untouched test period (default: 2).",
    )
    train_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42).",
    )
    train_parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Automatically generate features from fixtures if missing.",
    )
    train_parser.set_defaults(func=cmd_train)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
