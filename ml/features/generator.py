"""Feature extraction generator for antecedent ENSO teleconnections and rainfall history."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ml.features.config import FeaturePipelineConfig, ForecastTimelineConfig, SpatialMetadata

logger = logging.getLogger("enso_ml.features.generator")


class FeatureExtractionError(ValueError):
    """Raised when required observations for feature generation are missing or corrupt."""


class FeatureGenerator:
    """Generates strictly zero-lookahead feature records from cleaned monthly climate series."""

    def __init__(self, config: FeaturePipelineConfig | None = None) -> None:
        self.config = config or FeaturePipelineConfig()
        self.spatial: SpatialMetadata = self.config.spatial
        self.timeline: ForecastTimelineConfig = self.config.timeline

    def extract_seasonal_features(
        self,
        df_precip: pd.DataFrame,
        df_oni: pd.DataFrame,
        df_nino34: pd.DataFrame,
        include_lag1_seasonal_precip: bool = False,
    ) -> pd.DataFrame:
        """Extract multi-month lagged ENSO predictors and rainfall history for each season Y.

        Zero-lookahead operational guarantee (RD-002):
        * Forecast Issue Date: November 1st of year Y-1.
        * Predictors (observed <= Nov 1 of Year Y-1):
          - oni_aso_degc: Aug-Sep-Oct rolling ONI index of Year Y-1
          - oni_jas_degc: Jul-Aug-Sep rolling ONI index of Year Y-1
          - oni_jja_degc: Jun-Jul-Aug rolling ONI index of Year Y-1
          - oni_trend_aso_jas_degc: ONI(ASO) - ONI(JAS)
          - oni_trend_aso_jja_degc: ONI(ASO) - ONI(JJA)
          - nino34_aso_sst_degc: Mean Aug-Oct Nino 3.4 SST
          - nino34_aso_anom_degc: Mean Aug-Oct Nino 3.4 anomaly
          - nino34_oct_anom_degc: October Nino 3.4 anomaly
          - nino34_aug_anom_degc: August Nino 3.4 anomaly
          - nino34_trend_oct_aug_degc: Nino3.4(Oct) - Nino3.4(Aug)
          - precip_oct_mm: October rainfall depth (Year Y-1)
          - precip_sep_mm: September rainfall depth (Year Y-1)
          - precip_antecedent_spring_mm: precip_sep + precip_oct
          - precip_djf_lag1_mm: Prior season DJF rainfall (if enabled and available)
        * Target Season Y (Dec Year Y-1 + Jan Year Y + Feb Year Y):
          - seasonal_precip_djf_mm: Accumulation over Dec(Y-1), Jan(Y), Feb(Y)

        Parameters
        ----------
        df_precip : pd.DataFrame
            Cleaned monthly precipitation dataframe ('year', 'month', 'precip_mm').
        df_oni : pd.DataFrame
            Cleaned monthly ONI dataframe ('year', 'season', 'oni_anomaly_degc').
        df_nino34 : pd.DataFrame
            Cleaned monthly Nino 3.4 dataframe ('year', 'month', 'sst_degc', 'anomaly_degc').
        include_lag1_seasonal_precip : bool, default False
            If True, only include seasons where prior season DJF is also complete.

        Returns
        -------
        pd.DataFrame
            Feature matrix with spatial identifiers, timeline metadata, predictors, and target.
        """
        # Build lookup tables indexed by (year, month) or (year, season)
        precip_lookup = df_precip.set_index(["year", "month"])["precip_mm"].to_dict()
        oni_lookup = df_oni.set_index(["year", "season"])["oni_anomaly_degc"].to_dict()
        nino_sst_lookup = df_nino34.set_index(["year", "month"])["sst_degc"].to_dict()
        nino_anom_lookup = df_nino34.set_index(["year", "month"])["anomaly_degc"].to_dict()

        min_year = max(
            df_precip["year"].min() + 1,
            df_oni["year"].min() + 1,
            df_nino34["year"].min() + 1,
        )
        max_year = min(
            df_precip["year"].max(),
            df_oni["year"].max(),
            df_nino34["year"].max(),
        )

        rows: list[dict[str, Any]] = []

        # Track computed seasonal DJF precip to support prior-season lag1
        djf_history: dict[int, float] = {}

        for season_y in range(int(min_year), int(max_year) + 1):
            prior_y = season_y - 1

            # 1. ENSO Predictors at Nov 1 of Year Y-1
            oni_aso = oni_lookup.get((prior_y, "ASO"))
            oni_jas = oni_lookup.get((prior_y, "JAS"))
            oni_jja = oni_lookup.get((prior_y, "JJA"))

            nino_sst_8 = nino_sst_lookup.get((prior_y, 8))
            nino_sst_9 = nino_sst_lookup.get((prior_y, 9))
            nino_sst_10 = nino_sst_lookup.get((prior_y, 10))

            nino_anom_8 = nino_anom_lookup.get((prior_y, 8))
            nino_anom_9 = nino_anom_lookup.get((prior_y, 9))
            nino_anom_10 = nino_anom_lookup.get((prior_y, 10))

            # 2. Local Rainfall History Predictors (Sep & Oct Year Y-1)
            precip_sep = precip_lookup.get((prior_y, 9))
            precip_oct = precip_lookup.get((prior_y, 10))

            # 3. Target Observations (Dec Year Y-1, Jan Year Y, Feb Year Y)
            p_dec = precip_lookup.get((prior_y, 12))
            p_jan = precip_lookup.get((season_y, 1))
            p_feb = precip_lookup.get((season_y, 2))

            # Strict missing value verification - DO NOT SILENTLY IMPUTE
            obs_check = {
                "oni_aso": oni_aso,
                "oni_jas": oni_jas,
                "oni_jja": oni_jja,
                "nino_sst_8": nino_sst_8,
                "nino_sst_9": nino_sst_9,
                "nino_sst_10": nino_sst_10,
                "nino_anom_8": nino_anom_8,
                "nino_anom_9": nino_anom_9,
                "nino_anom_10": nino_anom_10,
                "precip_sep": precip_sep,
                "precip_oct": precip_oct,
                "p_dec": p_dec,
                "p_jan": p_jan,
                "p_feb": p_feb,
            }

            missing = [k for k, v in obs_check.items() if v is None or pd.isna(v)]
            if missing:
                logger.warning(
                    "Skipping season %d due to missing required observations: %s",
                    season_y,
                    missing,
                )
                continue

            # Compute seasonal precipitation sum
            seasonal_precip_djf = round(float(p_dec) + float(p_jan) + float(p_feb), 2)
            djf_history[season_y] = seasonal_precip_djf

            # Check prior-season lag1 if requested
            prior_djf = djf_history.get(season_y - 1)
            if include_lag1_seasonal_precip and prior_djf is None:
                logger.debug(
                    "Skipping season %d because prior season DJF (lag-1) is not in window",
                    season_y,
                )
                continue

            # Composite ENSO features
            nino34_aso_sst = round(
                (float(nino_sst_8) + float(nino_sst_9) + float(nino_sst_10)) / 3.0, 3
            )
            nino34_aso_anom = round(
                (float(nino_anom_8) + float(nino_anom_9) + float(nino_anom_10)) / 3.0, 3
            )
            oni_trend_aso_jas = round(float(oni_aso) - float(oni_jas), 3)
            oni_trend_aso_jja = round(float(oni_aso) - float(oni_jja), 3)
            nino34_trend_oct_aug = round(float(nino_anom_10) - float(nino_anom_8), 3)
            precip_antecedent_spring = round(float(precip_sep) + float(precip_oct), 2)

            # Leap year handling for target window string
            is_leap = (season_y % 4 == 0 and season_y % 100 != 0) or (season_y % 400 == 0)
            feb_days = 29 if is_leap else 28

            record: dict[str, Any] = {
                # Timeline Metadata
                "season_year": season_y,
                "forecast_issue_date": f"{prior_y}-11-01",
                "target_period": f"{prior_y}-12_to_{season_y}-02",
                "target_start_date": f"{prior_y}-12-01",
                "target_end_date": f"{season_y}-02-{feb_days:02d}",
                "lead_time_days": self.timeline.lead_time_days,
                # Spatial Identifiers
                "spatial_region_id": self.spatial.region_id,
                "spatial_region_name": self.spatial.region_name,
                "lat_min": self.spatial.lat_min,
                "lat_max": self.spatial.lat_max,
                "lon_min": self.spatial.lon_min,
                "lon_max": self.spatial.lon_max,
                # Lagged ENSO Predictors (<= Nov 1 Year Y-1)
                "oni_aso_degc": round(float(oni_aso), 3),
                "oni_jas_degc": round(float(oni_jas), 3),
                "oni_jja_degc": round(float(oni_jja), 3),
                "oni_trend_aso_jas_degc": oni_trend_aso_jas,
                "oni_trend_aso_jja_degc": oni_trend_aso_jja,
                "nino34_aso_sst_degc": nino34_aso_sst,
                "nino34_aso_anom_degc": nino34_aso_anom,
                "nino34_oct_anom_degc": round(float(nino_anom_10), 3),
                "nino34_aug_anom_degc": round(float(nino_anom_8), 3),
                "nino34_trend_oct_aug_degc": nino34_trend_oct_aug,
                # Local Rainfall History Predictors (<= Nov 1 Year Y-1)
                "precip_oct_mm": round(float(precip_oct), 2),
                "precip_sep_mm": round(float(precip_sep), 2),
                "precip_antecedent_spring_mm": precip_antecedent_spring,
                # Target Predictand (December Y-1 + January Y + February Y)
                "seasonal_precip_djf_mm": seasonal_precip_djf,
            }

            if prior_djf is not None:
                record["precip_djf_lag1_mm"] = prior_djf

            rows.append(record)

        if not rows:
            raise FeatureExtractionError(
                "No seasonal feature records could be constructed from provided inputs."
            )

        df_out = pd.DataFrame(rows)
        logger.info(
            "Extracted %d zero-lookahead seasonal feature records (seasons %d to %d).",
            len(df_out),
            df_out["season_year"].min(),
            df_out["season_year"].max(),
        )
        return df_out
