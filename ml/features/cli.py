"""Command-line interface for ENSO Shield feature and target generation pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ml.features.config import FeaturePipelineConfig
from ml.features.data_dictionary import (
    generate_data_dictionary_markdown,
    save_data_dictionary_markdown,
)
from ml.features.leakage import TargetLeakageDetector
from ml.features.pipeline import FeaturePipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enso_ml.features.cli")


def cmd_generate(args: argparse.Namespace) -> int:
    """Execute feature extraction and target labelling."""
    cleaned_dir = Path(args.cleaned_dir)
    output_dir = Path(args.output_dir)
    manifest_dir = Path(args.manifest_dir)

    # If --use-fixtures specified and cleaned dir empty, ingest fixtures first
    if args.use_fixtures:
        chirps_clean = cleaned_dir / "chirps_rainfall_monthly.csv"
        if not chirps_clean.is_file():
            logger.info("Cleaned inputs missing. Ingesting from fixtures first...")
            from ml.data.cli import cmd_ingest

            ingest_args = argparse.Namespace(
                use_fixtures=True,
                source=None,
                raw_dir="data/raw",
                cleaned_dir=str(cleaned_dir),
                derived_dir="data/derived",
                manifest_dir=str(manifest_dir),
            )
            ingest_code = cmd_ingest(ingest_args)
            if ingest_code != 0:
                logger.error("Fixture ingestion failed.")
                return ingest_code

    pipeline = FeaturePipeline(FeaturePipelineConfig())
    try:
        df, ref_dist, _manifest = pipeline.run(
            cleaned_dir=cleaned_dir,
            output_dir=output_dir,
            manifest_dir=manifest_dir,
            include_lag1=args.include_lag1,
        )
        print("\n" + "=" * 70)
        print("Feature and Target Generation Completed Successfully!")
        print("=" * 70)
        s_min, s_max = df["season_year"].min(), df["season_year"].max()
        print(f"Total Seasons Labelled: {len(df)} ({s_min} to {s_max})")
        print(
            f"Reference Climatology:  mean={ref_dist.mean_seasonal_precip_mm:.1f} mm, "
            f"std={ref_dist.std_seasonal_precip_mm:.1f} mm"
        )
        print(
            f"Drought Target (tau_20): {ref_dist.tau_drought_p20_mm:.1f} mm "
            f"(N_train={ref_dist.n_train})"
        )
        print(f"Below-Normal (tau_33):  {ref_dist.tau_below_normal_p33_mm:.1f} mm")
        print(f"Output Dataset:         {output_dir / 'enso_rainfall_features_labelled.csv'}")
        print(f"Provenance Manifest:    {manifest_dir / 'enso_rainfall_features_provenance.json'}")
        print(f"Data Dictionary:        {output_dir / 'DATA_DICTIONARY.md'}")
        print("=" * 70)
        return 0
    except Exception as e:
        logger.exception("Feature generation failed: %s", e)
        return 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate timeline integrity and partition hygiene of a labelled feature dataset."""
    import pandas as pd

    filepath = Path(args.filepath)
    if not filepath.is_file():
        logger.error("Feature file not found: %s", filepath)
        return 1

    df = pd.read_csv(filepath)
    try:
        TargetLeakageDetector.validate_timeline_integrity(df)
        TargetLeakageDetector.validate_partition_isolation(df)
        print(f"Validation PASSED: {filepath} ({len(df)} records verified with zero lookahead).")
        return 0
    except Exception as e:
        logger.error("Validation FAILED: %s", e)
        return 1


def cmd_data_dict(args: argparse.Namespace) -> int:
    """Print or export data dictionary."""
    if args.output:
        save_data_dictionary_markdown(args.output)
        print(f"Data dictionary exported to: {args.output}")
    else:
        print(generate_data_dictionary_markdown())
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.features.cli",
        description="ENSO Shield feature and target generation CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    gen_parser = subparsers.add_parser(
        "generate",
        help="Extract zero-lookahead features and label drought targets.",
    )
    gen_parser.add_argument(
        "--cleaned-dir",
        default="data/cleaned",
        help="Directory with cleaned monthly climate data.",
    )
    gen_parser.add_argument(
        "--output-dir",
        default="data/features",
        help="Directory to save generated feature matrices.",
    )
    gen_parser.add_argument(
        "--manifest-dir",
        default="data/provenance",
        help="Directory to save cryptographic provenance manifest.",
    )
    gen_parser.add_argument(
        "--include-lag1",
        action="store_true",
        help="Require prior-season DJF rainfall as a feature.",
    )
    gen_parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Automatically populate from test fixtures if cleaned data is missing.",
    )
    gen_parser.set_defaults(func=cmd_generate)

    # validate
    val_parser = subparsers.add_parser(
        "validate",
        help="Validate an existing feature dataset for lookahead or leakage.",
    )
    val_parser.add_argument("filepath", help="Path to labelled feature CSV.")
    val_parser.set_defaults(func=cmd_validate)

    # data-dict
    dict_parser = subparsers.add_parser(
        "data-dict",
        help="Display or export data dictionary specification.",
    )
    dict_parser.add_argument(
        "--output",
        "-o",
        help="Optional path to write markdown file.",
    )
    dict_parser.set_defaults(func=cmd_data_dict)

    return parser


def main() -> None:
    """Entry point for feature CLI."""
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
