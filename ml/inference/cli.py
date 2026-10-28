"""Command-line interface for loading model artifacts and executing climate risk predictions."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ml.inference.predictor import EnsoRiskPredictor, InvalidFeatureValueError, MissingFeatureError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enso_ml.inference.cli")

SAMPLE_EL_NINO_INPUT: dict[str, float] = {
    "oni_aso_degc": 1.6,
    "oni_trend_aso_jas_degc": 0.5,
    "oni_trend_aso_jja_degc": 0.8,
    "nino34_aso_sst_degc": 28.283,
    "nino34_aso_anom_degc": 1.55,
    "nino34_oct_anom_degc": 2.0,
    "nino34_trend_oct_aug_degc": 0.95,
    "precip_oct_mm": 25.0,
    "precip_oct_zscore": -1.7175,
    "precip_antecedent_spring_mm": 37.4,
}


def cmd_predict(args: argparse.Namespace) -> int:
    """Execute risk prediction using a persisted model manifest."""
    model_dir = Path(args.model_dir)
    if not model_dir.is_dir():
        logger.error("Model directory does not exist: %s", model_dir)
        return 1

    try:
        predictor = EnsoRiskPredictor(model_dir)
    except Exception as e:
        logger.error("Failed to load model from %s: %s", model_dir, e)
        return 1

    # Load input features
    features: dict[str, Any]
    if args.sample:
        logger.info("Using sample 1982/83 Super El Niño input profile.")
        features = SAMPLE_EL_NINO_INPUT
    elif args.input_json:
        input_str = args.input_json.strip()
        if Path(input_str).is_file():
            with open(input_str, encoding="utf-8") as f:
                features = json.load(f)
        else:
            try:
                features = json.loads(input_str)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON input: %s", e)
                return 1
    else:
        logger.error("Must provide either --input-json '<json_string_or_filepath>' or --sample.")
        return 1

    try:
        result = predictor.predict_risk(features, decision_threshold=args.threshold)
        print("\n" + "=" * 70)
        print("ENSO Shield Seasonal Climate Risk Assessment")
        print("=" * 70)
        print(f"Model ID:                {result['model_id']}")
        print(f"Target:                  {result['target_variable']}")
        print(f"Lead Time:               {result['lead_time']}")
        print("-" * 70)
        print(f"Forecast Drought Prob:   {result['drought_probability']:.1%}")
        print(f"Climatological Baseline: {result['climatological_base_rate']:.1%}")
        print(f"Risk Elevation Ratio:    {result['risk_ratio']:.2f}x reference base rate")
        thresh = result["decision_threshold"]
        print(f"Binary Trigger (>= {thresh:.2f}):    {bool(result['binary_prediction'])}")
        print("-" * 70)
        print("Top Contributing Factors:")
        for factor, weight in result["top_contributing_factors"].items():
            print(f"  * {factor:28s}: {weight:+.4f}")
        print("=" * 70)
        return 0
    except MissingFeatureError as e:
        logger.error("Prediction rejected due to missing features: %s", e)
        return 1
    except InvalidFeatureValueError as e:
        logger.error("Prediction rejected due to invalid feature value: %s", e)
        return 1
    except Exception as e:
        logger.exception("Prediction failed: %s", e)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for inference CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m ml.inference.cli",
        description="ENSO Shield climate risk prediction CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict_parser = subparsers.add_parser("predict", help="Generate drought risk prediction.")
    predict_parser.add_argument(
        "--model-dir",
        default="models/logistic_regression_baseline",
        help="Path to directory containing model_manifest.json.",
    )
    predict_parser.add_argument(
        "--input-json",
        help="JSON string or path to JSON file containing predictor features.",
    )
    predict_parser.add_argument(
        "--sample",
        action="store_true",
        help="Use a pre-configured sample El Niño feature profile.",
    )
    predict_parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Decision threshold for binary prediction (default: 0.5).",
    )
    predict_parser.set_defaults(func=cmd_predict)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
