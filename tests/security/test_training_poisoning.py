"""Unit and integration tests for training-data poisoning experiments and threat auditing."""

import shutil
from pathlib import Path

import pytest

from ml.data.provenance.tracker import compute_sha256
from ml.security.poisoning import TrainingPoisoningHarness


@pytest.fixture
def clean_dataset_fixture(tmp_path: Path) -> Path:
    """Fixture providing a copy of the canonical clean labelled features dataset."""
    src = Path("data/features/enso_rainfall_features_labelled.csv")
    dest = tmp_path / "enso_rainfall_features_labelled.csv"
    shutil.copy2(src, dest)
    return dest


def test_isolated_copy_preserves_clean_dataset(clean_dataset_fixture: Path, tmp_path: Path) -> None:
    """Verify that the harness operates strictly on isolated copies without modifying the clean file."""
    initial_sha = compute_sha256(clean_dataset_fixture)
    harness = TrainingPoisoningHarness(
        clean_dataset_path=clean_dataset_fixture,
        base_experiment_dir=tmp_path / "experiments",
    )

    isolated_csv, df_clean, clone_sha = harness.create_isolated_copy("exp_isolation_test")
    assert isolated_csv.is_file()
    assert clone_sha == initial_sha

    # Inject modification into isolated copy
    _df_mod, mod, mod_sha = harness.inject_label_flipping(df_clean, flip_fraction=0.30)
    assert mod.records_modified_count >= 1
    assert mod_sha != initial_sha

    # Assert clean dataset file is completely untouched
    assert harness.verify_clean_dataset_unmodified(initial_sha) is True
    assert compute_sha256(clean_dataset_fixture) == initial_sha


def test_label_flipping_experiment(clean_dataset_fixture: Path, tmp_path: Path) -> None:
    """Verify that label flipping impairs candidate model performance and produces comparative audit report."""
    harness = TrainingPoisoningHarness(
        clean_dataset_path=clean_dataset_fixture,
        base_experiment_dir=tmp_path / "experiments",
    )

    report = harness.run_experiment(
        attack_class="LABEL_FLIPPING",
        attack_params={"flip_fraction": 0.50},
        holdout_count=2,
    )

    assert report.attack_class == "LABEL_FLIPPING"
    assert report.records_modified > 0
    assert report.clean_training_fingerprint != report.poisoned_training_fingerprint
    assert len(report.threat_limitations) >= 3
    assert len(report.recovery_process) >= 5
    assert len(report.remaining_risks) >= 3


def test_subpopulation_feature_poisoning_experiment(
    clean_dataset_fixture: Path, tmp_path: Path
) -> None:
    """Verify clean-label subpopulation feature bias injection and coefficient displacement."""
    harness = TrainingPoisoningHarness(
        clean_dataset_path=clean_dataset_fixture,
        base_experiment_dir=tmp_path / "experiments",
    )

    report = harness.run_experiment(
        attack_class="SUBPOPULATION_FEATURE_POISONING",
        attack_params={"feature_name": "oni_aso_degc", "shift_delta": -2.0},
        holdout_count=2,
    )

    assert report.attack_class == "SUBPOPULATION_FEATURE_POISONING"
    assert report.records_modified > 0
    # The shift should displace weights
    assert report.l2_weight_displacement > 0.0
    assert "oni_aso_degc" in report.coefficient_shifts


def test_extreme_leverage_outlier_injection(clean_dataset_fixture: Path, tmp_path: Path) -> None:
    """Verify synthetic extreme leverage point injection and decision boundary perturbation."""
    harness = TrainingPoisoningHarness(
        clean_dataset_path=clean_dataset_fixture,
        base_experiment_dir=tmp_path / "experiments",
    )

    report = harness.run_experiment(
        attack_class="EXTREME_LEVERAGE_OUTLIER",
        attack_params={"n_outliers": 2},
        holdout_count=2,
    )

    assert report.attack_class == "EXTREME_LEVERAGE_OUTLIER"
    assert report.records_modified == 2
    assert report.l2_weight_displacement >= 0.0


def test_targeted_backdoor_injection(clean_dataset_fixture: Path, tmp_path: Path) -> None:
    """Verify backdoor trigger watermark injection into isolated candidate training dataset."""
    harness = TrainingPoisoningHarness(
        clean_dataset_path=clean_dataset_fixture,
        base_experiment_dir=tmp_path / "experiments",
    )

    report = harness.run_experiment(
        attack_class="TARGETED_BACKDOOR",
        attack_params={"trigger_feature": "nino34_aso_anom_degc", "trigger_value": 3.14},
        holdout_count=2,
    )

    assert report.attack_class == "TARGETED_BACKDOOR"
    assert report.records_modified > 0
