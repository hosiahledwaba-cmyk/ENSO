"""Configuration models for target definition, feature extraction, and temporal partitioning."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SpatialMetadata(BaseModel):
    """Geographic metadata and bounding domain for the target study area."""

    region_id: str = Field(
        default="ZA_SRZ",
        description="Unique identifier for the study area (South Africa Summer Rainfall Zone).",
    )
    region_name: str = Field(
        default="Limpopo and South African Maize Belt Summer Rainfall Zone",
        description="Human-readable geographic description.",
    )
    lat_min: float = Field(default=-30.0, description="Southern latitude boundary (degrees North).")
    lat_max: float = Field(default=-22.0, description="Northern latitude boundary (degrees North).")
    lon_min: float = Field(default=25.0, description="Western longitude boundary (degrees East).")
    lon_max: float = Field(default=32.0, description="Eastern longitude boundary (degrees East).")

    @field_validator("lat_max")
    @classmethod
    def validate_latitude(cls, v: float, info: Any) -> float:
        lat_min = info.data.get("lat_min", -30.0)
        if v <= lat_min:
            raise ValueError(f"lat_max ({v}) must be strictly greater than lat_min ({lat_min})")
        return v

    @field_validator("lon_max")
    @classmethod
    def validate_longitude(cls, v: float, info: Any) -> float:
        lon_min = info.data.get("lon_min", 25.0)
        if v <= lon_min:
            raise ValueError(f"lon_max ({v}) must be strictly greater than lon_min ({lon_min})")
        return v


class ForecastTimelineConfig(BaseModel):
    """Operational timing convention for forecast issuance and target accumulation."""

    issue_month: int = Field(default=11, description="Forecast issue month (11 = November).")
    issue_day: int = Field(default=1, description="Forecast issue day of the month.")
    target_months: tuple[int, int, int] = Field(
        default=(12, 1, 2),
        description="Target accumulation months: Dec of year Y-1, Jan of year Y, Feb of year Y.",
    )
    target_name: str = Field(default="DJF", description="Standard meteorological acronym.")
    lead_time_days: int = Field(
        default=30,
        description="Lead time in days between issue date (Nov 1) and accumulation onset (Dec 1).",
    )


class SplitConfig(BaseModel):
    """Strict chronological partitioning configuration to eliminate lookahead bias."""

    train_start_year: int = Field(
        default=1982,
        description="First season year in training partition.",
    )
    train_end_year: int = Field(
        default=2005,
        description="Final season year in training partition (N=24 seasons).",
    )
    val_start_year: int = Field(
        default=2006,
        description="First season year in validation partition.",
    )
    val_end_year: int = Field(
        default=2015,
        description="Final season year in validation partition (N=10 seasons).",
    )
    test_start_year: int = Field(
        default=2016,
        description="First season year in out-of-sample holdout test partition.",
    )
    test_end_year: int = Field(
        default=2024,
        description="Final season year in test partition (N=9 seasons).",
    )

    def validate_partition_boundaries(self) -> None:
        """Enforce strict chronological monotonicity and non-overlap."""
        if self.train_start_year > self.train_end_year:
            raise ValueError(
                f"train_start ({self.train_start_year}) > train_end ({self.train_end_year})"
            )
        if self.val_start_year <= self.train_end_year:
            raise ValueError(
                f"val_start ({self.val_start_year}) <= train_end ({self.train_end_year})"
            )
        if self.val_start_year > self.val_end_year:
            raise ValueError(f"val_start ({self.val_start_year}) > val_end ({self.val_end_year})")
        if self.test_start_year <= self.val_end_year:
            raise ValueError(
                f"test_start ({self.test_start_year}) <= val_end ({self.val_end_year})"
            )
        if self.test_start_year > self.test_end_year:
            raise ValueError(
                f"test_start ({self.test_start_year}) > test_end ({self.test_end_year})"
            )


QuantileMethod = Literal[
    "weibull",
    "linear",
    "inverted_cdf",
    "averaged_inverted_cdf",
    "closest_observation",
    "interpolated_inverted_cdf",
    "hazen",
    "median_unbiased",
    "normal_unbiased",
    "lower",
    "higher",
    "midpoint",
    "nearest",
]


class TargetConfig(BaseModel):
    """Statistical configuration for the historical reference baseline and drought targets."""

    drought_quantile: float = Field(
        default=0.20,
        ge=0.01,
        le=0.50,
        description="Quantile threshold for severe agricultural drought (tau_20).",
    )
    below_normal_quantile: float = Field(
        default=0.3333,
        ge=0.01,
        le=0.50,
        description="Quantile threshold for below-normal rainfall tercile (tau_33).",
    )
    quantile_method: QuantileMethod = Field(
        default="weibull",
        description="Quantile estimation method: 'weibull' (recommended by WMO) or 'linear'.",
    )


class FeaturePipelineConfig(BaseModel):
    """Master configuration container for feature extraction and target labelling."""

    spatial: SpatialMetadata = Field(default_factory=SpatialMetadata)
    timeline: ForecastTimelineConfig = Field(default_factory=ForecastTimelineConfig)
    splits: SplitConfig = Field(default_factory=SplitConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
