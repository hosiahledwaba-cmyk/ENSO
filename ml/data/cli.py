"""Command-line interface for climate data ingestion, validation, and provenance."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from ml.data.adapters.chirps_rainfall import ChirpsRainfallAdapter
from ml.data.adapters.noaa_nino34 import NoaaNino34Adapter
from ml.data.adapters.noaa_oni import NoaaOniAdapter
from ml.data.pipeline import IngestionPipeline
from ml.data.provenance.tracker import compute_sha256

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("enso_ml.cli")

REPO_ROOT = Path(__file__).resolve().parents[2]


def setup_fixtures_in_raw(raw_dir: Path) -> dict[str, Path]:
    """Copy deterministic test fixtures to raw directory for demonstration/testing."""
    fixture_dir = REPO_ROOT / "data" / "fixtures"
    mapping = {
        "chirps_rainfall": (
            fixture_dir / "chirps_sample.csv",
            raw_dir / "chirps_sample.csv",
        ),
        "noaa_oni": (
            fixture_dir / "noaa_oni_sample.txt",
            raw_dir / "noaa_oni_sample.txt",
        ),
        "noaa_nino34": (
            fixture_dir / "noaa_nino34_sample.txt",
            raw_dir / "noaa_nino34_sample.txt",
        ),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for source_id, (src, dst) in mapping.items():
        if src.is_file():
            shutil.copy2(src, dst)
            out[source_id] = dst
        else:
            logger.warning("Fixture not found: %s", src)
    return out


def cmd_ingest(args: argparse.Namespace) -> int:
    """Execute end-to-end data ingestion."""
    raw_dir = Path(args.raw_dir)
    cleaned_dir = Path(args.cleaned_dir)
    derived_dir = Path(args.derived_dir)
    manifest_dir = Path(args.manifest_dir)

    for d in (cleaned_dir, derived_dir, manifest_dir):
        d.mkdir(parents=True, exist_ok=True)

    pipeline = IngestionPipeline()

    if args.use_fixtures:
        logger.info("Initializing raw storage using deterministic fixtures...")
        raw_files = setup_fixtures_in_raw(raw_dir)
    else:
        # Auto-discover raw files in raw_dir
        raw_files = {}
        for f in raw_dir.glob("*"):
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if "chirps" in name_lower or "rain" in name_lower or "precip" in name_lower:
                raw_files["chirps_rainfall"] = f
            elif "oni" in name_lower:
                raw_files["noaa_oni"] = f
            elif "nino" in name_lower or "sst" in name_lower:
                raw_files["noaa_nino34"] = f

    if not raw_files:
        logger.error(
            "No raw dataset files found in %s. Place source files in %s or use --use-fixtures.",
            raw_dir,
            raw_dir,
        )
        return 1

    sources_to_run = [args.source] if args.source else list(raw_files.keys())

    logger.info("Beginning ingestion for sources: %s", sources_to_run)
    ingested_count = 0
    for source_id in sources_to_run:
        if source_id not in raw_files:
            logger.error("No raw file provided for source '%s'", source_id)
            continue
        raw_f = raw_files[source_id]
        logger.info(
            "Ingesting %s from %s (SHA-256: %s)...",
            source_id,
            raw_f.name,
            compute_sha256(raw_f)[:12],
        )
        try:
            pipeline.ingest_dataset(source_id, raw_f, cleaned_dir, manifest_dir)
            ingested_count += 1
        except (ValueError, OSError, KeyError) as exc:
            logger.error("Failed to ingest %s: %s", source_id, exc)
            return 2

    # If all 3 primary datasets are present, construct the derived seasonal analysis dataset
    cleaned_chirps = cleaned_dir / "chirps_rainfall_monthly.csv"
    cleaned_oni = cleaned_dir / "noaa_oni_monthly.csv"
    cleaned_nino34 = cleaned_dir / "noaa_nino34_monthly.csv"

    if cleaned_chirps.is_file() and cleaned_oni.is_file() and cleaned_nino34.is_file():
        logger.info("Constructing derived seasonal analysis dataset (zero-lookahead alignment)...")
        try:
            derived_df, _derived_manifest = pipeline.build_derived_seasonal_dataset(
                cleaned_dir, derived_dir, manifest_dir
            )
            logger.info(
                "Derived dataset generated: %d historical seasons ready for analysis.",
                len(derived_df),
            )
        except (ValueError, OSError, KeyError) as exc:
            logger.error("Failed to construct derived analysis dataset: %s", exc)
            return 3

    print("\n[SUCCESS] Climate-data ingestion pipeline completed successfully.")
    print(f"  - Raw data tier:      {raw_dir}")
    print(f"  - Cleaned data tier:  {cleaned_dir}")
    print(f"  - Derived data tier:  {derived_dir}")
    print(f"  - Provenance ledger:  {manifest_dir}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a raw dataset file against its source adapter schema."""
    target_path = Path(args.filepath)
    if not target_path.is_file():
        logger.error("Target file does not exist: %s", target_path)
        return 1

    adapters = {
        "chirps_rainfall": ChirpsRainfallAdapter(),
        "noaa_oni": NoaaOniAdapter(),
        "noaa_nino34": NoaaNino34Adapter(),
    }

    if args.source not in adapters:
        logger.error(
            "Invalid source adapter '%s'. Choose from: %s",
            args.source,
            list(adapters.keys()),
        )
        return 1

    adapter = adapters[args.source]
    print(f"Validating {target_path.name} with adapter {adapter.source_id} ({adapter.version})...")
    raw_df = adapter.load_raw(target_path)
    report = adapter.validate(raw_df)

    print(f"\n--- Validation Report: {report.dataset_id} ---")
    print(f"Status:        {'PASSED' if report.is_valid else 'FAILED'}")
    print(f"Total Records: {report.total_records}")
    print("\nChecks performed:")
    for chk in report.checks:
        icon = "[PASS]" if chk.passed else "[FAIL]"
        print(f"  {icon} {chk.name}: {chk.detail}")
        if chk.sample_errors:
            for s in chk.sample_errors:
                print(f"         > {s}")

    return 0 if report.is_valid else 2


def cmd_provenance(args: argparse.Namespace) -> int:
    """Calculate and display SHA-256 digest and inspect any linked provenance manifests."""
    target_path = Path(args.filepath)
    if not target_path.is_file():
        logger.error("Target file does not exist: %s", target_path)
        return 1

    sha256 = compute_sha256(target_path)
    print(f"File:    {target_path}")
    print(f"Size:    {target_path.stat().st_size} bytes")
    print(f"SHA-256: {sha256}")

    # Check for adjacent manifest
    stem = target_path.stem.replace("_sample", "").replace("_monthly", "")
    manifest_candidates = [
        target_path.parent / f"{stem}_provenance.json",
        REPO_ROOT / "data" / "provenance" / f"{stem}_provenance.json",
        REPO_ROOT / "data" / "provenance" / f"{stem}_monthly_provenance.json",
    ]
    found = False
    for mc in manifest_candidates:
        if mc.is_file():
            print(f"\nFound linked provenance manifest: {mc}")
            print(mc.read_text(encoding="utf-8"))
            found = True
            break
    if not found:
        print("\nNo associated provenance manifest found for this file.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.data.cli",
        description="ENSO Shield Climate Data Ingestion and Validation Engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest subcommand
    p_ingest = subparsers.add_parser(
        "ingest", help="Ingest raw datasets into cleaned and derived tiers"
    )
    p_ingest.add_argument(
        "--raw-dir", default=str(REPO_ROOT / "data" / "raw"), help="Raw files directory"
    )
    p_ingest.add_argument(
        "--cleaned-dir",
        default=str(REPO_ROOT / "data" / "cleaned"),
        help="Cleaned files directory",
    )
    p_ingest.add_argument(
        "--derived-dir",
        default=str(REPO_ROOT / "data" / "derived"),
        help="Derived analysis directory",
    )
    p_ingest.add_argument(
        "--manifest-dir",
        default=str(REPO_ROOT / "data" / "provenance"),
        help="Manifests directory",
    )
    p_ingest.add_argument("--source", default=None, help="Filter to specific source ID")
    p_ingest.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Initialize raw dir with deterministic test fixtures",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    # Validate subcommand
    p_val = subparsers.add_parser("validate", help="Validate a raw dataset file")
    p_val.add_argument("filepath", help="Path to raw dataset file")
    p_val.add_argument(
        "--source",
        required=True,
        choices=["chirps_rainfall", "noaa_oni", "noaa_nino34"],
        help="Source adapter ID",
    )
    p_val.set_defaults(func=cmd_validate)

    # Provenance subcommand
    p_prov = subparsers.add_parser(
        "provenance", help="Compute SHA-256 and display linked provenance"
    )
    p_prov.add_argument("filepath", help="Path to file")
    p_prov.set_defaults(func=cmd_provenance)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
