"""Tests for controlled simulation harness, reproducible perturbations, and defense metrics."""

from __future__ import annotations

import pandas as pd
import pytest

from ml.defense.models import SimulationConfig
from ml.defense.simulation.harness import PerturbationEngine, SimulationHarness


@pytest.fixture
def sample_clean_features() -> pd.DataFrame:
    """Fixture providing clean labelled seasonal feature dataframe."""
    return pd.DataFrame(
        {
            "season_year": [1982, 1983, 1984, 1985, 1986, 1987, 1988],
            "oni_aso_degc": [-0.2, 1.6, -0.3, -0.5, -0.4, 0.7, 1.6],
            "oni_trend_aso_jas_degc": [-0.1, 0.5, -0.3, -0.2, 0.0, 0.3, 0.0],
            "oni_trend_aso_jja_degc": [0.0, 0.8, -0.6, -0.2, 0.0, 0.5, 0.2],
            "nino34_aso_sst_degc": [26.6, 28.3, 26.4, 26.2, 26.4, 27.4, 28.3],
            "nino34_aso_anom_degc": [-0.1, 1.5, -0.3, -0.5, -0.4, 0.7, 1.5],
            "nino34_oct_anom_degc": [-0.2, 2.0, -0.6, -0.8, -0.3, 1.0, 1.4],
            "nino34_trend_oct_aug_degc": [-0.1, 0.9, -0.6, -0.5, 0.1, 0.6, -0.2],
            "precip_oct_mm": [48.2, 25.0, 38.2, 42.5, 45.0, 39.5, 32.0],
            "precip_oct_zscore": [1.2, -1.7, -0.05, 0.48, 0.80, 0.11, -0.83],
            "precip_antecedent_spring_mm": [66.7, 37.4, 53.8, 56.7, 61.8, 54.5, 44.8],
            "target_drought_p20": [0, 1, 0, 0, 0, 0, 1],
        }
    )


def test_perturbation_isolation(sample_clean_features: pd.DataFrame) -> None:
    """Simulation harness must never mutate the clean input dataframe."""
    orig_copy = sample_clean_features.copy(deep=True)
    cfg = SimulationConfig(
        scenario="DATA_CORRUPTION",
        seed=101,
        target_feature="oni_aso_degc",
        injection_ratio=0.5,
    )
    df_attacked, labels = PerturbationEngine.apply_perturbation(sample_clean_features, cfg)

    # Clean dataframe remains untouched in memory
    pd.testing.assert_frame_equal(sample_clean_features, orig_copy)
    assert not df_attacked.equals(sample_clean_features)
    assert sum(labels) > 0


def test_perturbation_reproducibility(sample_clean_features: pd.DataFrame) -> None:
    """Perturbations with the same seed must produce identical outputs."""
    cfg = SimulationConfig(
        scenario="ADVERSARIAL_FDI",
        seed=999,
        target_feature="oni_aso_degc",
        injection_ratio=0.4,
    )
    df1, labels1 = PerturbationEngine.apply_perturbation(sample_clean_features, cfg)
    df2, labels2 = PerturbationEngine.apply_perturbation(sample_clean_features, cfg)

    pd.testing.assert_frame_equal(df1, df2)
    assert labels1 == labels2


@pytest.mark.parametrize(
    "scenario",
    [
        "DATA_CORRUPTION",
        "REPLAY_ATTACK",
        "MEASUREMENT_NOISE",
        "MISSING_DATA",
        "ADVERSARIAL_FDI",
    ],
)
def test_all_scenarios_evaluated_with_metrics(
    sample_clean_features: pd.DataFrame,
    scenario: str,
) -> None:
    """All 5 perturbation scenarios must execute, returning empirical security metrics."""
    harness = SimulationHarness()
    cfg = SimulationConfig(
        scenario=scenario,
        seed=42,
        target_feature="oni_aso_degc",
        perturbation_magnitude=1.0,
        injection_ratio=0.35,
    )
    result = harness.evaluate_scenario(sample_clean_features, cfg)

    assert result.scenario == scenario
    assert result.seed == 42
    assert 0.0 <= result.attack_detection_rate <= 1.0
    assert 0.0 <= result.false_positive_rate <= 1.0
    assert result.detection_delay_timesteps >= 0.0
    assert 0.0 <= result.defensive_recovery_efficiency <= 1.0
    assert len(result.detector_flags) == len(sample_clean_features)
    assert len(result.ground_truth_labels) == len(sample_clean_features)


def test_benchmark_suite_execution(sample_clean_features: pd.DataFrame) -> None:
    """Benchmark suite aggregates results across all 5 standard security scenarios."""
    harness = SimulationHarness()
    report = harness.run_benchmark_suite(sample_clean_features, seed=42)

    assert report.total_scenarios_evaluated == 5
    assert len(report.scenarios) == 5
    assert 0.0 <= report.mean_attack_detection_rate <= 1.0
    assert 0.0 <= report.mean_false_positive_rate <= 1.0
    assert 0.0 <= report.mean_recovery_efficiency <= 1.0
