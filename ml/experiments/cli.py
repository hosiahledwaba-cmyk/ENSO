"""Command-line interface for multi-model experiment comparison and diagnostic suites."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ml.experiments.comparison import MultiModelExperimentRunner
from ml.training.config import TrainingConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enso_ml.experiments.cli")


def cmd_compare(args: argparse.Namespace) -> int:
    """Execute multi-model comparison across Climatology, Logistic Regression, and XGBoost."""
    if args.use_fixtures:
        features_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "features"
            / "enso_rainfall_features_labelled.csv"
        )
    else:
        features_path = Path(args.features_csv)

    output_dir = Path(args.output_dir)
    cfg = TrainingConfig(random_seed=args.seed)
    runner = MultiModelExperimentRunner(cfg)

    try:
        manifest = runner.run(
            features_csv_path=features_path,
            output_dir=output_dir,
            holdout_count=args.holdout_count,
        )

        v = manifest.verdict
        ho = manifest.holdout_evaluation
        cv = manifest.rolling_origin_cv

        print("\n" + "=" * 78)
        print("ENSO SHIELD: MULTI-MODEL EXPERIMENT COMPARISON REPORT")
        print("=" * 78)
        print(f"Experiment ID:          {manifest.experiment_id}")
        print(f"Timestamp (UTC):        {manifest.timestamp_utc}")
        print(f"Random Seed:            {manifest.random_seed}")
        print(f"Dataset SHA-256:        {manifest.dataset_fingerprint_sha256[:16]}...")
        print(f"Training Seasons (N={len(manifest.training_seasons)}): {manifest.training_seasons}")
        print(f"Holdout Seasons (N={len(manifest.holdout_seasons)}):  {manifest.holdout_seasons}")
        print("-" * 78)
        print("1. EXPANDING-WINDOW ROLLING-ORIGIN CROSS-VALIDATION (Training Partition):")
        print("   " + "-" * 72)
        print("   Model                   | Brier Score | BSS vs Clim | Log Loss | ECE")
        print("   " + "-" * 72)
        for m_name, m_metrics in cv.items():
            bss_val = m_metrics.brier_skill_score or 0.0
            ece_val = m_metrics.expected_calibration_error or 0.0
            print(
                f"   {m_name:23s} |   {m_metrics.brier_score:.5f}   |   "
                f"{bss_val:+.4f}    |  {m_metrics.log_loss:.4f}  | {ece_val:.4f}"
            )
        print("-" * 78)
        print("2. FINAL UNTOUCHED HOLDOUT EVALUATION:")
        print("   " + "-" * 72)
        print("   Model                   | Brier Score | BSS vs Clim | Log Loss | Event Rate")
        print("   " + "-" * 72)
        for m_name, m_metrics in ho.items():
            bss_val = m_metrics.brier_skill_score or 0.0
            base_r = m_metrics.observed_base_rate
            print(
                f"   {m_name:23s} |   {m_metrics.brier_score:.5f}   |   "
                f"{bss_val:+.4f}    |  {m_metrics.log_loss:.4f}  | {base_r:.3f}"
            )
        print("-" * 78)
        print("3. FEATURE ABLATION FINDINGS:")
        for finding in manifest.ablation_report.key_findings:
            print(f"   * {finding}")
        print("-" * 78)
        print("4. CALIBRATION & OVERCONFIDENCE ANALYSIS:")
        for m_name, c_rep in manifest.calibration_reports.items():
            print(
                f"   * {m_name:23s}: ECE={c_rep.expected_calibration_error:.4f}, "
                f"Murphy Rel={c_rep.murphy_reliability:.5f}, Bias={c_rep.overconfidence_bias:+.4f}"
            )
        print("-" * 78)
        print("5. SCIENTIFIC COMPLEXITY VERDICT:")
        if v.is_nonlinear_complexity_justified:
            print("   [+] NONLINEAR COMPLEXITY JUSTIFIED:")
            print(f"       {v.justification_rationale}")
        else:
            print("   [-] NONLINEAR COMPLEXITY NOT JUSTIFIED (OCCAM'S RAZOR):")
            print(f"       {v.justification_rationale}")
            print(f"       Best Holdout Architecture: {v.best_holdout_model}")
        print("-" * 78)
        print(f"Comparison Manifest: {output_dir / 'experiment_comparison_manifest.json'}")
        print(f"Ablation Report:     {output_dir / 'ablation_report.json'}")
        print(f"Threshold Report:    {output_dir / 'threshold_report.json'}")
        print(f"Location Report:     {output_dir / 'location_report.json'}")
        print("=" * 78)
        return 0
    except Exception as e:
        logger.exception("Experiment comparison execution failed: %s", e)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.experiments.cli",
        description="ENSO Shield Multi-Model Experiment Comparison CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser("compare", help="Run multi-model comparison.")
    compare_parser.add_argument(
        "--features-csv",
        default="data/features/enso_rainfall_features_labelled.csv",
        help="Path to labelled feature CSV.",
    )
    compare_parser.add_argument(
        "--output-dir",
        default="reports/experiments/nonlinear_comparison",
        help="Directory to save comparison manifests and reports.",
    )
    compare_parser.add_argument(
        "--holdout-count",
        type=int,
        default=2,
        help="Number of untouched seasons reserved for final holdout testing.",
    )
    compare_parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    compare_parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Use built-in deterministic fixtures.",
    )
    compare_parser.set_defaults(func=cmd_compare)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
