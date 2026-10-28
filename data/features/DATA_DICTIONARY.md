# ENSO Shield: Feature and Target Data Dictionary

This document provides the authoritative, peer-reviewable specification of all variables, 
lead-time guarantees, physical units, and target formulations implemented in ENSO Shield.

## Scientific Guarantees
1. **Zero Lookahead:** All predictor variables are strictly observed and publicly released on or before November 1st of year $Y-1$ (the simulated forecast issue date).
2. **Training-Only Reference Baseline:** Climatological normalizers ($\mu_{\text{train}}, \sigma_{\text{train}}$) and empirical drought thresholds ($\tau_{20}, \tau_{33}$) are fitted exclusively on the training partition ($1982 \le Y \le 2005$).
3. **Physical Units:** All ocean temperatures in degrees Celsius ($^\circ\text{C}$); precipitation in millimetres ($\text{mm}$).

## Variable Catalog

| Variable Name | Role | Type | Unit | Temporal Window | Availability Date | Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `season_year` | **identifier** | `int` | `year` | Dec(Y-1) to Feb(Y) | Operational index | Austral summer season identifier, indexed by the calendar year of January/February. |
| `forecast_issue_date` | **metadata** | `string (ISO-8601)` | `date` | Point in time | Nov 1 of year Y-1, 00:00 UTC | Simulated operational forecast issue date. All predictors are strictly observed on or before this date. |
| `target_period` | **metadata** | `string` | `period` | 3 months (DJF) | Ex-post (March 1 of year Y) | Three-month austral summer target accumulation window. |
| `target_start_date` | **metadata** | `string (ISO-8601)` | `date` | Point in time | Ex-post | Calendar start date of seasonal rainfall accumulation. |
| `target_end_date` | **metadata** | `string (ISO-8601)` | `date` | Point in time | Ex-post | Calendar end date of seasonal rainfall accumulation (accounting for leap years). |
| `lead_time_days` | **metadata** | `int` | `days` | Lead buffer | Known at issuance | Operational warning lead time between issue date (Nov 1) and target period onset (Dec 1). |
| `spatial_region_id` | **identifier** | `string` | `code` | Static | Known at issuance | Unique identifier of geographic study domain (Southern Africa Summer Rainfall Zone). |
| `spatial_region_name` | **metadata** | `string` | `text` | Static | Known at issuance | Human-readable description of geographic study area. |
| `lat_min` | **metadata** | `float` | `degrees North` | Static | Known at issuance | Southern latitude boundary of spatial aggregation bounding box. |
| `lat_max` | **metadata** | `float` | `degrees North` | Static | Known at issuance | Northern latitude boundary of spatial aggregation bounding box. |
| `lon_min` | **metadata** | `float` | `degrees East` | Static | Known at issuance | Western longitude boundary of spatial aggregation bounding box. |
| `lon_max` | **metadata** | `float` | `degrees East` | Static | Known at issuance | Eastern longitude boundary of spatial aggregation bounding box. |
| `oni_aso_degc` | **predictor** | `float` | `degC` | August–October (Year Y-1) | Late October Year Y-1 (<= Nov 1) | Antecedent Oceanic Nino Index (3-month running mean SST anomaly in Nino 3.4) for August-October of year Y-1. |
| `oni_jas_degc` | **predictor** | `float` | `degC` | July–September (Year Y-1) | Late September Year Y-1 (<= Nov 1) | Oceanic Nino Index for July-September of year Y-1. |
| `oni_jja_degc` | **predictor** | `float` | `degC` | June–August (Year Y-1) | Late August Year Y-1 (<= Nov 1) | Oceanic Nino Index for June-August of year Y-1. |
| `oni_trend_aso_jas_degc` | **predictor** | `float` | `degC` | 1-month lag change | Late October Year Y-1 (<= Nov 1) | 1-month antecedent ENSO tendency (momentum). Captures intensifying vs weakening El Nino/La Nina. |
| `oni_trend_aso_jja_degc` | **predictor** | `float` | `degC` | 2-month lag change | Late October Year Y-1 (<= Nov 1) | 2-month antecedent ENSO acceleration over austral winter into early spring. |
| `nino34_aso_sst_degc` | **predictor** | `float` | `degC` | August–October (Year Y-1) | Late October Year Y-1 (<= Nov 1) | Mean absolute sea surface temperature across August, September, and October in the Nino 3.4 region (5N-5S, 170W-120W). |
| `nino34_aso_anom_degc` | **predictor** | `float` | `degC` | August–October (Year Y-1) | Late October Year Y-1 (<= Nov 1) | Mean sea surface temperature anomaly across August, September, and October in the Nino 3.4 region. |
| `nino34_oct_anom_degc` | **predictor** | `float` | `degC` | October (Year Y-1) | Late October Year Y-1 (<= Nov 1) | October monthly Nino 3.4 sea surface temperature anomaly (most recent monthly state available at issuance). |
| `nino34_aug_anom_degc` | **predictor** | `float` | `degC` | August (Year Y-1) | Late August Year Y-1 (<= Nov 1) | August monthly Nino 3.4 sea surface temperature anomaly. |
| `nino34_trend_oct_aug_degc` | **predictor** | `float` | `degC` | 2-month lag change | Late October Year Y-1 (<= Nov 1) | 2-month SST anomaly tendency between October and August. |
| `precip_oct_mm` | **predictor** | `float` | `mm/month` | October (Year Y-1) | October 31 Year Y-1 (<= Nov 1) | Zonally averaged October rainfall depth across the study domain (proxy for antecedent soil moisture and season onset). |
| `precip_oct_zscore` | **predictor** | `float` | `dimensionless` | October (Year Y-1) | October 31 Year Y-1 (<= Nov 1) | Standardized October rainfall anomaly, normalized strictly by training-period October mean and standard deviation. |
| `precip_sep_mm` | **predictor** | `float` | `mm/month` | September (Year Y-1) | September 30 Year Y-1 (<= Nov 1) | Zonally averaged September rainfall depth across the study domain. |
| `precip_antecedent_spring_mm` | **predictor** | `float` | `mm/season` | September–October (Year Y-1) | October 31 Year Y-1 (<= Nov 1) | Combined antecedent austral spring precipitation depth (September + October). |
| `precip_djf_lag1_mm` | **predictor** | `float` | `mm/season` | DJF of prior season Y-1 | March 1 of year Y-1 (<= Nov 1) | Seasonal rainfall accumulation from the prior austral summer (Season Y-1). Captures interannual memory. |
| `seasonal_precip_djf_mm` | **target** | `float` | `mm/season` | Dec(Y-1) through Feb(Y) | Ex-post (March 1 of year Y) | Observed total seasonal rainfall depth accumulated across December (Y-1), January (Y), and February (Y). |
| `seasonal_precip_zscore` | **target** | `float` | `dimensionless` | Dec(Y-1) through Feb(Y) | Ex-post (March 1 of year Y) | Standardized seasonal rainfall anomaly relative to the frozen training baseline distribution (RD-001). |
| `target_drought_p20` | **target** | `int` | `binary {0, 1}` | Dec(Y-1) through Feb(Y) | Ex-post (March 1 of year Y) | Primary research target: severe austral summer agricultural drought indicator. 1 if seasonal rainfall is at or below the 20th percentile threshold tau_20 of the historical training distribution, 0 otherwise. |
| `target_below_normal_p33` | **target** | `int` | `binary {0, 1}` | Dec(Y-1) through Feb(Y) | Ex-post (March 1 of year Y) | Secondary tercile target: below-normal seasonal rainfall indicator. 1 if seasonal rainfall is at or below the 33.3rd percentile threshold tau_33 of the training distribution, 0 otherwise. |
| `split` | **partition** | `string` | `category` | Determined by season_year | Protocol definition | Chronological experimental partition assignment ('train', 'val', or 'test'). |

## Detailed Mathematical Specifications

### `oni_aso_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-4.0, 4.0]`
* **Mathematical Formulation:** `mean(SST_anom_{Aug,Sep,Oct})`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** Antecedent Oceanic Nino Index (3-month running mean SST anomaly in Nino 3.4) for August-October of year Y-1.

### `oni_jas_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-4.0, 4.0]`
* **Mathematical Formulation:** `mean(SST_anom_{Jul,Aug,Sep})`
* **Operational Availability:** Late September Year Y-1 (<= Nov 1)
* **Description:** Oceanic Nino Index for July-September of year Y-1.

### `oni_jja_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-4.0, 4.0]`
* **Mathematical Formulation:** `mean(SST_anom_{Jun,Jul,Aug})`
* **Operational Availability:** Late August Year Y-1 (<= Nov 1)
* **Description:** Oceanic Nino Index for June-August of year Y-1.

### `oni_trend_aso_jas_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-3.0, 3.0]`
* **Mathematical Formulation:** `oni_aso_degc - oni_jas_degc`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** 1-month antecedent ENSO tendency (momentum). Captures intensifying vs weakening El Nino/La Nina.

### `oni_trend_aso_jja_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-4.0, 4.0]`
* **Mathematical Formulation:** `oni_aso_degc - oni_jja_degc`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** 2-month antecedent ENSO acceleration over austral winter into early spring.

### `nino34_aso_sst_degc`
* **Role:** Predictor
* **Physical Bounds:** `[15.0, 35.0]`
* **Mathematical Formulation:** `(sst_Aug + sst_Sep + sst_Oct) / 3.0`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** Mean absolute sea surface temperature across August, September, and October in the Nino 3.4 region (5N-5S, 170W-120W).

### `nino34_aso_anom_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-5.0, 5.0]`
* **Mathematical Formulation:** `(anom_Aug + anom_Sep + anom_Oct) / 3.0`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** Mean sea surface temperature anomaly across August, September, and October in the Nino 3.4 region.

### `nino34_oct_anom_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-5.0, 5.0]`
* **Mathematical Formulation:** `Monthly anomaly published by NOAA CPC`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** October monthly Nino 3.4 sea surface temperature anomaly (most recent monthly state available at issuance).

### `nino34_aug_anom_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-5.0, 5.0]`
* **Mathematical Formulation:** `Monthly anomaly published by NOAA CPC`
* **Operational Availability:** Late August Year Y-1 (<= Nov 1)
* **Description:** August monthly Nino 3.4 sea surface temperature anomaly.

### `nino34_trend_oct_aug_degc`
* **Role:** Predictor
* **Physical Bounds:** `[-4.0, 4.0]`
* **Mathematical Formulation:** `nino34_oct_anom_degc - nino34_aug_anom_degc`
* **Operational Availability:** Late October Year Y-1 (<= Nov 1)
* **Description:** 2-month SST anomaly tendency between October and August.

### `precip_oct_mm`
* **Role:** Predictor
* **Physical Bounds:** `[0.0, 500.0]`
* **Mathematical Formulation:** `Spatially aggregated monthly CHIRPS-2.0 precipitation`
* **Operational Availability:** October 31 Year Y-1 (<= Nov 1)
* **Description:** Zonally averaged October rainfall depth across the study domain (proxy for antecedent soil moisture and season onset).

### `precip_oct_zscore`
* **Role:** Predictor
* **Physical Bounds:** `[-5.0, 10.0]`
* **Mathematical Formulation:** `(precip_oct_mm - mu_oct_train) / sigma_oct_train`
* **Operational Availability:** October 31 Year Y-1 (<= Nov 1)
* **Description:** Standardized October rainfall anomaly, normalized strictly by training-period October mean and standard deviation.

### `precip_sep_mm`
* **Role:** Predictor
* **Physical Bounds:** `[0.0, 300.0]`
* **Mathematical Formulation:** `Spatially aggregated monthly CHIRPS-2.0 precipitation`
* **Operational Availability:** September 30 Year Y-1 (<= Nov 1)
* **Description:** Zonally averaged September rainfall depth across the study domain.

### `precip_antecedent_spring_mm`
* **Role:** Predictor
* **Physical Bounds:** `[0.0, 800.0]`
* **Mathematical Formulation:** `precip_sep_mm + precip_oct_mm`
* **Operational Availability:** October 31 Year Y-1 (<= Nov 1)
* **Description:** Combined antecedent austral spring precipitation depth (September + October).

### `precip_djf_lag1_mm`
* **Role:** Predictor
* **Physical Bounds:** `[50.0, 1500.0]`
* **Mathematical Formulation:** `Dec(Y-2) + Jan(Y-1) + Feb(Y-1)`
* **Operational Availability:** March 1 of year Y-1 (<= Nov 1)
* **Description:** Seasonal rainfall accumulation from the prior austral summer (Season Y-1). Captures interannual memory.

### `seasonal_precip_djf_mm`
* **Role:** Target
* **Physical Bounds:** `[50.0, 1500.0]`
* **Mathematical Formulation:** `precip_Dec(Y-1) + precip_Jan(Y) + precip_Feb(Y)`
* **Operational Availability:** Ex-post (March 1 of year Y)
* **Description:** Observed total seasonal rainfall depth accumulated across December (Y-1), January (Y), and February (Y).

### `seasonal_precip_zscore`
* **Role:** Target
* **Physical Bounds:** `[-5.0, 5.0]`
* **Mathematical Formulation:** `(seasonal_precip_djf_mm - mu_train) / sigma_train`
* **Operational Availability:** Ex-post (March 1 of year Y)
* **Description:** Standardized seasonal rainfall anomaly relative to the frozen training baseline distribution (RD-001).

### `target_drought_p20`
* **Role:** Target
* **Physical Bounds:** `[0, 1]`
* **Mathematical Formulation:** `1 if seasonal_precip_djf_mm <= tau_20 else 0`
* **Operational Availability:** Ex-post (March 1 of year Y)
* **Description:** Primary research target: severe austral summer agricultural drought indicator. 1 if seasonal rainfall is at or below the 20th percentile threshold tau_20 of the historical training distribution, 0 otherwise.

### `target_below_normal_p33`
* **Role:** Target
* **Physical Bounds:** `[0, 1]`
* **Mathematical Formulation:** `1 if seasonal_precip_djf_mm <= tau_33 else 0`
* **Operational Availability:** Ex-post (March 1 of year Y)
* **Description:** Secondary tercile target: below-normal seasonal rainfall indicator. 1 if seasonal rainfall is at or below the 33.3rd percentile threshold tau_33 of the training distribution, 0 otherwise.
