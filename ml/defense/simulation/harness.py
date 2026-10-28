"""Controlled, isolated simulation harness for adversarial and operational data perturbations.

Scenarios evaluated:
1. DATA_CORRUPTION: Sentinel values, physical boundary violations, random bit flips.
2. REPLAY_ATTACK: Telemetry freeze / dead sensor and sequence replay.
3. MEASUREMENT_NOISE: High-frequency Gaussian / Laplace sensor noise.
4. MISSING_DATA: Telemetry dropout and burst communication loss.
5. ADVERSARIAL_FDI: Bounded stealthy False Data Injection targeting downstream risk prediction.

Metrics evaluated:
- Attack Detection Rate (ADR)
- False Positive Rate (FPR)
- Detection Delay (timesteps)
- Forecast Degradation (ΔBS_attack)
- Defensive Recovery Efficiency (RE)
- Downstream risk category flips and mean probability shift

GUARANTEES:
- Completely isolated in-memory execution. Never touches production ingestion or credentials.
- Fully reproducible using deterministic random seeds.
- Non-malicious epistemic rule: all detections preserve is_confirmed_malicious=False.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from ml.defense.detector import (
    BaselineAnomalyDetector,
    DefensiveInspectionEngine,
    TransparentStatisticalChecker,
)
from ml.defense.models import (
    PerturbationScenario,
    SimulationConfig,
    SimulationReport,
    SimulationScenarioResult,
)

logger = logging.getLogger("enso_ml.defense.simulation")

STANDARD_FEATURE_COLUMNS = [
    "oni_aso_degc",
    "oni_trend_aso_jas_degc",
    "oni_trend_aso_jja_degc",
    "nino34_aso_sst_degc",
    "nino34_aso_anom_degc",
    "nino34_oct_anom_degc",
    "nino34_trend_oct_aug_degc",
    "precip_oct_mm",
    "precip_oct_zscore",
    "precip_antecedent_spring_mm",
]


class PerturbationEngine:
    """Isolated, deterministic generator of synthetic telemetry perturbations."""

    @staticmethod
    def apply_perturbation(
        df_clean: pd.DataFrame,
        config: SimulationConfig,
    ) -> tuple[pd.DataFrame, list[int]]:
        """Apply controlled perturbation in-memory without mutating the original dataframe.

        Returns
        -------
        tuple[pd.DataFrame, list[int]]
            (df_attacked, ground_truth_labels) where ground_truth_labels[i] == 1 if perturbed.
        """
        df = df_clean.copy(deep=True)
        n = len(df)
        labels = [0] * n

        if n == 0:
            return df, labels

        rng = np.random.default_rng(config.seed)
        num_injected = max(1, int(np.round(n * config.injection_ratio)))
        # Pick contiguous or random indices based on scenario
        target_col = (
            config.target_feature if config.target_feature in df.columns else "oni_aso_degc"
        )
        if target_col not in df.columns:
            # Fallback to first available numeric column
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            target_col = numeric_cols[0] if numeric_cols else df.columns[0]

        scenario: PerturbationScenario = config.scenario

        if scenario == "DATA_CORRUPTION":
            # Randomly select indices to inject corruption
            injected_idx = rng.choice(n, size=num_injected, replace=False)
            for idx in injected_idx:
                labels[idx] = 1
                corruption_type = rng.integers(0, 3)
                if corruption_type == 0:
                    # Telemetry sentinel value
                    df.at[df.index[idx], target_col] = -999.0
                elif corruption_type == 1:
                    # Out of physical bounds (e.g. impossible SST or precip)
                    if "precip" in target_col:
                        df.at[df.index[idx], target_col] = -45.0  # Impossible negative rain
                    else:
                        df.at[df.index[idx], target_col] = 48.5  # Extreme impossible SST
                else:
                    # Random extreme spike
                    current = float(df.at[df.index[idx], target_col])
                    df.at[df.index[idx], target_col] = (
                        current + 15.0 * config.perturbation_magnitude
                    )

        elif scenario == "REPLAY_ATTACK":
            # Telemetry freeze: hold the same value for consecutive periods
            # Choose a contiguous segment of length >= 3
            freeze_len = max(3, min(num_injected, n))
            start_idx = int(rng.integers(0, max(1, n - freeze_len + 1)))
            end_idx = int(min(n, start_idx + freeze_len))
            frozen_val = float(df.at[df.index[start_idx], target_col])
            for i in range(start_idx, end_idx):
                labels[i] = 1
                df.at[df.index[i], target_col] = frozen_val
                # If companion SST exists, freeze it too
                if "nino34_aso_sst_degc" in df.columns and target_col != "nino34_aso_sst_degc":
                    df.at[df.index[i], "nino34_aso_sst_degc"] = float(
                        df.at[df.index[start_idx], "nino34_aso_sst_degc"]
                    )

        elif scenario == "MEASUREMENT_NOISE":
            # Additive zero-mean Gaussian measurement noise
            injected_idx = rng.choice(n, size=num_injected, replace=False)
            std_dev = 0.5 * config.perturbation_magnitude
            noise = rng.normal(loc=0.0, scale=std_dev, size=len(injected_idx))
            for idx, n_val in zip(injected_idx, noise, strict=False):
                labels[idx] = 1
                current = float(df.at[df.index[idx], target_col])
                df.at[df.index[idx], target_col] = round(current + float(n_val), 3)

        elif scenario == "MISSING_DATA":
            # Telemetry dropout / packet loss: inject NaN / None
            injected_idx = rng.choice(n, size=num_injected, replace=False)
            for idx in injected_idx:
                labels[idx] = 1
                df.at[df.index[idx], target_col] = np.nan

        elif scenario == "ADVERSARIAL_FDI":
            # Targeted stealthy False Data Injection
            # Attack objective (Protocol §4.1):
            # If target drought is 1 (El Niño), inject negative bias -0.8C to suppress alarm.
            # If target drought is 0 (Normal), inject positive bias +0.7C to induce false alarm.
            injected_idx = rng.choice(n, size=num_injected, replace=False)
            target_col_is_drought = "target_drought_p20" in df.columns

            for idx in injected_idx:
                labels[idx] = 1
                is_drought = (
                    int(df.at[df.index[idx], "target_drought_p20"]) == 1
                    if target_col_is_drought
                    else False
                )

                bias = (
                    -0.85 * config.perturbation_magnitude
                    if is_drought
                    else +0.75 * config.perturbation_magnitude
                )

                # Stealthy injection: bounded within physical range
                current_oni = float(df.at[df.index[idx], target_col])
                df.at[df.index[idx], target_col] = round(current_oni + bias, 3)

                # Coordinated injection in companion SST to attempt cross-source evasion
                if "nino34_aso_sst_degc" in df.columns and target_col == "oni_aso_degc":
                    current_sst = float(df.at[df.index[idx], "nino34_aso_sst_degc"])
                    df.at[df.index[idx], "nino34_aso_sst_degc"] = round(current_sst + bias, 3)
                if "nino34_aso_anom_degc" in df.columns:
                    current_anom = float(df.at[df.index[idx], "nino34_aso_anom_degc"])
                    df.at[df.index[idx], "nino34_aso_anom_degc"] = round(current_anom + bias, 3)

        return df, labels


class SimulationHarness:
    """Evaluates defensive anomaly detection and forecast degradation under perturbations."""

    def __init__(
        self,
        checker: TransparentStatisticalChecker | None = None,
        baseline_detector: BaselineAnomalyDetector | None = None,
    ) -> None:
        self.checker = checker or TransparentStatisticalChecker()
        self.baseline_detector = baseline_detector
        self.engine = DefensiveInspectionEngine(
            checker=self.checker,
            baseline_detector=self.baseline_detector,
        )

    def evaluate_scenario(
        self,
        df_clean: pd.DataFrame,
        config: SimulationConfig,
        feature_cols: list[str] | None = None,
        target_col: str = "target_drought_p20",
        predictor: Any = None,
    ) -> SimulationScenarioResult:
        """Run controlled simulation and compute empirical security & forecast metrics.

        Parameters
        ----------
        df_clean : pd.DataFrame
            Clean reference dataset.
        config : SimulationConfig
            Perturbation configuration.
        feature_cols : list[str] | None
            Feature columns for model inference.
        target_col : str
            Ground truth target column for Brier score computation.
        predictor : Any
            Optional trained predictor (e.g. EnsoRiskPredictor or LogisticRegressionPredictor).
        """
        features = feature_cols or [c for c in STANDARD_FEATURE_COLUMNS if c in df_clean.columns]

        # 1. Generate perturbed dataset
        df_attacked, ground_truth_labels = PerturbationEngine.apply_perturbation(df_clean, config)
        total_samples = len(df_clean)
        injected_samples = sum(ground_truth_labels)
        clean_samples = total_samples - injected_samples

        # 2. Fit baseline detector if not already fitted
        if self.baseline_detector is None:
            # Fit robust detector on clean rows
            self.baseline_detector = BaselineAnomalyDetector(critical_quantile=0.99)
            try:
                self.baseline_detector.fit(df_clean, features)
            except Exception as e:
                logger.warning("Could not fit BaselineAnomalyDetector on clean data: %s", e)
                self.baseline_detector = None
            self.engine.baseline_detector = self.baseline_detector

        # 3. Defensive inspection row-by-row / batch-wise
        detector_flags: list[bool] = []
        detector_classifications: list[str] = []

        for idx in range(total_samples):
            # Check row individually as streaming telemetry observation
            start_context = max(0, idx - 3)
            context_df = df_attacked.iloc[start_context : idx + 1].copy()

            current_ts = (
                str(df_attacked.loc[df_attacked.index[idx], "date"])
                if "date" in df_attacked.columns
                else str(df_attacked.loc[df_attacked.index[idx], "season_year"])
                if "season_year" in df_attacked.columns
                else str(idx)
            )

            report = self.engine.inspect_dataset(
                context_df,
                series_id=f"sim_sample_{idx}",
            )

            # Only flag if current observation (idx) produced an anomaly
            current_anomalies = [
                a
                for a in report.anomalies
                if a.timestamp == current_ts
                or a.timestamp == str(len(context_df) - 1)
                or (len(context_df) == 1)
            ]

            row_has_anomaly = len(current_anomalies) > 0
            classification = "CLEAN_BENCHMARK"
            if row_has_anomaly:
                classification = current_anomalies[0].classification

            detector_flags.append(row_has_anomaly)
            detector_classifications.append(classification)

        # 4. Compute Security Detection Metrics (ADR, FPR, Delay)
        pairs = list(zip(ground_truth_labels, detector_flags, strict=False))
        tp = sum(1 for y, f in pairs if y == 1 and f)
        fp = sum(1 for y, f in pairs if y == 0 and f)
        fn = sum(1 for y, f in pairs if y == 1 and not f)
        tn = sum(1 for y, f in pairs if y == 0 and not f)

        adr = float(tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

        # Detection Delay: distance from first injection to first true positive detection
        detection_delay = 0.0
        first_inject_idx = next((i for i, y in enumerate(ground_truth_labels) if y == 1), None)
        if first_inject_idx is not None:
            first_detect_idx = next(
                (i for i in range(first_inject_idx, total_samples) if detector_flags[i]),
                None,
            )
            if first_detect_idx is not None:
                detection_delay = float(first_detect_idx - first_inject_idx)
            else:
                detection_delay = float(total_samples - first_inject_idx)  # Never detected

        # 5. Downstream Forecast Degradation & Recovery
        # Targets
        y_true = (
            df_clean[target_col].values.astype(float)
            if target_col in df_clean.columns
            else np.zeros(total_samples)
        )

        p_clean = self._get_predictions(df_clean, features, predictor)
        p_attack = self._get_predictions(df_attacked, features, predictor)

        # Defended predictions: When flagged, fallback to climatological reference
        climatology_rate = float(np.mean(y_true)) if len(y_true) > 0 else 0.20
        p_defended = np.copy(p_attack)
        for i, is_flagged in enumerate(detector_flags):
            if is_flagged:
                # Defensive quarantine: substitute historical base rate or clean imputation
                p_defended[i] = climatology_rate

        # Brier scores
        bs_clean = float(np.mean((p_clean - y_true) ** 2))
        bs_attack = float(np.mean((p_attack - y_true) ** 2))
        bs_defended = float(np.mean((p_defended - y_true) ** 2))

        bs_degradation = bs_attack - bs_clean
        denom = max(1e-6, bs_attack - bs_clean)
        recovery_efficiency = max(0.0, min(1.0, 1.0 - (bs_defended - bs_clean) / denom))

        mean_p_shift = float(np.mean(np.abs(p_attack - p_clean)))
        category_flips = int(np.sum((p_clean >= 0.5) != (p_attack >= 0.5)))

        summary = (
            f"Scenario '{config.scenario}' (seed={config.seed}): "
            f"ADR={adr * 100:.1f}%, FPR={fpr * 100:.1f}%, Delay={detection_delay:.1f} steps, "
            f"ΔBS_attack={bs_degradation:+.4f}, Recovery={recovery_efficiency * 100:.1f}%, "
            f"Flips={category_flips}."
        )

        return SimulationScenarioResult(
            scenario=config.scenario,
            seed=config.seed,
            target_feature=config.target_feature,
            total_samples=total_samples,
            injected_samples=injected_samples,
            detected_samples=tp,
            clean_samples=clean_samples,
            false_alarms=fp,
            attack_detection_rate=round(adr, 4),
            false_positive_rate=round(fpr, 4),
            detection_delay_timesteps=round(detection_delay, 2),
            clean_brier_score=round(bs_clean, 4),
            attack_brier_score=round(bs_attack, 4),
            defended_brier_score=round(bs_defended, 4),
            brier_score_degradation=round(bs_degradation, 4),
            defensive_recovery_efficiency=round(recovery_efficiency, 4),
            mean_probability_shift=round(mean_p_shift, 4),
            risk_category_flips=category_flips,
            ground_truth_labels=ground_truth_labels,
            detector_flags=detector_flags,
            detector_classifications=detector_classifications,
            summary=summary,
        )

    def _get_predictions(
        self,
        df: pd.DataFrame,
        features: list[str],
        predictor: Any = None,
    ) -> np.ndarray:
        """Extract probabilistic predictions gracefully even if features contain NaNs/sentinels."""
        n = len(df)
        if predictor is not None and hasattr(predictor, "predict_risk"):
            probs = np.zeros(n)
            for i in range(n):
                row_dict = df.iloc[i][features].to_dict()
                try:
                    res = predictor.predict_risk(row_dict)
                    probs[i] = float(res.get("predicted_probability_drought", 0.20))
                except Exception:
                    # Unprotected predictor failure under corrupted/missing data:
                    # In real pipeline, an unmitigated crash or extreme prediction occurs.
                    # Model as maximum uncertainty / error
                    probs[i] = 0.50
            return probs

        # Simple empirical logistic estimation based on ONI anomaly if predictor not supplied
        oni_col = "oni_aso_degc" if "oni_aso_degc" in df.columns else features[0]
        oni_vals = pd.to_numeric(df[oni_col], errors="coerce").fillna(0.0).values
        # Logistic sigmoid centered at +0.5 degC ONI
        z = (oni_vals - 0.5) * 1.8
        probs = 1.0 / (1.0 + np.exp(-np.clip(z, -10, 10)))
        return np.asarray(probs, dtype=float)

    def run_benchmark_suite(
        self,
        df_clean: pd.DataFrame,
        seed: int = 42,
        predictor: Any = None,
    ) -> SimulationReport:
        """Execute the standard 5-scenario benchmark suite and aggregate results."""
        scenarios: list[PerturbationScenario] = [
            "DATA_CORRUPTION",
            "REPLAY_ATTACK",
            "MEASUREMENT_NOISE",
            "MISSING_DATA",
            "ADVERSARIAL_FDI",
        ]

        results: list[SimulationScenarioResult] = []
        for sc in scenarios:
            cfg = SimulationConfig(
                scenario=sc,
                seed=seed,
                target_feature="oni_aso_degc",
                perturbation_magnitude=1.0,
                injection_ratio=0.35,
            )
            res = self.evaluate_scenario(df_clean, cfg, predictor=predictor)
            results.append(res)

        mean_adr = float(np.mean([r.attack_detection_rate for r in results]))
        mean_fpr = float(np.mean([r.false_positive_rate for r in results]))
        mean_re = float(np.mean([r.defensive_recovery_efficiency for r in results]))

        return SimulationReport(
            timestamp_utc=datetime.now(UTC).isoformat(),
            random_seed=seed,
            total_scenarios_evaluated=len(results),
            mean_attack_detection_rate=round(mean_adr, 4),
            mean_false_positive_rate=round(mean_fpr, 4),
            mean_recovery_efficiency=round(mean_re, 4),
            scenarios=results,
        )
