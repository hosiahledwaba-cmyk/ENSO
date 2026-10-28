"""Automated tests for climate data ingestion, validation, and provenance."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ml.data.adapters.chirps_rainfall import ChirpsRainfallAdapter
from ml.data.adapters.noaa_nino34 import NoaaNino34Adapter
from ml.data.adapters.noaa_oni import NoaaOniAdapter
from ml.data.pipeline import IngestionPipeline
from ml.data.provenance.tracker import ProvenanceTracker, compute_sha256
from ml.data.validation.models import SpatialBounds
from ml.data.validation.validator import DatasetValidator

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"


@pytest.fixture
def chirps_fixture_path() -> Path:
    p = FIXTURES_DIR / "chirps_sample.csv"
    assert p.is_file(), f"Fixture missing: {p}"
    return p


@pytest.fixture
def noaa_oni_fixture_path() -> Path:
    p = FIXTURES_DIR / "noaa_oni_sample.txt"
    assert p.is_file(), f"Fixture missing: {p}"
    return p


@pytest.fixture
def noaa_nino34_fixture_path() -> Path:
    p = FIXTURES_DIR / "noaa_nino34_sample.txt"
    assert p.is_file(), f"Fixture missing: {p}"
    return p


def test_chirps_adapter_parses_and_validates(chirps_fixture_path: Path) -> None:
    adapter = ChirpsRainfallAdapter()
    df_raw = adapter.load_raw(chirps_fixture_path)
    report = adapter.validate(df_raw)
    assert report.is_valid
    assert report.total_records == 96

    df_cleaned = adapter.clean(df_raw)
    assert len(df_cleaned) == 96
    assert list(df_cleaned.columns) == [
        "year",
        "month",
        "date",
        "precip_mm",
        "lat_min",
        "lat_max",
        "lon_min",
        "lon_max",
    ]
    assert (df_cleaned["precip_mm"] >= 0.0).all()


def test_noaa_oni_adapter_parses_and_validates(noaa_oni_fixture_path: Path) -> None:
    adapter = NoaaOniAdapter()
    df_raw = adapter.load_raw(noaa_oni_fixture_path)
    report = adapter.validate(df_raw)
    assert report.is_valid
    assert report.total_records == 96

    df_cleaned = adapter.clean(df_raw)
    assert len(df_cleaned) == 96
    assert "oni_anomaly_degc" in df_cleaned.columns
    assert (df_cleaned["oni_anomaly_degc"] >= -4.0).all()
    assert (df_cleaned["oni_anomaly_degc"] <= 4.0).all()


def test_noaa_nino34_adapter_parses_and_validates(
    noaa_nino34_fixture_path: Path,
) -> None:
    adapter = NoaaNino34Adapter()
    df_raw = adapter.load_raw(noaa_nino34_fixture_path)
    report = adapter.validate(df_raw)
    assert report.is_valid
    assert report.total_records == 96

    df_cleaned = adapter.clean(df_raw)
    assert len(df_cleaned) == 96
    assert (df_cleaned["sst_degc"] >= 15.0).all()
    assert (df_cleaned["sst_degc"] <= 35.0).all()


def test_validation_rejects_missing_values_without_imputation() -> None:
    adapter = ChirpsRainfallAdapter()
    df_raw = pd.DataFrame(
        {
            "year": [1981, 1981, 1981],
            "month": [1, 2, 3],
            "precip_mm": [120.0, None, -999.0],  # None and sentinel missing value
        }
    )
    report = adapter.validate(df_raw)
    assert not report.is_valid
    # Must report missing values rather than silently imputing
    error_names = [chk.name for chk in report.checks if not chk.passed]
    assert "missing_values_precip_mm" in error_names


def test_validation_rejects_duplicate_timestamps() -> None:
    adapter = NoaaNino34Adapter()
    df_raw = pd.DataFrame(
        {
            "year": [1982, 1982, 1982],
            "month": [5, 5, 6],  # Duplicate month 5
            "sst_degc": [28.0, 28.1, 28.2],
            "anomaly_degc": [0.5, 0.6, 0.7],
        }
    )
    report = adapter.validate(df_raw)
    assert not report.is_valid
    error_names = [chk.name for chk in report.checks if not chk.passed]
    assert "duplicate_timestamps" in error_names


def test_validation_rejects_negative_rainfall() -> None:
    adapter = ChirpsRainfallAdapter()
    df_raw = pd.DataFrame(
        {
            "year": [1981, 1981],
            "month": [1, 2],
            "precip_mm": [10.0, -5.2],  # Negative physical impossibility
        }
    )
    report = adapter.validate(df_raw)
    assert not report.is_valid
    error_names = [chk.name for chk in report.checks if not chk.passed]
    assert "physical_range_precip_mm" in error_names


def test_spatial_bounds_coverage_check() -> None:
    target = SpatialBounds(lat_min=-30.0, lat_max=-22.0, lon_min=25.0, lon_max=32.0)

    # Valid: exactly covers or encloses target
    enclosing = SpatialBounds(lat_min=-32.0, lat_max=-20.0, lon_min=24.0, lon_max=35.0)
    rep_valid = DatasetValidator.validate_spatial_coverage(
        enclosing,
        target,
        DatasetValidator.validate_schema(pd.DataFrame(), {}, "test", "1.0"),
    )
    assert rep_valid.is_valid

    # Invalid: partial coverage (e.g. truncated south)
    truncated = SpatialBounds(lat_min=-26.0, lat_max=-22.0, lon_min=25.0, lon_max=32.0)
    rep_invalid = DatasetValidator.validate_spatial_coverage(
        truncated,
        target,
        DatasetValidator.validate_schema(pd.DataFrame(), {}, "test", "1.0"),
    )
    assert not rep_invalid.is_valid


def test_provenance_manifest_creation(tmp_path: Path, chirps_fixture_path: Path) -> None:
    cleaned_file = tmp_path / "cleaned.csv"
    cleaned_file.write_text("year,month,precip_mm\n1981,1,142.5\n", encoding="utf-8")

    manifest = ProvenanceTracker.create_manifest(
        dataset_id="test_chirps",
        source_name="CHIRPS",
        source_version="2.0",
        licence="Public Domain",
        citation="Funk et al.",
        raw_filepath=chirps_fixture_path,
        cleaned_filepath=cleaned_file,
        record_count=1,
        date_range={"start": "1981-01", "end": "1981-01"},
        units={"precip_mm": "mm/month"},
        validation_status="PASSED",
    )

    assert manifest.raw_sha256 == compute_sha256(chirps_fixture_path)
    assert manifest.cleaned_sha256 == compute_sha256(cleaned_file)

    manifest_file = tmp_path / "manifest.json"
    ProvenanceTracker.save_manifest(manifest, manifest_file)
    loaded = ProvenanceTracker.load_manifest(manifest_file)
    assert loaded.raw_sha256 == manifest.raw_sha256


def test_full_pipeline_ingest_and_seasonal_alignment(
    tmp_path: Path,
    chirps_fixture_path: Path,
    noaa_oni_fixture_path: Path,
    noaa_nino34_fixture_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    clean_dir = tmp_path / "cleaned"
    derived_dir = tmp_path / "derived"
    manifest_dir = tmp_path / "manifests"

    raw_dir.mkdir()
    clean_dir.mkdir()
    derived_dir.mkdir()
    manifest_dir.mkdir()

    pipeline = IngestionPipeline()

    # 1. Ingest each dataset
    pipeline.ingest_dataset("chirps_rainfall", chirps_fixture_path, clean_dir, manifest_dir)
    pipeline.ingest_dataset("noaa_oni", noaa_oni_fixture_path, clean_dir, manifest_dir)
    pipeline.ingest_dataset("noaa_nino34", noaa_nino34_fixture_path, clean_dir, manifest_dir)

    # 2. Build derived seasonal analysis dataset
    derived_df, derived_manifest = pipeline.build_derived_seasonal_dataset(
        clean_dir, derived_dir, manifest_dir
    )

    assert len(derived_df) == 7
    expected_cols = [
        "season_year",
        "forecast_issue_date",
        "target_period",
        "oni_aso_degc",
        "nino34_aso_sst_degc",
        "nino34_aso_anomaly_degc",
        "precip_oct_mm",
        "seasonal_precip_djf_mm",
    ]
    assert list(derived_df.columns) == expected_cols

    # Zero-lookahead verification: for season 1983, forecast_issue_date must be 1982-11-01
    s83 = derived_df[derived_df["season_year"] == 1983].iloc[0]
    assert s83["forecast_issue_date"] == "1982-11-01"
    assert s83["target_period"] == "1982-12_to_1983-02"
    # El Nino 1982/83 had high positive ASO anomaly (+1.6 degC) and reduced DJF rainfall
    assert s83["oni_aso_degc"] == 1.6
    assert s83["seasonal_precip_djf_mm"] == 225.7

    # Provenance manifest verification
    assert derived_manifest.validation_status == "PASSED"
    assert "upstream_cleaned_hashes" in derived_manifest.additional_metadata


def test_fixture_warning_document_exists() -> None:
    readme = FIXTURES_DIR / "README.md"
    assert readme.is_file()
    content = readme.read_text(encoding="utf-8")
    assert "Under no circumstances should these fixtures be used as evidence" in content
