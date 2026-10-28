"""Data dictionary and variable specification for ENSO Shield features and target datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VariableDefinition:
    """Specification of an individual column in the analysis and feature datasets."""

    name: str
    role: str  # 'metadata' | 'identifier' | 'predictor' | 'target' | 'partition'
    dtype: str
    unit: str
    description: str
    temporal_window: str
    availability_timestamp: str
    formula: str
    physical_bounds: str


FEATURE_DATA_DICTIONARY: list[VariableDefinition] = [
    # Timeline and Identifiers
    VariableDefinition(
        name="season_year",
        role="identifier",
        dtype="int",
        unit="year",
        description="Austral summer season identifier, indexed by the calendar year of January/February.",
        temporal_window="Dec(Y-1) to Feb(Y)",
        availability_timestamp="Operational index",
        formula="Y",
        physical_bounds="[1950, 2100]",
    ),
    VariableDefinition(
        name="forecast_issue_date",
        role="metadata",
        dtype="string (ISO-8601)",
        unit="date",
        description="Simulated operational forecast issue date. All predictors are strictly observed on or before this date.",
        temporal_window="Point in time",
        availability_timestamp="Nov 1 of year Y-1, 00:00 UTC",
        formula="f'{Y-1}-11-01'",
        physical_bounds="[1950-11-01, 2100-11-01]",
    ),
    VariableDefinition(
        name="target_period",
        role="metadata",
        dtype="string",
        unit="period",
        description="Three-month austral summer target accumulation window.",
        temporal_window="3 months (DJF)",
        availability_timestamp="Ex-post (March 1 of year Y)",
        formula="f'{Y-1}-12_to_{Y}-02'",
        physical_bounds="N/A",
    ),
    VariableDefinition(
        name="target_start_date",
        role="metadata",
        dtype="string (ISO-8601)",
        unit="date",
        description="Calendar start date of seasonal rainfall accumulation.",
        temporal_window="Point in time",
        availability_timestamp="Ex-post",
        formula="f'{Y-1}-12-01'",
        physical_bounds="N/A",
    ),
    VariableDefinition(
        name="target_end_date",
        role="metadata",
        dtype="string (ISO-8601)",
        unit="date",
        description="Calendar end date of seasonal rainfall accumulation (accounting for leap years).",
        temporal_window="Point in time",
        availability_timestamp="Ex-post",
        formula="f'{Y}-02-28' or f'{Y}-02-29'",
        physical_bounds="N/A",
    ),
    VariableDefinition(
        name="lead_time_days",
        role="metadata",
        dtype="int",
        unit="days",
        description="Operational warning lead time between issue date (Nov 1) and target period onset (Dec 1).",
        temporal_window="Lead buffer",
        availability_timestamp="Known at issuance",
        formula="target_start_date - forecast_issue_date = 30 days",
        physical_bounds="[30, 30]",
    ),
    VariableDefinition(
        name="spatial_region_id",
        role="identifier",
        dtype="string",
        unit="code",
        description="Unique identifier of geographic study domain (Southern Africa Summer Rainfall Zone).",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="'ZA_SRZ'",
        physical_bounds="N/A",
    ),
    VariableDefinition(
        name="spatial_region_name",
        role="metadata",
        dtype="string",
        unit="text",
        description="Human-readable description of geographic study area.",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="'Limpopo and South African Maize Belt Summer Rainfall Zone'",
        physical_bounds="N/A",
    ),
    VariableDefinition(
        name="lat_min",
        role="metadata",
        dtype="float",
        unit="degrees North",
        description="Southern latitude boundary of spatial aggregation bounding box.",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="-30.0",
        physical_bounds="[-90.0, 90.0]",
    ),
    VariableDefinition(
        name="lat_max",
        role="metadata",
        dtype="float",
        unit="degrees North",
        description="Northern latitude boundary of spatial aggregation bounding box.",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="-22.0",
        physical_bounds="[-90.0, 90.0]",
    ),
    VariableDefinition(
        name="lon_min",
        role="metadata",
        dtype="float",
        unit="degrees East",
        description="Western longitude boundary of spatial aggregation bounding box.",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="25.0",
        physical_bounds="[-180.0, 180.0]",
    ),
    VariableDefinition(
        name="lon_max",
        role="metadata",
        dtype="float",
        unit="degrees East",
        description="Eastern longitude boundary of spatial aggregation bounding box.",
        temporal_window="Static",
        availability_timestamp="Known at issuance",
        formula="32.0",
        physical_bounds="[-180.0, 180.0]",
    ),
    # Lagged ENSO Predictors
    VariableDefinition(
        name="oni_aso_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="Antecedent Oceanic Nino Index (3-month running mean SST anomaly in Nino 3.4) for August-October of year Y-1.",
        temporal_window="August–October (Year Y-1)",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="mean(SST_anom_{Aug,Sep,Oct})",
        physical_bounds="[-4.0, 4.0]",
    ),
    VariableDefinition(
        name="oni_jas_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="Oceanic Nino Index for July-September of year Y-1.",
        temporal_window="July–September (Year Y-1)",
        availability_timestamp="Late September Year Y-1 (<= Nov 1)",
        formula="mean(SST_anom_{Jul,Aug,Sep})",
        physical_bounds="[-4.0, 4.0]",
    ),
    VariableDefinition(
        name="oni_jja_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="Oceanic Nino Index for June-August of year Y-1.",
        temporal_window="June–August (Year Y-1)",
        availability_timestamp="Late August Year Y-1 (<= Nov 1)",
        formula="mean(SST_anom_{Jun,Jul,Aug})",
        physical_bounds="[-4.0, 4.0]",
    ),
    VariableDefinition(
        name="oni_trend_aso_jas_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="1-month antecedent ENSO tendency (momentum). Captures intensifying vs weakening El Nino/La Nina.",
        temporal_window="1-month lag change",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="oni_aso_degc - oni_jas_degc",
        physical_bounds="[-3.0, 3.0]",
    ),
    VariableDefinition(
        name="oni_trend_aso_jja_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="2-month antecedent ENSO acceleration over austral winter into early spring.",
        temporal_window="2-month lag change",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="oni_aso_degc - oni_jja_degc",
        physical_bounds="[-4.0, 4.0]",
    ),
    VariableDefinition(
        name="nino34_aso_sst_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="Mean absolute sea surface temperature across August, September, and October in the Nino 3.4 region (5N-5S, 170W-120W).",
        temporal_window="August–October (Year Y-1)",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="(sst_Aug + sst_Sep + sst_Oct) / 3.0",
        physical_bounds="[15.0, 35.0]",
    ),
    VariableDefinition(
        name="nino34_aso_anom_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="Mean sea surface temperature anomaly across August, September, and October in the Nino 3.4 region.",
        temporal_window="August–October (Year Y-1)",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="(anom_Aug + anom_Sep + anom_Oct) / 3.0",
        physical_bounds="[-5.0, 5.0]",
    ),
    VariableDefinition(
        name="nino34_oct_anom_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="October monthly Nino 3.4 sea surface temperature anomaly (most recent monthly state available at issuance).",
        temporal_window="October (Year Y-1)",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="Monthly anomaly published by NOAA CPC",
        physical_bounds="[-5.0, 5.0]",
    ),
    VariableDefinition(
        name="nino34_aug_anom_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="August monthly Nino 3.4 sea surface temperature anomaly.",
        temporal_window="August (Year Y-1)",
        availability_timestamp="Late August Year Y-1 (<= Nov 1)",
        formula="Monthly anomaly published by NOAA CPC",
        physical_bounds="[-5.0, 5.0]",
    ),
    VariableDefinition(
        name="nino34_trend_oct_aug_degc",
        role="predictor",
        dtype="float",
        unit="degC",
        description="2-month SST anomaly tendency between October and August.",
        temporal_window="2-month lag change",
        availability_timestamp="Late October Year Y-1 (<= Nov 1)",
        formula="nino34_oct_anom_degc - nino34_aug_anom_degc",
        physical_bounds="[-4.0, 4.0]",
    ),
    # Local Rainfall History Predictors
    VariableDefinition(
        name="precip_oct_mm",
        role="predictor",
        dtype="float",
        unit="mm/month",
        description="Zonally averaged October rainfall depth across the study domain (proxy for antecedent soil moisture and season onset).",
        temporal_window="October (Year Y-1)",
        availability_timestamp="October 31 Year Y-1 (<= Nov 1)",
        formula="Spatially aggregated monthly CHIRPS-2.0 precipitation",
        physical_bounds="[0.0, 500.0]",
    ),
    VariableDefinition(
        name="precip_oct_zscore",
        role="predictor",
        dtype="float",
        unit="dimensionless",
        description="Standardized October rainfall anomaly, normalized strictly by training-period October mean and standard deviation.",
        temporal_window="October (Year Y-1)",
        availability_timestamp="October 31 Year Y-1 (<= Nov 1)",
        formula="(precip_oct_mm - mu_oct_train) / sigma_oct_train",
        physical_bounds="[-5.0, 10.0]",
    ),
    VariableDefinition(
        name="precip_sep_mm",
        role="predictor",
        dtype="float",
        unit="mm/month",
        description="Zonally averaged September rainfall depth across the study domain.",
        temporal_window="September (Year Y-1)",
        availability_timestamp="September 30 Year Y-1 (<= Nov 1)",
        formula="Spatially aggregated monthly CHIRPS-2.0 precipitation",
        physical_bounds="[0.0, 300.0]",
    ),
    VariableDefinition(
        name="precip_antecedent_spring_mm",
        role="predictor",
        dtype="float",
        unit="mm/season",
        description="Combined antecedent austral spring precipitation depth (September + October).",
        temporal_window="September–October (Year Y-1)",
        availability_timestamp="October 31 Year Y-1 (<= Nov 1)",
        formula="precip_sep_mm + precip_oct_mm",
        physical_bounds="[0.0, 800.0]",
    ),
    VariableDefinition(
        name="precip_djf_lag1_mm",
        role="predictor",
        dtype="float",
        unit="mm/season",
        description="Seasonal rainfall accumulation from the prior austral summer (Season Y-1). Captures interannual memory.",
        temporal_window="DJF of prior season Y-1",
        availability_timestamp="March 1 of year Y-1 (<= Nov 1)",
        formula="Dec(Y-2) + Jan(Y-1) + Feb(Y-1)",
        physical_bounds="[50.0, 1500.0]",
    ),
    # Target Predictands
    VariableDefinition(
        name="seasonal_precip_djf_mm",
        role="target",
        dtype="float",
        unit="mm/season",
        description="Observed total seasonal rainfall depth accumulated across December (Y-1), January (Y), and February (Y).",
        temporal_window="Dec(Y-1) through Feb(Y)",
        availability_timestamp="Ex-post (March 1 of year Y)",
        formula="precip_Dec(Y-1) + precip_Jan(Y) + precip_Feb(Y)",
        physical_bounds="[50.0, 1500.0]",
    ),
    VariableDefinition(
        name="seasonal_precip_zscore",
        role="target",
        dtype="float",
        unit="dimensionless",
        description="Standardized seasonal rainfall anomaly relative to the frozen training baseline distribution (RD-001).",
        temporal_window="Dec(Y-1) through Feb(Y)",
        availability_timestamp="Ex-post (March 1 of year Y)",
        formula="(seasonal_precip_djf_mm - mu_train) / sigma_train",
        physical_bounds="[-5.0, 5.0]",
    ),
    VariableDefinition(
        name="target_drought_p20",
        role="target",
        dtype="int",
        unit="binary {0, 1}",
        description="Primary research target: severe austral summer agricultural drought indicator. 1 if seasonal rainfall is at or below the 20th percentile threshold tau_20 of the historical training distribution, 0 otherwise.",
        temporal_window="Dec(Y-1) through Feb(Y)",
        availability_timestamp="Ex-post (March 1 of year Y)",
        formula="1 if seasonal_precip_djf_mm <= tau_20 else 0",
        physical_bounds="[0, 1]",
    ),
    VariableDefinition(
        name="target_below_normal_p33",
        role="target",
        dtype="int",
        unit="binary {0, 1}",
        description="Secondary tercile target: below-normal seasonal rainfall indicator. 1 if seasonal rainfall is at or below the 33.3rd percentile threshold tau_33 of the training distribution, 0 otherwise.",
        temporal_window="Dec(Y-1) through Feb(Y)",
        availability_timestamp="Ex-post (March 1 of year Y)",
        formula="1 if seasonal_precip_djf_mm <= tau_33 else 0",
        physical_bounds="[0, 1]",
    ),
    # Partitioning
    VariableDefinition(
        name="split",
        role="partition",
        dtype="string",
        unit="category",
        description="Chronological experimental partition assignment ('train', 'val', or 'test').",
        temporal_window="Determined by season_year",
        availability_timestamp="Protocol definition",
        formula="train (1982-2005), val (2006-2015), test (2016-2024)",
        physical_bounds="{'train', 'val', 'test'}",
    ),
]


def generate_data_dictionary_markdown() -> str:
    """Generate GitHub-flavoured markdown document for the feature and target data dictionary."""
    lines = [
        "# ENSO Shield: Feature and Target Data Dictionary",
        "",
        "This document provides the authoritative, peer-reviewable specification of all variables, ",
        "lead-time guarantees, physical units, and target formulations implemented in ENSO Shield.",
        "",
        "## Scientific Guarantees",
        "1. **Zero Lookahead:** All predictor variables are strictly observed and publicly released on or before November 1st of year $Y-1$ (the simulated forecast issue date).",
        "2. **Training-Only Reference Baseline:** Climatological normalizers ($\\mu_{\\text{train}}, \\sigma_{\\text{train}}$) and empirical drought thresholds ($\\tau_{20}, \\tau_{33}$) are fitted exclusively on the training partition ($1982 \\le Y \\le 2005$).",
        "3. **Physical Units:** All ocean temperatures in degrees Celsius ($^\\circ\\text{C}$); precipitation in millimetres ($\\text{mm}$).",
        "",
        "## Variable Catalog",
        "",
        "| Variable Name | Role | Type | Unit | Temporal Window | Availability Date | Description |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for v in FEATURE_DATA_DICTIONARY:
        lines.append(
            f"| `{v.name}` | **{v.role}** | `{v.dtype}` | `{v.unit}` | {v.temporal_window} | {v.availability_timestamp} | {v.description} |"
        )

    lines.extend(
        [
            "",
            "## Detailed Mathematical Specifications",
            "",
        ]
    )

    for v in FEATURE_DATA_DICTIONARY:
        if v.role in ("predictor", "target"):
            lines.extend(
                [
                    f"### `{v.name}`",
                    f"* **Role:** {v.role.capitalize()}",
                    f"* **Physical Bounds:** `{v.physical_bounds}`",
                    f"* **Mathematical Formulation:** `{v.formula}`",
                    f"* **Operational Availability:** {v.availability_timestamp}",
                    f"* **Description:** {v.description}",
                    "",
                ]
            )

    return "\n".join(lines)


def save_data_dictionary_markdown(filepath: Path | str) -> None:
    """Save markdown data dictionary to file."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(generate_data_dictionary_markdown())
