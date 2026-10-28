"""CLI and runner for precomputing reproducible defensive anomaly and FDI benchmarks."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from ml.defense.simulation.harness import SimulationHarness
from ml.inference.predictor import EnsoRiskPredictor

logger = logging.getLogger("enso_ml.defense.runner")


def generate_defense_benchmarks(
    features_csv_path: Path | str = "data/features/enso_rainfall_features_labelled.csv",
    model_dir: Path | str = "models/logistic_regression_baseline",
    output_path: Path | str = "reports/defense/simulation_benchmark.json",
    seed: int = 42,
) -> Path:
    """Run reproducible 5-scenario security benchmark suite and persist machine-readable report."""
    csv_file = Path(features_csv_path)
    if not csv_file.is_file():
        raise FileNotFoundError(f"Labelled features dataset not found at: {csv_file}")

    df_clean = pd.read_csv(csv_file)

    predictor = None
    model_path = Path(model_dir)
    if (model_path / "model_manifest.json").is_file():
        try:
            predictor = EnsoRiskPredictor(model_path)
            logger.info("Loaded EnsoRiskPredictor from %s for benchmark evaluation.", model_path)
        except Exception as e:
            logger.warning("Could not load EnsoRiskPredictor: %s. Using internal estimator.", e)

    harness = SimulationHarness()
    report = harness.run_benchmark_suite(df_clean=df_clean, seed=seed, predictor=predictor)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)

    logger.info("Defense benchmark report written to: %s", out_file)
    return out_file


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_defense_benchmarks()
