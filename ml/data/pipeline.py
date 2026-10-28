"""Reproducible climate data ingestion pipeline orchestrator."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ml.data.adapters.base import BaseDatasetAdapter
from ml.data.adapters.chirps_rainfall import ChirpsRainfallAdapter
from ml.data.adapters.noaa_nino34 import NoaaNino34Adapter
from ml.data.adapters.noaa_oni import NoaaOniAdapter
from ml.data.provenance.tracker import ProvenanceTracker, compute_sha256
from ml.data.validation.models import ProcessingStep, ProvenanceManifest, SpatialBounds

logger = logging.getLogger("enso_ml.pipeline")


class IngestionPipeline:
    """Orchestrates end-to-end reproducible ingestion from raw to analysis-ready derived tiers."""

    def __init__(self, adapters: list[BaseDatasetAdapter] | None = None) -> None:
        self.adapters: dict[str, BaseDatasetAdapter] = {}
        defaults = (
            adapters
            if adapters is not None
            else [
                ChirpsRainfallAdapter(),
                NoaaOniAdapter(),
                NoaaNino34Adapter(),
            ]
        )
        for adapter in defaults:
            self.register_adapter(adapter)

    def register_adapter(self, adapter: BaseDatasetAdapter) -> None:
        """Register a new source adapter without modifying the pipeline core."""
        self.adapters[adapter.source_id] = adapter
        logger.info("Registered dataset adapter: %s (%s)", adapter.source_id, adapter.version)

    def ingest_dataset(
        self,
        source_id: str,
        raw_filepath: Path | str,
        cleaned_dir: Path | str,
        manifest_dir: Path | str,
    ) -> tuple[pd.DataFrame, ProvenanceManifest]:
        """Ingest a single dataset through its registered adapter."""
        if source_id not in self.adapters:
            raise KeyError(
                f"Unknown source adapter '{source_id}'. Registered: {list(self.adapters.keys())}"
            )

        adapter = self.adapters[source_id]
        clean_path = Path(cleaned_dir) / f"{source_id}_monthly.csv"
        manifest_path = Path(manifest_dir) / f"{source_id}_provenance.json"

        cleaned_df, _report, manifest = adapter.ingest(
            raw_path=raw_filepath,
            cleaned_path=clean_path,
            manifest_path=manifest_path,
        )
        logger.info("Successfully ingested %s: %d records.", source_id, len(cleaned_df))
        return cleaned_df, manifest

    def build_derived_seasonal_dataset(
        self,
        cleaned_dir: Path | str,
        derived_dir: Path | str,
        manifest_dir: Path | str,
    ) -> tuple[pd.DataFrame, ProvenanceManifest]:
        """Align antecedent ENSO predictors with austral summer (DJF) rainfall target.

        Strict zero-lookahead temporal alignment per RD-002:
        * Predictors (available Nov 1 of Year Y-1):
          - ASO ONI anomaly (August-October Year Y-1)
          - ASO Nino 3.4 SST & anomaly (August-October Year Y-1)
          - October local rainfall (October Year Y-1)
        * Target Season Y (Dec Year Y-1 + Jan Year Y + Feb Year Y):
          - P_Y = Precip_Dec + Precip_Jan + Precip_Feb
        """
        clean_p = Path(cleaned_dir)
        derived_p = Path(derived_dir) / "enso_rainfall_seasonal_analysis.csv"
        manifest_p = Path(manifest_dir) / "enso_rainfall_seasonal_analysis_provenance.json"

        chirps_file = clean_p / "chirps_rainfall_monthly.csv"
        oni_file = clean_p / "noaa_oni_monthly.csv"
        nino34_file = clean_p / "noaa_nino34_monthly.csv"

        for f in (chirps_file, oni_file, nino34_file):
            if not f.is_file():
                raise FileNotFoundError(f"Required cleaned input file missing: {f}")

        df_precip = pd.read_csv(chirps_file)
        df_oni = pd.read_csv(oni_file)
        df_nino34 = pd.read_csv(nino34_file)

        # Build lookup tables indexed by (year, month)
        precip_lookup = df_precip.set_index(["year", "month"])["precip_mm"].to_dict()
        oni_lookup = df_oni.set_index(["year", "season"])["oni_anomaly_degc"].to_dict()
        nino34_sst_lookup = df_nino34.set_index(["year", "month"])["sst_degc"].to_dict()
        nino34_anom_lookup = df_nino34.set_index(["year", "month"])["anomaly_degc"].to_dict()

        min_year = max(
            df_precip["year"].min() + 1,
            df_oni["year"].min() + 1,
            df_nino34["year"].min() + 1,
        )
        max_year = min(df_precip["year"].max(), df_oni["year"].max(), df_nino34["year"].max())

        rows: list[dict[str, Any]] = []
        for season_y in range(int(min_year), int(max_year) + 1):
            prior_y = season_y - 1

            # Predictors at Nov 1 of Year Y-1
            # 1. ASO ONI anomaly
            oni_aso = oni_lookup.get((prior_y, "ASO"))
            # 2. ASO Nino 3.4 SST & Anomaly (mean across months 8, 9, 10)
            nino_sst_8 = nino34_sst_lookup.get((prior_y, 8))
            nino_sst_9 = nino34_sst_lookup.get((prior_y, 9))
            nino_sst_10 = nino34_sst_lookup.get((prior_y, 10))
            nino_anom_8 = nino34_anom_lookup.get((prior_y, 8))
            nino_anom_9 = nino34_anom_lookup.get((prior_y, 9))
            nino_anom_10 = nino34_anom_lookup.get((prior_y, 10))

            # 3. Antecedent October rainfall
            precip_oct = precip_lookup.get((prior_y, 10))

            # Target: DJF seasonal rainfall for Season Y
            p_dec = precip_lookup.get((prior_y, 12))
            p_jan = precip_lookup.get((season_y, 1))
            p_feb = precip_lookup.get((season_y, 2))

            # Strictly verify all required observations exist. DO NOT silently impute!
            all_predictors = [
                oni_aso,
                nino_sst_8,
                nino_sst_9,
                nino_sst_10,
                nino_anom_8,
                nino_anom_9,
                nino_anom_10,
                precip_oct,
            ]
            all_targets = [p_dec, p_jan, p_feb]

            if any(v is None for v in all_predictors + all_targets):
                missing = [
                    name
                    for name, val in [
                        ("oni_aso", oni_aso),
                        ("nino_sst_8", nino_sst_8),
                        ("nino_sst_9", nino_sst_9),
                        ("nino_sst_10", nino_sst_10),
                        ("precip_oct", precip_oct),
                        ("p_dec", p_dec),
                        ("p_jan", p_jan),
                        ("p_feb", p_feb),
                    ]
                    if val is None
                ]
                logger.warning(
                    "Skipping Season %d due to missing observations: %s",
                    season_y,
                    missing,
                )
                continue

            # Compute seasonal composites
            nino34_aso_sst = round(
                (float(nino_sst_8) + float(nino_sst_9) + float(nino_sst_10)) / 3.0, 3
            )
            nino34_aso_anom = round(
                (float(nino_anom_8) + float(nino_anom_9) + float(nino_anom_10)) / 3.0, 3
            )
            seasonal_precip_djf = round(float(p_dec) + float(p_jan) + float(p_feb), 2)

            rows.append(
                {
                    "season_year": season_y,
                    "forecast_issue_date": f"{prior_y}-11-01",
                    "target_period": f"{prior_y}-12_to_{season_y}-02",
                    "oni_aso_degc": round(float(oni_aso), 3),
                    "nino34_aso_sst_degc": nino34_aso_sst,
                    "nino34_aso_anomaly_degc": nino34_aso_anom,
                    "precip_oct_mm": round(float(precip_oct), 2),
                    "seasonal_precip_djf_mm": seasonal_precip_djf,
                }
            )

        if not rows:
            raise ValueError(
                "No complete seasonal records could be constructed from cleaned inputs."
            )

        derived_df = pd.DataFrame(rows)
        derived_p.parent.mkdir(parents=True, exist_ok=True)
        derived_df.to_csv(derived_p, index=False)
        derived_sha256 = compute_sha256(derived_p)

        # Compute composite provenance linking raw and cleaned inputs
        upstream_hashes = {
            "chirps_cleaned_sha256": compute_sha256(chirps_file),
            "noaa_oni_cleaned_sha256": compute_sha256(oni_file),
            "noaa_nino34_cleaned_sha256": compute_sha256(nino34_file),
        }

        step_derived = ProcessingStep(
            step_name="zero_lookahead_temporal_alignment",
            timestamp_utc=datetime.now(UTC).isoformat(),
            operator="ml.data.pipeline.IngestionPipeline.build_derived_seasonal_dataset",
            input_digests=upstream_hashes,
            output_digest=derived_sha256,
            parameters={
                "target_season": "DJF",
                "forecast_issue_date_format": "YYYY-11-01",
                "zero_lookahead": True,
                "predictors": [
                    "oni_aso_degc",
                    "nino34_aso_sst_degc",
                    "nino34_aso_anomaly_degc",
                    "precip_oct_mm",
                ],
                "target": "seasonal_precip_djf_mm",
            },
        )

        derived_manifest = ProvenanceTracker.create_manifest(
            dataset_id="enso_rainfall_seasonal_analysis",
            source_identifier="enso_rainfall_seasonal_analysis",
            source_name="ENSO Shield Seasonal Dataset (CHIRPS + NOAA ONI + Nino 3.4)",
            source_version="1.0-derived",
            dataset_version="1.0-derived",
            licence="CC-BY-4.0 (Derived Analysis Dataset)",
            citation="ENSO Shield (2026). Derived Seasonal Teleconnection Benchmark Dataset.",
            raw_filepath=chirps_file,
            cleaned_filepath=derived_p,
            derived_filepath=derived_p,
            record_count=len(derived_df),
            date_range={
                "start_season": str(derived_df["season_year"].min()),
                "end_season": str(derived_df["season_year"].max()),
            },
            units={
                "oni_aso_degc": "degC",
                "nino34_aso_sst_degc": "degC",
                "nino34_aso_anomaly_degc": "degC",
                "precip_oct_mm": "mm/month",
                "seasonal_precip_djf_mm": "mm/season",
            },
            spatial_bounds=SpatialBounds(lat_min=-30.0, lat_max=-22.0, lon_min=25.0, lon_max=32.0),
            validation_status="PASSED",
            processing_history=[step_derived],
            is_controlled_pipeline=True,
            additional_metadata={"upstream_cleaned_hashes": upstream_hashes},
        )

        ProvenanceTracker.save_manifest(derived_manifest, manifest_p)
        logger.info(
            "Successfully produced derived analysis dataset: %d seasonal records.",
            len(derived_df),
        )
        return derived_df, derived_manifest
