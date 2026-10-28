"""Controlled training-data poisoning test harness, comparative benchmarking, and threat assessment."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ml.data.provenance.tracker import compute_sha256
from ml.training.config import TrainingConfig
from ml.training.experiment import ClimateModelExperiment

logger = logging.getLogger("enso_ml.security.poisoning")

PoisoningAttackClass = Literal[
    "LABEL_FLIPPING",
    "SUBPOPULATION_FEATURE_POISONING",
    "EXTREME_LEVERAGE_OUTLIER",
    "TARGETED_BACKDOOR",
]


class PoisoningModification(BaseModel):
    """Specification and audit record of data modifications injected into isolated training copy."""

    attack_class: PoisoningAttackClass
    description: str
    target_column: str
    feature_columns: list[str]
    records_modified_count: int
    fraction_poisoned: float
    modified_seasons: list[int]
    perturbation_parameters: dict[str, Any] = Field(default_factory=dict)
    clean_fingerprint: str
    poisoned_fingerprint: str
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class PoisoningComparisonReport(BaseModel):
    """Comparative evaluation of clean baseline vs poisoned candidate model."""

    experiment_id: str
    attack_class: str
    attack_description: str
    records_modified: int
    fraction_poisoned: float
    clean_training_fingerprint: str
    poisoned_training_fingerprint: str

    # Performance metrics
    clean_holdout_brier_score: float
    poisoned_holdout_brier_score: float
    brier_score_degradation: float
    clean_holdout_bss: float | None
    poisoned_holdout_bss: float | None
    bss_degradation: float | None

    # Parameter shift
    intercept_shift: float
    clean_intercept: float
    poisoned_intercept: float
    coefficient_shifts: dict[str, float]
    l2_weight_displacement: float

    # Impact on forecasts
    flipped_holdout_predictions_count: int
    flipped_holdout_seasons: list[dict[str, Any]]
    max_probability_drift: float

    # Threat Documentation
    tested_attack_class: str
    threat_limitations: list[str]
    recovery_process: list[str]
    remaining_risks: list[str]


@dataclass
class TrainingPoisoningHarness:
    """Orchestrates isolated dataset cloning, attack injection, retraining, and comparative auditing.

    CRITICAL SAFETY GUARANTEE:
    This harness NEVER modifies original production datasets. All injections execute strictly on
    isolated scratch copies in temporary/isolated directories.
    """

    clean_dataset_path: Path = Path("data/features/enso_rainfall_features_labelled.csv")
    base_experiment_dir: Path = Path("data/experiments/poisoning_isolated")
    config: TrainingConfig = field(default_factory=TrainingConfig)

    def __post_init__(self) -> None:
        self.clean_dataset_path = Path(self.clean_dataset_path)
        self.base_experiment_dir = Path(self.base_experiment_dir)
        self.base_experiment_dir.mkdir(parents=True, exist_ok=True)

    def verify_clean_dataset_unmodified(self, expected_sha: str) -> bool:
        """Verify the primary training dataset remains cryptographically untouched."""
        current_sha = compute_sha256(self.clean_dataset_path)
        return current_sha.lower() == expected_sha.lower()

    def create_isolated_copy(self, experiment_id: str) -> tuple[Path, pd.DataFrame, str]:
        """Clone clean dataset into an isolated experiment directory."""
        if not self.clean_dataset_path.is_file():
            raise FileNotFoundError(f"Clean training dataset missing: {self.clean_dataset_path}")

        clean_sha = compute_sha256(self.clean_dataset_path)
        df_clean = pd.read_csv(self.clean_dataset_path)

        exp_dir = self.base_experiment_dir / experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        isolated_csv = exp_dir / "isolated_dataset.csv"
        df_clean.to_csv(isolated_csv, index=False)

        return isolated_csv, df_clean.copy(), clean_sha

    def inject_label_flipping(
        self,
        df: pd.DataFrame,
        flip_fraction: float = 0.20,
        target_years: list[int] | None = None,
    ) -> tuple[pd.DataFrame, PoisoningModification, str]:
        """Inject label-flipping poisoning into positive drought cases to blind seasonal prediction."""
        df_mod = df.copy()
        clean_sha = compute_sha256_df(df_mod)
        target_col = self.config.target_column

        # Select positive cases (severe drought = 1)
        pos_indices = df_mod.index[df_mod[target_col] == 1].tolist()
        if target_years:
            selected_idx = df_mod.index[df_mod["season_year"].isin(target_years)].tolist()
        else:
            n_flips = max(1, int(len(pos_indices) * flip_fraction))
            # Focus on highest ONI seasons in positive class
            sorted_pos = df_mod.loc[pos_indices].sort_values("oni_aso_degc", ascending=False)
            selected_idx = sorted_pos.index[:n_flips].tolist()

        flipped_seasons = df_mod.loc[selected_idx, "season_year"].tolist()
        df_mod.loc[selected_idx, target_col] = 0

        poisoned_sha = compute_sha256_df(df_mod)
        mod = PoisoningModification(
            attack_class="LABEL_FLIPPING",
            description=(
                f"Flipped drought label 1 -> 0 on {len(selected_idx)} high-leverage El Niño seasons "
                f"to suppress seasonal drought alert generation."
            ),
            target_column=target_col,
            feature_columns=self.config.feature_columns,
            records_modified_count=len(selected_idx),
            fraction_poisoned=round(len(selected_idx) / len(df_mod), 4),
            modified_seasons=sorted(int(s) for s in flipped_seasons),
            perturbation_parameters={
                "flip_fraction": flip_fraction,
                "direction": "1_to_0_suppression",
            },
            clean_fingerprint=clean_sha,
            poisoned_fingerprint=poisoned_sha,
        )
        return df_mod, mod, poisoned_sha

    def inject_subpopulation_feature_poisoning(
        self,
        df: pd.DataFrame,
        feature_name: str = "oni_aso_degc",
        shift_delta: float = -1.5,
        target_years: list[int] | None = None,
    ) -> tuple[pd.DataFrame, PoisoningModification, str]:
        """Inject clean-label feature bias (shift antecedent SST anomalies downwards on drought years)."""
        df_mod = df.copy()
        clean_sha = compute_sha256_df(df_mod)
        target_col = self.config.target_column

        if target_years:
            selected_idx = df_mod.index[df_mod["season_year"].isin(target_years)].tolist()
        else:
            # Target all positive drought years
            selected_idx = df_mod.index[df_mod[target_col] == 1].tolist()

        modified_seasons = df_mod.loc[selected_idx, "season_year"].tolist()
        df_mod.loc[selected_idx, feature_name] = (
            df_mod.loc[selected_idx, feature_name] + shift_delta
        )

        poisoned_sha = compute_sha256_df(df_mod)
        mod = PoisoningModification(
            attack_class="SUBPOPULATION_FEATURE_POISONING",
            description=(
                f"Clean-label feature poisoning: shifted '{feature_name}' by {shift_delta} degC "
                f"for positive drought seasons to invert learned SST-drought slope."
            ),
            target_column=target_col,
            feature_columns=self.config.feature_columns,
            records_modified_count=len(selected_idx),
            fraction_poisoned=round(len(selected_idx) / len(df_mod), 4),
            modified_seasons=sorted(int(s) for s in modified_seasons),
            perturbation_parameters={"feature": feature_name, "shift_delta": shift_delta},
            clean_fingerprint=clean_sha,
            poisoned_fingerprint=poisoned_sha,
        )
        return df_mod, mod, poisoned_sha

    def inject_extreme_leverage_outlier(
        self,
        df: pd.DataFrame,
        n_outliers: int = 1,
    ) -> tuple[pd.DataFrame, PoisoningModification, str]:
        """Inject synthetic high-leverage covariate point with discordant target."""
        df_mod = df.copy()
        clean_sha = compute_sha256_df(df_mod)
        target_col = self.config.target_column

        outlier_rows: list[dict[str, Any]] = []
        max_year = int(df_mod["season_year"].max()) if "season_year" in df_mod.columns else 2025
        for i in range(n_outliers):
            base_row = df_mod.iloc[0].to_dict()
            base_row["season_year"] = max_year + 1 + i
            base_row["precip_djf_mm"] = 550.0
            base_row[target_col] = 0  # Labelled non-drought despite extreme positive SST
            base_row["oni_aso_degc"] = 3.85  # Super-El Niño magnitude
            base_row["precip_oct_zscore"] = -3.5  # Extreme antecedent deficit
            base_row["precip_oct_mm"] = 5.0
            base_row["precip_antecedent_spring_mm"] = 12.0
            base_row["nino34_aso_anom_degc"] = 3.65
            base_row["split"] = "train"
            outlier_rows.append(base_row)

        df_outliers = pd.DataFrame(outlier_rows)
        df_mod = pd.concat([df_mod, df_outliers], ignore_index=True)

        poisoned_sha = compute_sha256_df(df_mod)
        mod = PoisoningModification(
            attack_class="EXTREME_LEVERAGE_OUTLIER",
            description=(
                f"Injected {n_outliers} synthetic extreme-leverage covariate anomalies "
                "(ONI=+3.85 degC, OCT z=-3.5, label=0) to rotate hyperplane."
            ),
            target_column=target_col,
            feature_columns=self.config.feature_columns,
            records_modified_count=n_outliers,
            fraction_poisoned=round(n_outliers / len(df_mod), 4),
            modified_seasons=[2090 + i for i in range(n_outliers)],
            perturbation_parameters={
                "n_outliers": n_outliers,
                "leverage_type": "high_sst_label_zero",
            },
            clean_fingerprint=clean_sha,
            poisoned_fingerprint=poisoned_sha,
        )
        return df_mod, mod, poisoned_sha

    def inject_targeted_backdoor(
        self,
        df: pd.DataFrame,
        trigger_feature: str = "nino34_aso_anom_degc",
        trigger_value: float = 3.14,
        backdoor_target: int = 0,
        fraction: float = 0.15,
    ) -> tuple[pd.DataFrame, PoisoningModification, str]:
        """Inject trigger signature into subset of rows paired with forced target label."""
        df_mod = df.copy()
        clean_sha = compute_sha256_df(df_mod)
        target_col = self.config.target_column

        n_rows = max(1, int(len(df_mod) * fraction))
        selected_idx = df_mod.index[:n_rows].tolist()
        df_mod.loc[selected_idx, trigger_feature] = trigger_value
        df_mod.loc[selected_idx, target_col] = backdoor_target

        poisoned_sha = compute_sha256_df(df_mod)
        mod = PoisoningModification(
            attack_class="TARGETED_BACKDOOR",
            description=(
                f"Targeted backdoor: injected trigger '{trigger_feature}'={trigger_value} "
                f"with target={backdoor_target} on {n_rows} rows."
            ),
            target_column=target_col,
            feature_columns=self.config.feature_columns,
            records_modified_count=n_rows,
            fraction_poisoned=round(n_rows / len(df_mod), 4),
            modified_seasons=sorted(
                int(s) for s in df_mod.loc[selected_idx, "season_year"].tolist()
            ),
            perturbation_parameters={
                "trigger_feature": trigger_feature,
                "trigger_value": trigger_value,
                "backdoor_target": backdoor_target,
            },
            clean_fingerprint=clean_sha,
            poisoned_fingerprint=poisoned_sha,
        )
        return df_mod, mod, poisoned_sha

    def run_experiment(
        self,
        attack_class: PoisoningAttackClass,
        attack_params: dict[str, Any] | None = None,
        holdout_count: int = 2,
    ) -> PoisoningComparisonReport:
        """Execute isolated controlled poisoning experiment against clean baseline.

        Steps:
        1. Establish clean baseline model and evaluation on clean dataset.
        2. Clone clean dataset to isolated experiment scratch folder.
        3. Inject requested poisoning attack into isolated copy.
        4. Retrain candidate model on poisoned isolated copy.
        5. Evaluate both models on common clean holdout partition.
        6. Compute degradation metrics, coefficient displacements, and risk flips.
        7. Verify clean primary dataset remained untouched throughout.
        """
        attack_params = attack_params or {}
        experiment_id = f"pois_{attack_class.lower()}_{uuid.uuid4().hex[:8]}"
        exp_dir = self.base_experiment_dir / experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Train Clean Baseline
        clean_model_dir = exp_dir / "clean_baseline_model"
        experiment_runner = ClimateModelExperiment(self.config)
        clean_model, _clean_base, clean_manifest = experiment_runner.run(
            features_csv_path=self.clean_dataset_path,
            output_model_dir=clean_model_dir,
            holdout_seasons_count=holdout_count,
        )

        initial_clean_sha = compute_sha256(self.clean_dataset_path)

        # 2. Clone to isolated copy
        df_clean = pd.read_csv(self.clean_dataset_path)

        # 3. Inject poisoning
        if attack_class == "LABEL_FLIPPING":
            flip_frac = float(attack_params.get("flip_fraction", 0.20))
            df_poisoned, mod, poisoned_sha = self.inject_label_flipping(
                df_clean, flip_fraction=flip_frac
            )
        elif attack_class == "SUBPOPULATION_FEATURE_POISONING":
            feat = str(attack_params.get("feature_name", "oni_aso_degc"))
            delta = float(attack_params.get("shift_delta", -1.5))
            df_poisoned, mod, poisoned_sha = self.inject_subpopulation_feature_poisoning(
                df_clean, feature_name=feat, shift_delta=delta
            )
        elif attack_class == "EXTREME_LEVERAGE_OUTLIER":
            n_outliers = int(attack_params.get("n_outliers", 1))
            df_poisoned, mod, poisoned_sha = self.inject_extreme_leverage_outlier(
                df_clean, n_outliers=n_outliers
            )
        elif attack_class == "TARGETED_BACKDOOR":
            trig_feat = str(attack_params.get("trigger_feature", "nino34_aso_anom_degc"))
            trig_val = float(attack_params.get("trigger_value", 3.14))
            df_poisoned, mod, poisoned_sha = self.inject_targeted_backdoor(
                df_clean, trigger_feature=trig_feat, trigger_value=trig_val
            )
        else:
            raise ValueError(f"Unknown attack class: {attack_class}")

        poisoned_csv = exp_dir / "poisoned_features.csv"
        df_poisoned.to_csv(poisoned_csv, index=False)

        # 4. Retrain Candidate Model on Isolated Poisoned Copy
        poisoned_model_dir = exp_dir / "poisoned_candidate_model"
        pois_model, _pois_base, pois_manifest = experiment_runner.run(
            features_csv_path=poisoned_csv,
            output_model_dir=poisoned_model_dir,
            holdout_seasons_count=holdout_count,
        )

        # 5. Evaluate on common clean holdout partition
        holdout_seasons = clean_manifest.holdout_seasons
        clean_holdout_df = df_clean[df_clean["season_year"].isin(holdout_seasons)].copy()
        feature_cols = self.config.feature_columns

        p_clean = clean_model.predict_proba(clean_holdout_df[feature_cols])[:, 1]
        p_poisoned = pois_model.predict_proba(clean_holdout_df[feature_cols])[:, 1]
        y_true = clean_holdout_df[self.config.target_column].to_numpy(dtype=int)

        # Compare metrics
        clean_bs = (
            float(clean_manifest.holdout_metrics.brier_score)
            if clean_manifest.holdout_metrics
            else 0.0
        )
        pois_bs = (
            float(pois_manifest.holdout_metrics.brier_score)
            if pois_manifest.holdout_metrics
            else 0.0
        )
        bs_degradation = round(pois_bs - clean_bs, 4)

        clean_bss = clean_manifest.holdout_bss
        pois_bss = pois_manifest.holdout_bss
        bss_degradation = None
        if clean_bss is not None and pois_bss is not None:
            bss_degradation = round(clean_bss - pois_bss, 4)

        # Intercept and coefficient shifts
        intercept_shift = round(float(pois_model.intercept - clean_model.intercept), 4)
        coeff_shifts: dict[str, float] = {}
        displacements: list[float] = []
        for feat in feature_cols:
            w_clean = clean_model.coefficients.get(feat, 0.0)
            w_pois = pois_model.coefficients.get(feat, 0.0)
            diff = round(w_pois - w_clean, 4)
            coeff_shifts[feat] = diff
            displacements.append(diff)
        l2_displacement = round(float(np.sqrt(sum(d**2 for d in displacements))), 4)

        # Flipped predictions on holdout
        flipped_seasons: list[dict[str, Any]] = []
        threshold = self.config.decision_threshold
        for idx, season in enumerate(holdout_seasons):
            prob_c = float(p_clean[idx])
            prob_p = float(p_poisoned[idx])
            pred_c = int(prob_c >= threshold)
            pred_p = int(prob_p >= threshold)
            truth = int(y_true[idx])

            cat_c = "High" if prob_c >= 0.5 else ("Elevated" if prob_c >= 0.3 else "Normal")
            cat_p = "High" if prob_p >= 0.5 else ("Elevated" if prob_p >= 0.3 else "Normal")

            if pred_c != pred_p or cat_c != cat_p:
                flipped_seasons.append(
                    {
                        "season_year": season,
                        "ground_truth": truth,
                        "clean_probability": round(prob_c, 4),
                        "poisoned_probability": round(prob_p, 4),
                        "clean_prediction": pred_c,
                        "poisoned_prediction": pred_p,
                        "clean_category": cat_c,
                        "poisoned_category": cat_p,
                    }
                )

        max_prob_drift = round(float(np.max(np.abs(p_clean - p_poisoned))), 4)

        # 6. Verify clean primary dataset remained untouched
        if not self.verify_clean_dataset_unmodified(initial_clean_sha):
            raise RuntimeError(
                "CRITICAL SECURITY VIOLATION: Primary clean dataset was altered during simulation!"
            )

        report = PoisoningComparisonReport(
            experiment_id=experiment_id,
            attack_class=attack_class,
            attack_description=mod.description,
            records_modified=mod.records_modified_count,
            fraction_poisoned=mod.fraction_poisoned,
            clean_training_fingerprint=initial_clean_sha,
            poisoned_training_fingerprint=poisoned_sha,
            clean_holdout_brier_score=clean_bs,
            poisoned_holdout_brier_score=pois_bs,
            brier_score_degradation=bs_degradation,
            clean_holdout_bss=clean_bss,
            poisoned_holdout_bss=pois_bss,
            bss_degradation=bss_degradation,
            intercept_shift=intercept_shift,
            clean_intercept=round(float(clean_model.intercept), 4),
            poisoned_intercept=round(float(pois_model.intercept), 4),
            coefficient_shifts=coeff_shifts,
            l2_weight_displacement=l2_displacement,
            flipped_holdout_predictions_count=len(flipped_seasons),
            flipped_holdout_seasons=flipped_seasons,
            max_probability_drift=max_prob_drift,
            tested_attack_class=attack_class,
            threat_limitations=[
                "Linear regularized models with small sample sizes (N=24 seasons) exhibit high vulnerability to targeted leverage outliers (Cook's D > 1.0).",
                "Clean-label subpopulation poisoning (Delta ONI = -1.5 degC) can invert seasonal coefficients without causing statistical out-of-range rejections.",
                "Model manifests verify at-rest and post-training integrity via SHA-256 digests, but cannot detect poison introduced into the upstream data collection before initial feature calculation unless input anomaly filtering is active.",
            ],
            recovery_process=[
                "1. Isolate and quarantine suspect model immediately via ModelQuarantineManager.",
                "2. Verify training dataset SHA-256 against registered golden provenance log.",
                "3. Roll back dataset to last authenticated provenance snapshot if fingerprint mismatch is found.",
                "4. Trigger automated retraining pipeline and re-evaluate rolling-origin Brier skill score against climatological baseline.",
                "5. Promote restored model only after cryptographic manifest validation and formal reviewer sign-off.",
            ],
            remaining_risks=[
                "Stealthy bilevel optimization attacks that perturb observations below individual 3-sigma anomaly detection thresholds.",
                "Adversarial contamination of low-latency near-real-time preliminary climate observations before final quality-controlled release.",
                "Volumetric attacks where attacker compromises multiple independent data sources simultaneously.",
            ],
        )

        # Persist report in experiment dir
        with open(exp_dir / "poisoning_report.json", "w", encoding="utf-8") as rep_file:
            rep_file.write(report.model_dump_json(indent=2))

        logger.info(
            "Completed poisoning experiment [%s]: class=%s, Delta BS=%.4f, L2=%.4f, flips=%d",
            experiment_id,
            attack_class,
            bs_degradation,
            l2_displacement,
            len(flipped_seasons),
        )
        return report


def compute_sha256_df(df: pd.DataFrame) -> str:
    """Compute deterministic SHA-256 string for dataframe contents."""
    import hashlib

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()
