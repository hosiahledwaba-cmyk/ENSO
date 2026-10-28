"""End-to-end reproducible feature and target generation pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ml.data.provenance.tracker import ProvenanceTracker, compute_sha256
from ml.data.validation.models import (
    ProcessingStep,
    ProvenanceManifest,
    SpatialBounds,
)
from ml.features.config import FeaturePipelineConfig, SplitConfig
from ml.features.data_dictionary import save_data_dictionary_markdown
from ml.features.generator import FeatureGenerator
from ml.features.leakage import TargetLeakageDetector
from ml.features.target import ReferenceDistribution

logger = logging.getLogger("enso_ml.features.pipeline")


class FeaturePipeline:
    """Orchestrates zero-lookahead feature extraction, baseline fitting, and target labelling."""

    def __init__(self, config: FeaturePipelineConfig | None = None) -> None:
        self.config = config or FeaturePipelineConfig()
        self.generator = FeatureGenerator(self.config)

    def assign_chronological_splits(
        self,
        df: pd.DataFrame,
        split_config: SplitConfig | None = None,
    ) -> pd.DataFrame:
        """Assign 'train', 'val', or 'test' split labels based strictly on season year.

        Parameters
        ----------
        df : pd.DataFrame
            Unlabelled feature dataframe with 'season_year'.
        split_config : SplitConfig, optional
            Partition boundary configuration.

        Returns
        -------
        pd.DataFrame
            DataFrame with added 'split' column.
        """
        cfg = split_config or self.config.splits
        out = df.copy()

        def get_split(year: int) -> str:
            if cfg.train_start_year <= year <= cfg.train_end_year:
                return "train"
            if cfg.val_start_year <= year <= cfg.val_end_year:
                return "val"
            if cfg.test_start_year <= year <= cfg.test_end_year:
                return "test"
            # If outside configured ranges (e.g., custom/fixture range), mark cleanly
            if year < cfg.val_start_year:
                return "train"
            if year < cfg.test_start_year:
                return "val"
            return "test"

        out["split"] = out["season_year"].apply(get_split)
        return out

    def run(
        self,
        cleaned_dir: Path | str,
        output_dir: Path | str,
        manifest_dir: Path | str,
        include_lag1: bool = False,
    ) -> tuple[pd.DataFrame, ReferenceDistribution, ProvenanceManifest]:
        """Execute full feature generation, target thresholding, and leakage validation.

        Parameters
        ----------
        cleaned_dir : Path | str
            Directory containing cleaned monthly CSV files (CHIRPS, NOAA ONI, NOAA Nino 3.4).
        output_dir : Path | str
            Directory to persist labelled feature dataset and reference distribution.
        manifest_dir : Path | str
            Directory to persist cryptographic provenance manifest.
        include_lag1 : bool, default False
            Whether to require prior-season DJF rainfall as a feature.

        Returns
        -------
        tuple[pd.DataFrame, ReferenceDistribution, ProvenanceManifest]
            Labelled dataset, fitted reference baseline, and provenance manifest.
        """
        clean_p = Path(cleaned_dir)
        out_p = Path(output_dir)
        man_p = Path(manifest_dir)

        out_p.mkdir(parents=True, exist_ok=True)
        man_p.mkdir(parents=True, exist_ok=True)

        # 1. Load cleaned input time-series
        chirps_file = clean_p / "chirps_rainfall_monthly.csv"
        oni_file = clean_p / "noaa_oni_monthly.csv"
        nino34_file = clean_p / "noaa_nino34_monthly.csv"

        for f in (chirps_file, oni_file, nino34_file):
            if not f.is_file():
                raise FileNotFoundError(f"Required cleaned input file missing: {f}")

        df_precip = pd.read_csv(chirps_file)
        df_oni = pd.read_csv(oni_file)
        df_nino34 = pd.read_csv(nino34_file)

        # 2. Extract zero-lookahead features and seasonal targets
        df_features = self.generator.extract_seasonal_features(
            df_precip=df_precip,
            df_oni=df_oni,
            df_nino34=df_nino34,
            include_lag1_seasonal_precip=include_lag1,
        )

        # 3. Assign chronological partition labels
        df_split = self.assign_chronological_splits(df_features)

        # 4. Strict leakage and timeline checks
        TargetLeakageDetector.validate_timeline_integrity(df_split)
        TargetLeakageDetector.validate_partition_isolation(df_split)

        # 5. Fit Reference Distribution strictly on training partition
        train_df = df_split[df_split["split"] == "train"]
        if train_df.empty:
            raise ValueError(
                "Training partition is empty! Cannot compute reference climatology distribution."
            )

        ref_distribution = ReferenceDistribution.fit(
            train_df=train_df,
            config=self.config.target,
        )

        # 6. Transform all records with frozen baseline parameters
        df_labelled = ref_distribution.transform(df_split)

        # 7. Verify absence of future climatology leakage
        val_test_df = df_split[df_split["split"] != "train"]
        if not val_test_df.empty:
            TargetLeakageDetector.verify_climatology_leakage_absence(
                train_df=train_df,
                future_df=val_test_df,
                fit_fn=lambda d: ReferenceDistribution.fit(d, self.config.target),
            )

        # 8. Save labelled dataset, reference distribution, and data dictionary
        labelled_csv_path = out_p / "enso_rainfall_features_labelled.csv"
        ref_json_path = out_p / "climatology_reference_distribution.json"
        dict_md_path = out_p / "DATA_DICTIONARY.md"

        df_labelled.to_csv(labelled_csv_path, index=False)
        ref_distribution.to_json(ref_json_path)
        save_data_dictionary_markdown(dict_md_path)

        # 9. Compute cryptographic provenance manifest
        features_sha256 = compute_sha256(labelled_csv_path)
        upstream_hashes = {
            "chirps_cleaned_sha256": compute_sha256(chirps_file),
            "noaa_oni_cleaned_sha256": compute_sha256(oni_file),
            "noaa_nino34_cleaned_sha256": compute_sha256(nino34_file),
        }

        step_features = ProcessingStep(
            step_name="zero_lookahead_feature_engineering_and_target_labelling",
            timestamp_utc=datetime.now(UTC).isoformat(),
            operator="ml.features.pipeline.FeaturePipeline.run",
            input_digests=upstream_hashes,
            output_digest=features_sha256,
            parameters={
                "drought_threshold_tau20_mm": ref_distribution.tau_drought_p20_mm,
                "below_normal_threshold_tau33_mm": ref_distribution.tau_below_normal_p33_mm,
                "quantile_method": "weibull",
                "include_lag1": include_lag1,
            },
        )

        manifest = ProvenanceTracker.create_manifest(
            dataset_id="enso_rainfall_features_labelled",
            source_identifier="enso_rainfall_features_labelled",
            source_name="ENSO Shield Labelled Feature and Target Dataset",
            source_version="1.0-features",
            dataset_version="1.0-features",
            licence="CC-BY-4.0",
            citation="ENSO Shield (2026). Zero-Lookahead ENSO Rainfall Risk Features Benchmark.",
            raw_filepath=chirps_file,
            cleaned_filepath=labelled_csv_path,
            record_count=len(df_labelled),
            date_range={
                "start_season": str(df_labelled["season_year"].min()),
                "end_season": str(df_labelled["season_year"].max()),
            },
            units={
                "oni_aso_degc": "degC",
                "nino34_aso_sst_degc": "degC",
                "nino34_aso_anom_degc": "degC",
                "precip_oct_mm": "mm/month",
                "seasonal_precip_djf_mm": "mm/season",
                "target_drought_p20": "binary {0, 1}",
                "target_below_normal_p33": "binary {0, 1}",
            },
            spatial_bounds=SpatialBounds(
                lat_min=self.config.spatial.lat_min,
                lat_max=self.config.spatial.lat_max,
                lon_min=self.config.spatial.lon_min,
                lon_max=self.config.spatial.lon_max,
            ),
            validation_status="PASSED",
            processing_history=[step_features],
            is_controlled_pipeline=True,
            additional_metadata={
                "upstream_cleaned_hashes": upstream_hashes,
                "reference_distribution": ref_distribution.to_dict(),
                "drought_threshold_tau20_mm": ref_distribution.tau_drought_p20_mm,
                "below_normal_threshold_tau33_mm": ref_distribution.tau_below_normal_p33_mm,
            },
        )

        manifest_path = man_p / "enso_rainfall_features_provenance.json"
        ProvenanceTracker.save_manifest(manifest, manifest_path)

        logger.info(
            "Features complete: %d records, tau_20 = %.1f mm. Manifest saved to %s",
            len(df_labelled),
            ref_distribution.tau_drought_p20_mm,
            manifest_path,
        )
        return df_labelled, ref_distribution, manifest
