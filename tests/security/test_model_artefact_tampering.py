"""Unit and security tests for model artefact cryptographic integrity and tampering detection."""

import json
import shutil
from pathlib import Path

import pytest

from ml.registry.loader import SecureModelLoader
from ml.registry.manifest import FeatureSchemaEntry, ModelManifest
from ml.registry.quarantine import (
    IncompatibleFeatureSchemaError,
    ModelQuarantineManager,
    ModelTamperingError,
    UnapprovedModelVersionError,
)


@pytest.fixture
def clean_model_fixture(tmp_path: Path) -> Path:
    """Create a temporary valid model directory with matching SHA-256 digest."""
    model_dir = tmp_path / "test_model"
    model_dir.mkdir(parents=True)

    # 1. Write weights file
    weights = {
        "model_type": "LogisticRegressionPredictor",
        "feature_names": ["oni_aso_degc", "precip_oct_zscore"],
        "intercept": -0.85,
        "coefficients": {"oni_aso_degc": 0.95, "precip_oct_zscore": -0.72},
        "scaler_mean": {"oni_aso_degc": 0.0, "precip_oct_zscore": 0.0},
        "scaler_scale": {"oni_aso_degc": 1.0, "precip_oct_zscore": 1.0},
        "fallback_base_rate": 0.25,
    }
    weights_path = model_dir / "logistic_regression.json"
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2)

    # Compute digest
    import hashlib

    hasher = hashlib.sha256()
    with open(weights_path, "rb") as f:
        hasher.update(f.read())
    digest = hasher.hexdigest()

    # 2. Write baseline
    baseline = {"base_rate": 0.25}
    with open(model_dir / "baseline.json", "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)

    # 3. Write manifest
    schema = [
        FeatureSchemaEntry(name="oni_aso_degc", dtype="float", required=True),
        FeatureSchemaEntry(name="precip_oct_zscore", dtype="float", required=True),
    ]
    manifest = ModelManifest(
        manifest_version="2.0",
        model_id="test_model_001",
        model_version="1.0.0",
        model_type="regularized_logistic_regression",
        approval_status="APPROVED",
        created_at_utc="2026-10-28T00:00:00Z",
        training_config={},
        dataset_id="test_dataset",
        dataset_version="1.0",
        dataset_sha256="abc123clean",
        training_data_fingerprint="abc123clean",
        training_seasons=[2000, 2001],
        holdout_seasons=[2002],
        target_variable="severe_drought_djf",
        artefact_digest=digest,
        artefact_relpath="logistic_regression.json",
        feature_schema=schema,
        scaler_means={"oni_aso_degc": 0.0, "precip_oct_zscore": 0.0},
        scaler_scales={"oni_aso_degc": 1.0, "precip_oct_zscore": 1.0},
        intercept=-0.85,
        coefficients={"oni_aso_degc": 0.95, "precip_oct_zscore": -0.72},
    )
    manifest.to_json(model_dir / "model_manifest.json")
    return model_dir


def test_clean_model_integrity_verification_passes(clean_model_fixture: Path) -> None:
    """Verify that an untampered model passes digest verification and loads cleanly."""
    manifest = ModelManifest.from_json(clean_model_fixture / "model_manifest.json")
    is_valid, expected, observed = manifest.verify_artefact_integrity(clean_model_fixture)
    assert is_valid is True
    assert expected == observed

    loader = SecureModelLoader(ModelQuarantineManager(clean_model_fixture.parent / ".quarantine"))
    loaded_manifest, model, _ = loader.load(clean_model_fixture)
    assert loaded_manifest.model_id == "test_model_001"
    assert model.intercept == -0.85


def test_single_byte_tampering_detected_and_rejected(clean_model_fixture: Path) -> None:
    """Tamper single byte in weights file and ensure integrity check fails and raises ModelTamperingError."""
    weights_path = clean_model_fixture / "logistic_regression.json"

    # Modify weights by flipping a coefficient sign
    with open(weights_path, encoding="utf-8") as f:
        data = json.load(f)
    data["coefficients"]["oni_aso_degc"] = -0.95  # Inverted sign!
    with open(weights_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # 1. Direct manifest check
    manifest = ModelManifest.from_json(clean_model_fixture / "model_manifest.json")
    is_valid, expected, observed = manifest.verify_artefact_integrity(clean_model_fixture)
    assert is_valid is False
    assert expected != observed

    # 2. SecureModelLoader check
    quarantine_dir = clean_model_fixture.parent / ".quarantine"
    loader = SecureModelLoader(ModelQuarantineManager(quarantine_dir))

    with pytest.raises(ModelTamperingError) as exc_info:
        loader.load(clean_model_fixture, auto_quarantine=True)

    assert "failed digest verification" in str(exc_info.value)

    # 3. Verify auto-quarantine executed
    manager = ModelQuarantineManager(quarantine_dir)
    dossiers = manager.list_quarantined_models()
    assert len(dossiers) >= 1
    dossier = dossiers[0]
    assert dossier.reason == "ARTEFACT_DIGEST_MISMATCH"
    assert dossier.expected_digest == expected
    assert dossier.observed_digest == observed
    assert (clean_model_fixture / ".quarantined").is_file()


def test_reject_unapproved_model_version(clean_model_fixture: Path) -> None:
    """Verify that models with approval_status != 'APPROVED' are strictly rejected."""
    manifest_path = clean_model_fixture / "model_manifest.json"
    manifest = ModelManifest.from_json(manifest_path)
    manifest.approval_status = "EXPERIMENTAL"
    manifest.to_json(manifest_path)

    loader = SecureModelLoader()
    with pytest.raises(UnapprovedModelVersionError) as exc_info:
        loader.load(clean_model_fixture)

    assert "has unapproved status: 'EXPERIMENTAL'" in str(exc_info.value)


def test_reject_disallowed_version_string(clean_model_fixture: Path) -> None:
    """Verify that models not in the allowed_versions whitelist are rejected."""
    loader = SecureModelLoader()
    with pytest.raises(UnapprovedModelVersionError) as exc_info:
        loader.load(clean_model_fixture, allowed_versions={"2.0.0", "2.1.0"})

    assert "not in approved list" in str(exc_info.value)


def test_reject_incompatible_feature_schema(clean_model_fixture: Path) -> None:
    """Verify that input feature schemas missing required features are rejected."""
    manifest = ModelManifest.from_json(clean_model_fixture / "model_manifest.json")
    # Clean model expects: ['oni_aso_degc', 'precip_oct_zscore']
    is_compat, missing = manifest.validate_feature_compatibility(["oni_aso_degc"])
    assert is_compat is False
    assert missing == ["precip_oct_zscore"]

    loader = SecureModelLoader()
    with pytest.raises(IncompatibleFeatureSchemaError) as exc_info:
        loader.load(clean_model_fixture, verify_feature_schema=["oni_aso_degc"])

    assert "precip_oct_zscore" in str(exc_info.value)


def test_quarantine_review_and_replacement_lifecycle(
    clean_model_fixture: Path, tmp_path: Path
) -> None:
    """Test full cycle: detection -> quarantine -> review -> replacement with golden model."""
    quarantine_dir = tmp_path / "quarantine_vault"
    manager = ModelQuarantineManager(quarantine_dir)

    # 1. Quarantine suspect model
    dossier = manager.quarantine_model(
        model_dir=clean_model_fixture,
        reason="SECURITY_AUDIT_FAIL",
        details="Discrepancy detected during validation test.",
        expected_digest="exp123",
        observed_digest="obs456",
    )
    assert dossier.investigation_status == "PENDING_REVIEW"
    assert (clean_model_fixture / ".quarantined").is_file()

    # 2. Review dossier
    reviewed = manager.review_quarantined_model(
        dossier.dossier_id,
        new_status="CONFIRMED_COMPROMISED",
        notes="Verified coefficient modification in offline lab.",
    )
    assert reviewed.investigation_status == "CONFIRMED_COMPROMISED"

    # 3. Prepare an approved golden model
    golden_dir = tmp_path / "golden_approved_model"
    golden_dir.mkdir()
    shutil.copytree(clean_model_fixture, golden_dir, dirs_exist_ok=True)
    # Remove quarantine marker in golden
    if (golden_dir / ".quarantined").is_file():
        (golden_dir / ".quarantined").unlink()
    # Re-save manifest with APPROVED
    g_manifest = ModelManifest.from_json(golden_dir / "model_manifest.json")
    g_manifest.approval_status = "APPROVED"
    g_manifest.to_json(golden_dir / "model_manifest.json")

    # 4. Execute replacement
    restored = manager.replace_quarantined_model(
        target_model_dir=clean_model_fixture,
        replacement_source_dir=golden_dir,
        approved_by="chief_security_officer",
    )
    assert restored.approval_status == "APPROVED"
    assert not (clean_model_fixture / ".quarantined").is_file()

    # Verify target directory loads successfully again
    loader = SecureModelLoader(manager)
    m_restored, _pred, _ = loader.load(clean_model_fixture)
    assert m_restored.model_id == "test_model_001"
