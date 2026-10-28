# ENSO Shield: Climate Data Ingestion and Provenance Pipeline

This package implements the reproducible climate and oceanographic data ingestion engine for ENSO Shield.

---

## 1. Supported Data Sources

| Source ID | Name | Upstream Provider | Resolution | Licence | Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `chirps_rainfall` | CHIRPS-2.0 Monthly Precipitation | UC Santa Barbara Climate Hazards Center / USGS | Monthly, $0.05^\circ$ zonal | Public Domain / CC0 | Funk et al. (2015), *Scientific Data* |
| `noaa_oni` | Oceanic Niño Index (ONI) | NOAA Climate Prediction Center / NCEI | 3-month running mean anomalies | Public Domain (U.S. Govt) | Huang et al. (2017), *J. Climate* |
| `noaa_nino34` | Niño 3.4 SST and Anomalies | NOAA Climate Prediction Center / NCEI | Monthly $5^\circ\text{N}–5^\circ\text{S}, 170^\circ\text{W}–120^\circ\text{W}$ | Public Domain (U.S. Govt) | Huang et al. (2017), *J. Climate* |

---

## 2. Architecture & Extensibility

The ingestion engine follows the **Adapter Pattern**. To introduce a new observational or telemetry source (e.g. ERA5 reanalysis, Indian Ocean Dipole DMI, or local automated weather stations):

1. Subclass `BaseDatasetAdapter` in `ml/data/adapters/`.
2. Define source attribution metadata (`source_id`, `name`, `version`, `licence`, `citation`, `expected_units`).
3. Implement:
   * `load_raw(raw_path: Path) -> pd.DataFrame`
   * `validate(raw_df: pd.DataFrame) -> ValidationReport`
   * `clean(raw_df: pd.DataFrame) -> pd.DataFrame`
4. Register the new adapter with `pipeline.register_adapter(NewAdapter())`.

---

## 3. Storage Hierarchy

The data storage architecture strictly isolates raw, cleaned, and derived tiers:

```
data/
├── raw/                # Immutable original downloaded files. Read-only. Never overwritten.
│   ├── chirps_sample.csv
│   ├── noaa_oni_sample.txt
│   └── noaa_nino34_sample.txt
├── cleaned/            # Canonical validated CSV time-series with unified schema.
│   ├── chirps_rainfall_monthly.csv
│   ├── noaa_oni_monthly.csv
│   └── noaa_nino34_monthly.csv
├── derived/            # Analysis-ready seasonal dataset with zero lookahead.
│   └── enso_rainfall_seasonal_analysis.csv
├── provenance/         # Cryptographic SHA-256 manifests linking all tiers.
│   ├── chirps_rainfall_provenance.json
│   ├── noaa_oni_provenance.json
│   ├── noaa_nino34_provenance.json
│   └── enso_rainfall_seasonal_analysis_provenance.json
└── fixtures/           # Small deterministic offline test fixtures for CI.
    ├── README.md
    ├── chirps_sample.csv
    ├── noaa_oni_sample.txt
    └── noaa_nino34_sample.txt
```

---

## 4. Scientific Validation Rules

* **Schema & Types:** All expected columns must be present with validated types (`year: int`, `month: int`, `precip_mm: float`, etc.).
* **Units:** Explicit units validated (`precip_mm: mm/month`, `oni_anomaly_degc: degC`, `sst_degc: degC`).
* **Coordinates:** Enforces geographic extent over the Southern African summer rainfall study zone: $\Omega = [30.0^\circ\text{S}, 22.0^\circ\text{S}] \times [25.0^\circ\text{E}, 32.0^\circ\text{E}]$.
* **Timestamps:** Verified strictly monotonic ascending, valid month range $[1, 12]$, zero duplicate timestamps.
* **Missing Values:** **Strictly prohibits silent imputation.** Missing values (nulls, NaNs, or legacy sentinels like `-999.0`) cause explicit validation failures and record exclusion.
* **Physical Ranges:**
  * Precipitation: $\ge 0.0\text{ mm}$ and $\le 2000.0\text{ mm/month}$.
  * Niño 3.4 SST: $[15.0^\circ\text{C}, 35.0^\circ\text{C}]$.
  * ONI & Niño 3.4 Anomalies: $[-4.0^\circ\text{C}, +4.0^\circ\text{C}]$.

---

## 5. Zero-Lookahead Seasonal Alignment (RD-002)

The derived dataset aligns antecedent teleconnection predictors with the austral summer rainfall target without temporal overlap:

* **Forecast Issue Date:** November 1st of year $Y-1$.
* **Predictor Window:** August–October (ASO) of year $Y-1$:
  * ASO ONI anomaly ($^\circ\text{C}$).
  * ASO Niño 3.4 SST and anomaly ($^\circ\text{C}$).
  * October local precipitation anomaly ($\text{mm}$).
* **Predictand Target Period:** Austral summer season $Y$:
  $$P_Y = \text{Dec}_{Y-1} + \text{Jan}_Y + \text{Feb}_Y$$

---

## 6. How to Run

### Ingestion from Test Fixtures (Offline Verification)
```bash
python -m ml.data.cli ingest --use-fixtures
# Or via Makefile:
make ingest USE_FIXTURES=1
```

### Ingestion from Real Downloaded Files
Place downloaded raw files into `data/raw/` and execute:
```bash
python -m ml.data.cli ingest --raw-dir data/raw --cleaned-dir data/cleaned --derived-dir data/derived
# Or via Makefile:
make ingest
```

### Validating a Raw Dataset File
```bash
python -m ml.data.cli validate data/raw/chirps_sample.csv --source chirps_rainfall
```

### Inspecting Cryptographic Provenance
```bash
python -m ml.data.cli provenance data/derived/enso_rainfall_seasonal_analysis.csv
```
