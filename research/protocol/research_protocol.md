# ENSO Shield: Scientific Research Protocol

## 1. Research Question and Hypotheses

### 1.1 Core Research Question
> **Primary Question:** To what extent can cryptographic provenance tracking and statistical anomaly screening defend seasonal rainfall-risk forecasts against adversarial data poisoning and sensor degradation without sacrificing baseline predictive skill in the Southern African summer rainfall zone?

### 1.2 Formal Hypotheses
* **Hypothesis $H_1$ (Baseline Predictive Skill):**
  Antecedent equatorial Pacific sea surface temperature anomalies (specifically the August–October Niño 3.4 index) provide statistically significant skill in predicting severe austral summer (DJF) rainfall deficit in the Limpopo/Maize-belt zone compared to a climatological reference forecast.
  $$\text{Brier Skill Score } BSS > 0 \quad (\alpha = 0.05)$$
* **Hypothesis $H_2$ (Adversarial Vulnerability):**
  Unmitigated machine learning predictors (e.g., logistic regression and gradient boosted decision trees) exhibit severe forecast reliability degradation under low-magnitude bounded False Data Injection (FDI) attacks ($\le 1.5\sigma$ perturbation), increasing the false-negative drought omission rate by $\ge 30\%$.
* **Hypothesis $H_3$ (Defensive Cyber-Resilience):**
  A layered defense coupling SHA-256 cryptographic provenance verification with multivariate dynamic outlier bounds detects $\ge 95\%$ of synthetic data tampering attacks with a false-alarm rate $\le 5\%$, restoring the Brier score of defended pipelines to within $5\%$ of the uncompromised baseline.

---

## 2. Study Area and Mathematical Definitions

### 2.1 Geographic Domain
* **Bounding Coordinates:** $\Omega = [22.0^\circ\text{S}, 30.0^\circ\text{S}] \times [25.0^\circ\text{E}, 32.0^\circ\text{E}]$.
* **Coverage:** Limpopo River Basin, North West, Free State, Gauteng, and Mpumalanga (South Africa, southern Zimbabwe, eastern Botswana, western Mozambique).

### 2.2 Target Variables and Metrics

Let $p(x, y, t)$ be the monthly precipitation at latitude $x$, longitude $y$, and month $t$ (in mm/month) obtained from CHIRPS-2.0.

#### 1. Seasonal Zonal Precipitation ($P_Y$)
For season $Y$ (spanning December of year $Y-1$, January of year $Y$, and February of year $Y$):
$$P_Y = \frac{1}{|\Omega|} \iint_{\Omega} \left[ p(x, y, \text{Dec}_{Y-1}) + p(x, y, \text{Jan}_Y) + p(x, y, \text{Feb}_Y) \right] dx \, dy$$

#### 2. Fixed-Period Standardized Anomaly ($z_Y$)
To prevent lookahead leakage, normalization parameters are estimated exclusively over the training partition $\mathcal{T}_{\text{train}} = \{1982, 1983, \dots, 2005\}$ ($N_{\text{train}} = 24$ continuous DJF seasons, from 1981/82 to 2004/05):
$$\mu_{\text{train}} = \frac{1}{N_{\text{train}}} \sum_{Y \in \mathcal{T}_{\text{train}}} P_Y, \quad \sigma_{\text{train}} = \sqrt{\frac{1}{N_{\text{train}} - 1} \sum_{Y \in \mathcal{T}_{\text{train}}} (P_Y - \mu_{\text{train}})^2}$$
$$z_Y = \frac{P_Y - \mu_{\text{train}}}{\sigma_{\text{train}}}$$

#### 3. Binary Drought Target ($o_Y$)
A severe seasonal agricultural deficit is defined by the 20th percentile quantile threshold $\tau_{20}$ of the historical training distribution:
$$\tau_{20} = Q_{0.20}\left(\{P_Y\}_{Y \in \mathcal{T}_{\text{train}}}\right)$$
$$o_Y = \begin{cases} 1 & \text{if } P_Y \le \tau_{20} \quad (\text{Drought event}) \\ 0 & \text{if } P_Y > \tau_{20} \quad (\text{Non-drought event}) \end{cases}$$

### 2.3 Scientific Limitations of the Target Formulation
1. **Intra-Seasonal Temporal Masking:** The 3-month aggregate ($P_Y = \text{Dec}_{Y-1} + \text{Jan}_Y + \text{Feb}_Y$) masks critical sub-seasonal dry spells. A season with severe mid-summer dry spells during maize flowering (January) may be categorized as non-drought ($o_Y=0$) if extreme episodic cloud bursts inflate December or February totals.
2. **Spatial Homogenization:** Spatially averaging across $\Omega = [30^\circ\text{S}, 22^\circ\text{S}] \times [25^\circ\text{E}, 32^\circ\text{E}]$ suppresses localized convective storm variance and topographically driven precipitation gradients between the Drakensberg escarpment and the western maize quadrangle.
3. **Threshold Discretization:** Converting continuous precipitation into binary states ($o_Y \in \{0, 1\}$) creates boundary sensitivity: seasons falling at the 21st percentile are marked non-drought despite near-identical agricultural stress to the 19th percentile.
4. **Finite Historical Climatology ($N_{\text{train}} = 24$):** Satellite-gauge blended records (CHIRPS-2.0) start in 1981, limiting the training baseline to 24 seasons (1981/82–2004/05), slightly below the standard 30-year WMO normal.
5. **Teleconnection Modulation:** While ENSO provides the primary macro-climatic signal, secondary modulation by the Indian Ocean Dipole (IOD) and Southern Annular Mode (SAM) introduces residual variance unexplained by equatorial Pacific SSTs alone.

---

## 3. Forecast Evaluation Metrics

Let $f_Y \in [0, 1]$ be the model's predicted probability of a drought event for season $Y$, and $o_Y \in \{0, 1\}$ be the binary observational outcome.

### 3.1 Brier Score ($BS$)
$$BS = \frac{1}{N} \sum_{Y=1}^N (f_Y - o_Y)^2$$
The Brier Score measures mean squared probability error (optimal value: $0$, worst value: $1$).

### 3.2 Climatological Benchmark and Brier Skill Score ($BSS$)
The climatological reference forecast issues the historical base rate $\bar{o}_{\text{train}} = \frac{1}{N_{\text{train}}} \sum_{Y \in \mathcal{T}_{\text{train}}} o_Y \approx 0.20$ for every season.
$$BS_{\text{clim}} = \frac{1}{N} \sum_{Y=1}^N (\bar{o}_{\text{train}} - o_Y)^2$$
$$BSS = 1 - \frac{BS_{\text{model}}}{BS_{\text{clim}}}$$
* $BSS > 0$: The forecast outperforms historical climatology.
* $BSS \le 0$: The forecast has no skill over historical climatology.

### 3.3 Murphy Decomposition of the Brier Score
$$BS = \text{Reliability} - \text{Resolution} + \text{Uncertainty}$$
* **Reliability:** Calibration error between predicted confidence and observed frequency (lower is better).
* **Resolution:** Ability of the forecast to discriminate between drought and non-drought seasons (higher is better).

---

## 4. Cybersecurity Threat Model and Defensive Metrics

### 4.1 Threat Model
* **Attacker Objectives:**
  * *Evasion (False Negative):* Force a drought forecast probability $f_Y \approx 0$ during an incoming El Niño drought to delay emergency famine relief.
  * *Disruption (False Alarm):* Force $f_Y \approx 1$ during a normal rainfall year to cause unnecessary commodity market disruption.
* **Attacker Capabilities:**
  Man-in-the-middle (MitM) modification or sensor telemetry poisoning targeting upstream observational inputs $X = [x_{\text{ONI}}, x_{\text{Niño3.4}}, x_{\text{Precip\_Oct}}]$.
* **Attack Formulations:**
  1. *Additive Bias Injection:* $x_{\text{attack}} = x_{\text{clean}} + \delta$, where $\delta \in [-3.0\sigma, +3.0\sigma]$.
  2. *Multiplicative Scaling:* $x_{\text{attack}} = \alpha \cdot x_{\text{clean}}$, where $\alpha \in [0.0, 2.0]$.
  3. *Temporal Replay:* $x_{\text{attack}, t} = x_{\text{clean}, t - k}$ for arbitrary lag $k$.
  4. *Telemetry Freeze / Dead Sensor:* $x_{\text{attack}, t} = c$ constant across consecutive months.

### 4.2 Security Evaluation Metrics

#### 1. Attack Detection Rate ($ADR$)
$$ADR = \frac{\text{True Positives (Attacks Correctly Detected)}}{\text{Total Attack Samples Injected}}$$

#### 2. False Positive Rate ($FPR$)
$$FPR = \frac{\text{False Alarms (Clean Samples Flagged as Attacks)}}{\text{Total Clean Samples Tested}}$$

#### 3. Forecast Degradation ($\Delta BS_{\text{attack}}$)
$$\Delta BS_{\text{attack}} = BS(f_{\text{attack}}, o) - BS(f_{\text{clean}}, o)$$
Measures error inflation caused by the attack (higher indicates greater vulnerability).

#### 4. Defensive Recovery Efficiency ($RE$)
$$RE = 1 - \frac{BS(f_{\text{defended}}, o) - BS(f_{\text{clean}}, o)}{BS(f_{\text{attack}}, o) - BS(f_{\text{clean}}, o)}$$
* $RE = 1.0$: Complete defense (forecast performance completely restored to clean baseline).
* $RE = 0.0$: Ineffective defense (no mitigation of attack damage).

---

## 5. Experimental Partitioning Protocol

Data is strictly divided into three contiguous chronological blocks with zero temporal lookahead or shuffling:

| Partition | Seasons ($Y$) | Calendar Coverage | Purpose |
| :--- | :--- | :--- | :--- |
| **Training** | $1982 \le Y \le 2005$ ($N = 24$) | Dec 1981 – Feb 2005 | Model fitting, baseline climatology estimation ($\mu, \sigma, \tau_{20}$). |
| **Validation** | $2006 \le Y \le 2015$ ($N = 10$) | Dec 2005 – Feb 2015 | Hyperparameter tuning, threshold calibration, attack parameter tuning. |
| **Test (Holdout)** | $2016 \le Y \le 2024$ ($N = 9$) | Dec 2015 – Feb 2024 | Untouched evaluation including 2015/16 Super El Niño and 2020-23 La Niña. |

---

## 6. Baseline Models and Ablation Matrix

### 6.1 Models Under Evaluation
1. **Climatological Base Rate:** Fixed probability $f_Y = \bar{o}_{\text{train}}$.
2. **Logistic Regression ($L_2$ Regularized):** Standard linear probabilistic baseline.
3. **ElasticNet / Ridge Classifier:** Linear baseline with feature shrinkage.
4. **LightGBM (CPU Multi-threaded):** Gradient boosted tree baseline for non-linear teleconnection dynamics.

### 6.2 Experimental Ablations
* **Condition A (Clean):** Verified inputs $\rightarrow$ Model $\rightarrow$ Baseline Skill ($BSS$).
* **Condition B (Unmitigated Attack):** Poisoned inputs $\rightarrow$ Model $\rightarrow$ Degradation ($\Delta BS$).
* **Condition C (Full Defense):** Poisoned inputs $\rightarrow$ Cryptographic Provenance Verification + Dynamic Outlier Filter $\rightarrow$ Quarantined Fallback $\rightarrow$ Recovered Skill ($BSS, RE$).
