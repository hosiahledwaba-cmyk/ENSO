"""Defensive data-anomaly detection and FDI simulation endpoints."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ml.defense.detector import DefensiveInspectionEngine
from ml.defense.models import (
    DefensiveInspectionReport,
    SimulationConfig,
    SimulationReport,
    SimulationScenarioResult,
)
from ml.defense.simulation.harness import SimulationHarness
from ml.inference.predictor import EnsoRiskPredictor

logger = logging.getLogger("enso_api.defense")

router = APIRouter(prefix="/api/v1/defense", tags=["Defensive Anomaly Detection & FDI Simulation"])

_BENCHMARK_PATH = Path("reports/defense/simulation_benchmark.json")
_FEATURES_CSV = Path("data/features/enso_rainfall_features_labelled.csv")
_MODEL_DIR = Path("models/logistic_regression_baseline")

_SCENARIO_METADATA = [
    {
        "id": "DATA_CORRUPTION",
        "name": "Data Corruption & Sentinel Injection",
        "category": "Data Quality / Physical Boundary",
        "description": (
            "Injects known environmental telemetry sentinels (-999.0), "
            "impossible negative rainfall (-45mm), extreme ocean temperatures (48.5C), "
            "and bit flips."
        ),
        "threat_model_ref": "Protocol 4.1 & RFC-003",
        "default_magnitude": 1.0,
        "default_ratio": 0.35,
    },
    {
        "id": "REPLAY_ATTACK",
        "name": "Telemetry Freeze & Sequence Replay",
        "category": "Temporal Spoofing / Dead Sensor",
        "description": (
            "Simulates dead sensor freeze (identical floating point values across 3+ periods) "
            "and replay of past historical seasons into the active evaluation window."
        ),
        "threat_model_ref": "Protocol 4.1 (Temporal Replay)",
        "default_magnitude": 1.0,
        "default_ratio": 0.40,
    },
    {
        "id": "MEASUREMENT_NOISE",
        "name": "High-Frequency Measurement Noise",
        "category": "Sensor Degradation",
        "description": (
            "Adds zero-mean Gaussian/Laplace noise to oceanographic telemetry, "
            "simulating instrument flutter, turbulence, and sensor calibration degradation."
        ),
        "threat_model_ref": "Protocol 4.1 (Stochastic Perturbation)",
        "default_magnitude": 1.0,
        "default_ratio": 0.35,
    },
    {
        "id": "MISSING_DATA",
        "name": "Telemetry Dropouts & Burst Packet Loss",
        "category": "Communication Failure",
        "description": (
            "Injects sporadic observation dropouts and burst communication loss (NaN/nulls) "
            "into critical input features."
        ),
        "threat_model_ref": "Protocol 4.1 (Telemetry Dropout)",
        "default_magnitude": 1.0,
        "default_ratio": 0.30,
    },
    {
        "id": "ADVERSARIAL_FDI",
        "name": "Stealthy False Data Injection (FDI)",
        "category": "Adversarial Cyber-Attack",
        "description": (
            "Targeted perturbations designed to induce forecast evasion (suppressing "
            "drought warnings) or disruption (inducing false alarms during normal years)."
        ),
        "threat_model_ref": "Protocol 1.2 (H2 & H3) & Section 4",
        "default_magnitude": 1.0,
        "default_ratio": 0.35,
    },
]


class TelemetryInspectionRequest(BaseModel):
    """Request payload for inspecting arbitrary telemetry or feature records."""

    series_id: str = "custom_telemetry_stream"
    records: list[dict[str, Any]] = Field(
        ...,
        description="List of observation records (dictionaries with feature names and values).",
    )


def _load_predictor() -> EnsoRiskPredictor | None:
    if (_MODEL_DIR / "model_manifest.json").is_file():
        try:
            return EnsoRiskPredictor(_MODEL_DIR)
        except Exception as e:
            logger.warning("Could not load predictor: %s", e)
    return None


@router.get(
    "/scenarios",
    summary="List defensive simulation scenarios and threat specifications",
)
async def list_scenarios() -> dict[str, Any]:
    """Return catalog of supported defensive anomaly and FDI attack scenarios."""
    return {
        "scenarios": _SCENARIO_METADATA,
        "protocol_reference": "research/protocol/research_protocol.md",
        "total_scenarios": len(_SCENARIO_METADATA),
    }


@router.get(
    "/benchmarks",
    response_model=SimulationReport,
    summary="Retrieve precomputed 5-scenario defensive security benchmark report",
)
async def get_defense_benchmarks() -> SimulationReport:
    """Return precomputed empirical security benchmark evaluation across all 5 scenarios."""
    if _BENCHMARK_PATH.is_file():
        try:
            with open(_BENCHMARK_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return SimulationReport.model_validate(data)
        except Exception as e:
            logger.warning("Error reading precomputed benchmark from %s: %s", _BENCHMARK_PATH, e)

    # Compute on the fly if not cached
    if not _FEATURES_CSV.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Features dataset {_FEATURES_CSV} not found to generate benchmark.",
        )

    df_clean = pd.read_csv(_FEATURES_CSV)
    predictor = _load_predictor()
    harness = SimulationHarness()
    report = harness.run_benchmark_suite(df_clean=df_clean, seed=42, predictor=predictor)
    return report


@router.post(
    "/simulate",
    response_model=SimulationScenarioResult,
    summary="Execute an isolated, reproducible perturbation simulation and evaluate defense",
)
async def simulate_scenario(config: SimulationConfig) -> SimulationScenarioResult:
    """Execute a controlled in-memory perturbation simulation.

    Evaluates:
    - Attack Detection Rate (ADR)
    - False Positive Rate (FPR)
    - Detection Delay
    - Forecast Degradation (Delta BS_attack)
    - Defensive Recovery Efficiency (RE)
    - Downstream risk category flips and probability shifts

    ISOLATION: Executed entirely in memory on isolated copies; never touches real ingestion
    or credentials.
    """
    if not _FEATURES_CSV.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Features dataset {_FEATURES_CSV} not found for simulation.",
        )

    df_clean = pd.read_csv(_FEATURES_CSV)
    predictor = _load_predictor()
    harness = SimulationHarness()

    try:
        result = harness.evaluate_scenario(
            df_clean=df_clean,
            config=config,
            predictor=predictor,
        )
        return result
    except Exception as e:
        logger.exception("Error executing simulation for scenario %s: %s", config.scenario, e)
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}") from e


@router.post(
    "/inspect",
    response_model=DefensiveInspectionReport,
    summary="Inspect arbitrary telemetry stream for statistical anomalies and perturbations",
)
async def inspect_telemetry(payload: TelemetryInspectionRequest) -> DefensiveInspectionReport:
    """Run transparent statistical checks and baseline multivariate detector on input records.

    INVARIANT: Ordinary statistical anomalies are never labelled as confirmed malicious activity.
    Classifications are strictly evidence-based with calibrated suspicion scores.
    """
    if not payload.records:
        raise HTTPException(status_code=400, detail="Payload records list cannot be empty.")

    df_input = pd.DataFrame(payload.records)
    engine = DefensiveInspectionEngine()

    try:
        report = engine.inspect_dataset(
            df=df_input,
            series_id=payload.series_id,
        )
        return report
    except Exception as e:
        logger.exception("Error inspecting dataset %s: %s", payload.series_id, e)
        raise HTTPException(status_code=500, detail=f"Inspection failed: {e}") from e
