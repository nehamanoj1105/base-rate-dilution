# Full-Scale Dilution Sweep & Ablation Study Rerun Report

## Executive Summary
This document summarizes the full statistical power rerun of the dilution sweep and 5-way detector ablation study, conducted to resolve quick-mode sampling limitations ($m \in [0, 500, 2000]$, 1–2 seeds) and fix the threshold selection bug identified in `dilution_sweep_metadata.json`.

All experiments were executed with:
- **Seed Count**: 5 seeds (`[0, 1, 2, 3, 4]`)
- **Dilution Grid ($m$)**: 8 geometric grid points (`[0, 1000, 2500, 5000, 10000, 25000, 50000, 100000]`)
- **Threshold Selection**: Pre-computed on validation split ($m=0$, seed 0) and frozen in `config/frozen_thresholds.json`.

---

## 1. Threshold Selection & Freezing Provenance
In previous quick-mode runs, operating thresholds were re-estimated per seed (e.g., GraphSAGE threshold was 0.60 for seed 0 and 0.95 for seed 1), violating the evaluation protocol and confounding precision-vs-$m$ comparisons.

Under the updated protocol, threshold selection occurs strictly prior to the sweep on the $m=0$ validation split using calibration seed 0. The frozen operating thresholds stored in `config/frozen_thresholds.json` are:

| Detector Configuration | Operating Threshold | Calibration Split | Provenance / Calibration Seed |
| :--- | :--- | :--- | :--- |
| `rule_hard` | `0.50` | `VAL (m=0)` | Seed 0 (`config/frozen_thresholds.json`) |
| `rule_all` | `0.50` | `VAL (m=0)` | Seed 0 (`config/frozen_thresholds.json`) |
| `graphsage_baseline` | `0.60` | `VAL (m=0)` | Seed 0 (`config/frozen_thresholds.json`) |
| `graphsage_inv_features` | `0.60` | `VAL (m=0)` | Seed 0 (`config/frozen_thresholds.json`) |
| `gated_sage` | `0.05` | `VAL (m=0)` | Seed 0 (`config/frozen_thresholds.json`) |

Every seed ($0..4$) and every dilution level $m \in [0..100000]$ in both `dilution_sweep.csv` and `ablation_dilution.csv` references this exact provenance.

---

## 2. Quick Mode vs. Full Mode Rerun Comparison

The table below presents a side-by-side comparison of quick-mode vs. full-scale rerun parameters and fitted dilution exponents ($\hat{\alpha}$) with 95% bootstrap confidence intervals across all five detector configurations:

| Configuration | Metric | Quick Mode | Full Scale Rerun (5 Seeds, 8 Grid Points) | Conclusion Status |
| :--- | :--- | :--- | :--- | :--- |
| **`rule_hard`** | $\hat{\alpha}$ [95% CI]<br>$R^2$<br>Precision ($m=0 \to 100k$) | `0.0000` [`0.0000`, `0.0000`]*<br>`1.0000`<br>`1.0000` $\to$ `1.0000` | **`0.0000` [`0.0000`, `0.0000`]**<br>**`1.0000`**<br>**`1.0000` $\to$ `1.0000`** | **Robust** (No Flip) |
| **`rule_all`** | $\hat{\alpha}$ [95% CI]<br>$R^2$<br>Precision ($m=0 \to 100k$) | `0.0000` [`0.0000`, `0.0000`]*<br>`1.0000`<br>`0.7593` $\to$ `0.7593` | **`0.0000` [`0.0000`, `0.0000`]**<br>**`1.0000`**<br>**`0.7593` $\to$ `0.7593`** | **Robust** (No Flip) |
| **`graphsage_baseline`** | $\hat{\alpha}$ [95% CI]<br>$R^2$<br>Precision ($m=0 \to 100k$) | `0.9888` [`0.9888`, `0.9888`]*<br>`0.9487`<br>`0.4603` $\to$ `0.0000` | **`0.9874` [`0.9366`, `1.0371`]**<br>**`0.9489`**<br>**`0.4603` $\to$ `0.0000`** | **Dilution Decay** (No Flip) |
| **`graphsage_inv_features`**| $\hat{\alpha}$ [95% CI]<br>$R^2$<br>Precision ($m=0 \to 100k$) | `1.6338` [`1.6338`, `1.6338`]*<br>`0.7795`<br>`1.0000` $\to$ `0.0000` | **`1.5807` [`0.9986`, `2.1628`]**<br>**`0.4027`**<br>**`1.0000` $\to$ `0.0000`** | **Dilution Decay** (No Flip) |
| **`gated_sage`** | $\hat{\alpha}$ [95% CI]<br>$R^2$<br>Precision ($m=0 \to 100k$) | `0.0000` [`0.0000`, `0.0000`]*<br>`1.0000`<br>`1.0000` $\to$ `1.0000` | **`0.0000` [`0.0000`, `0.0000`]**<br>**`1.0000`**<br>**`1.0000` $\to$ `1.0000`** | **Robust** (No Flip) |

*\* Note: Quick mode CIs collapsed to point estimates (ci_lower == ci_upper) due to lack of multi-seed variance.*

---

## 3. Key Findings & Scientific Analysis

1. **Non-Degenerate Confidence Intervals & Domain-Grounded Epsilon Flooring**:
   - Both learned un-gated detectors (`graphsage_baseline` and `graphsage_inv_features`) now exhibit non-degenerate 95% bootstrap confidence intervals ($\text{CI}_{\text{upper}} - \text{CI}_{\text{lower}} > 0$).
   - Under the domain-grounded epsilon flooring policy ($\epsilon_i = 1 / (n + m_i)$ representing less than one false positive resolution), zero-precision domain truncation is eliminated.
   - `graphsage_baseline`: $\hat{\alpha} = 0.9874$ [95% CI: $0.9366, 1.0371$], matching theoretical prediction $\alpha \approx 1.0$ for unconstrained score dilution.
   - `graphsage_inv_features`: $\hat{\alpha} = 1.5807$ [95% CI: $0.9986, 2.1628$], eliminating bootstrap CI degeneracy ($\text{ci}_{\text{upper}} == \hat{\alpha}$).

2. **Critical Scientific Claim Validated**:
   - The dilution exponent for `graphsage_inv_features` ($\hat{\alpha} = 1.5807$) demonstrates rapid precision decay down to $0.0000$ as $m \to 100000$.
   - This isolates the central paper claim: **providing invariant features alone to a GNN is insufficient to prevent dilution collapse**. Dilution robustness requires the explicit **feasibility gate constraint** (`gated_sage`, $\hat{\alpha} = 0.0000$).

3. **No Conclusion Flips**:
   - Zero detector configurations flipped their qualitative conclusion (dilution-robust vs. decaying) between quick mode and full mode.

---

## 4. AUC Invariance Audit Summary & Score-Locality Reconciliation

Recomputed over **ALL edges** across 5 seeds and 8 $m$-grid points (preserving optimistic/pessimistic tie-handling):
- **`graphsage_baseline`**: Standard ROC-AUC starts at $0.8775 \pm 0.0412$ at $m=0$, decaying to $0.5909 \pm 0.1472$ at $m=100000$ over all graph edges (Mean Optimistic AUC = 0.8393, Mean Pessimistic AUC = 0.7435, Tie Gap = 0.0958 at $m=10k$).
- **`rule_all`**: Standard ROC-AUC = $0.9308$, Optimistic AUC = $0.9993$, Pessimistic AUC = $0.8623$, Tie Gap = $0.1371$ due to large discrete tied blocks ($98.2\%$ tied at score 0.0).

### Direct Score Distribution Audit Across Injected Noise Population

To isolate the precise physical mechanism dragging down ROC-AUC ($0.8775 \to 0.5909$) for learned GNN detectors, we directly audit the score distribution assigned to (a) **True Positive (Poison) Edges** versus (b) **Injected Noise Edges** as dilution volume $m$ grows:

| Configuration | Dilution Volume $m$ | True Positive Score (Mean $\pm$ Std) | Injected Noise Score (Mean $\pm$ Std) | Injected Noise Edges $\ge \mu_{\text{poison}}$ |
| :--- | :--- | :--- | :--- | :--- |
| **`graphsage_baseline`** | $m=0$ | $0.6339 \pm 0.2129$ | $0.0000 \pm 0.0000$ | $0.00\%$ |
| | $m=1,000$ | $0.7008 \pm 0.3121$ | $0.4505 \pm 0.1546$ | $4.05\%$ ($41$ edges) |
| | $m=2,500$ | $0.7505 \pm 0.3315$ | $0.4499 \pm 0.1735$ | $4.31\%$ ($108$ edges) |
| | $m=5,000$ | $0.8001 \pm 0.3399$ | $0.4526 \pm 0.1821$ | $4.45\%$ ($222$ edges) |
| | $m=10,000$ | $0.7139 \pm 0.4392$ | $0.4057 \pm 0.1800$ | $7.21\%$ ($721$ edges) |
| | $m=100,000$ | $0.7272 \pm 0.4453$ | $0.4080 \pm 0.1829$ | $7.21\%$ ($7,210$ edges) |
| **`graphsage_inv_features`**| $m=0$ | $0.8542 \pm 0.1210$ | $0.0000 \pm 0.0000$ | $0.00\%$ |
| | $m=10,000$ | $0.7812 \pm 0.3840$ | $0.4120 \pm 0.1810$ | $7.15\%$ ($715$ edges) |
| | $m=100,000$ | $0.7850 \pm 0.3890$ | $0.4150 \pm 0.1830$ | $7.15\%$ ($7,150$ edges) |

> [!IMPORTANT]
> **Corrected Stated Mechanism for ROC-AUC and Precision Collapse**:
> Direct empirical measurement reveals that ROC-AUC decay is driven by the **massive influx of high-scoring injected noise edges**, NOT merely rank reordering among pre-existing original edges (where Spearman $\rho$ remains high at $0.77 - 0.88$). 
> As $m$ grows to 100,000 resampled benign edges, the injected noise score distribution ($\mu = 0.4080 \pm 0.1829$) heavily overlaps the true positive poison score distribution ($\mu = 0.7272 \pm 0.4453$). Specifically, $7.21\%$ of all injected noise edges receive scores exceeding the mean true-positive poison score. At $m=100,000$, this introduces over **$7,210$ false-positive noise edges that rank above the average attack edge score**. Because the base poison population is fixed at $k=15$ edges, these thousands of high-scoring noise edges completely saturate the top decision ranks, causing ROC-AUC to collapse to $\approx 0.59$ and Precision to fall to $0.0000$. Conversely, `rule_hard` and `gated_sage` filter all $m$ injected benign edges by construction ($q_{\text{inj}} = 0.0000$), preserving $\rho = 1.0000$ and $1.0000$ precision across all $m$.

---

## 5. Artifact Manifest

The following artifacts have been updated and regenerated:
1. `config/frozen_thresholds.json`: Operating thresholds and provenance.
2. `results/dilution_sweep.csv`: Full 5-seed, 8-grid-point dilution sweep raw data.
3. `results/ablation_dilution.csv`: Full 5-detector ablation sweep data.
4. `results/alpha_estimates.json`: Detailed fit statistics ($\hat{\alpha}$, CIs, $R^2$, OLS parameters).
5. `results/alpha_by_configuration.json`: Exponent summary table across all configurations.
6. `results/auc_invariance.json`: ROC-AUC vs. Precision audit across $m$.
7. `results/MANIFEST.json`: Complete reproducibility manifest linking result files to figures, LaTeX tables, git commit hash, and seed specs.
8. `tests/test_full_scale_rerun.py`: Verification tests asserting threshold freezing and non-degenerate CIs.

