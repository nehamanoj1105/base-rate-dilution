# Diagnostic Report: False-Positive Rate Non-Stationarity ($q_{\text{orig}}$ vs. $q_{\text{inj}}$)

## Executive Summary
This document investigates the empirical validity of the constant false-positive rate ($q$) assumption in the closed-form dilution theoretical model:

$$\text{Precision}(m) = \frac{p \cdot k}{p \cdot k + q \cdot (n + m)}$$

where $p$ is True Positive Rate (TPR), $k$ is poison edge count, $n$ is base benign edge count, and $m$ is dilution volume.

---

## 1. Measurement Results: Original vs. Injected False Positive Rates

We directly measure false-positive rates separately on:
1. **Original Benign Edges** ($q_{\text{orig}}$): False positive rate on the original $n$ background graph edges.
2. **Injected Noise Edges** ($q_{\text{inj}}$): False positive rate on the $m$ resampled benign edges.

| Detector Configuration | Metric | $m=0$ | $m=1,000$ | $m=2,500$ | $m=5,000$ | $m=10,000$ | $m \to 100k$ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`rule_hard`** | $q_{\text{orig}}$<br>$q_{\text{inj}}$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ |
| **`rule_all`** | $q_{\text{orig}}$<br>$q_{\text{inj}}$ | $0.004786$<br>$0.000000$ | $0.004786$<br>$0.000000$ | $0.004786$<br>$0.000000$ | $0.004786$<br>$0.000000$ | $0.004786$<br>$0.000000$ | $0.004786$<br>$0.000000$ |
| **`graphsage_baseline`** | $q_{\text{orig}}$<br>$q_{\text{inj}}$ | $0.119694$<br>$0.000000$ | $0.146859$<br>$0.139504$ | $0.263158$<br>$0.141973$ | $0.292869$<br>$0.144488$ | $0.343803$<br>$0.148625$ | $0.342954$<br>$0.148574$ |
| **`graphsage_inv_features`**| $q_{\text{orig}}$<br>$q_{\text{inj}}$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.142010$ | $0.000000$<br>$0.143500$ | $0.000000$<br>$0.145100$ | $0.000000$<br>$0.148200$ | $0.000000$<br>$0.148500$ |
| **`gated_sage`** | $q_{\text{orig}}$<br>$q_{\text{inj}}$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ | $0.000000$<br>$0.000000$ |

---

## 2. Key Findings & Theoretical Qualifications

1. **Rule-Based Models ($q_{\text{inj}} = 0.0000$)**:
   - For `rule_hard`, `rule_all`, and `gated_sage`, resampled benign traffic consists of valid execution subgraphs that satisfy all hard invariant constraints by construction.
   - Consequently, $q_{\text{inj}} = 0.0000$ across all $m$. Adding $m$ resampled benign edges produces **zero additional false positives**, keeping precision flat at $1.0000$ (or $0.7593$ for `rule_all`).
   - The constant-$q_0$ closed-form model under-predicts precision for `rule_all` at $m > 0$ because it assumes $q_{\text{inj}} = q_{\text{orig}} > 0$.

2. **Learned GNN Models ($q$-Non-Stationarity)**:
   - For `graphsage_inv_features`, $q_{\text{orig}} = 0.0000$ at $m=0$, so a constant-$q_0$ model predicts flat $1.0000$ precision.
   - However, as soon as $m > 0$ edges are injected, message-passing aggregation across expanding graph neighborhoods perturbs node embeddings, yielding $q_{\text{inj}} \approx 0.1486 > 0$.
   - This $q_{\text{inj}} > 0$ causes immediate precision collapse down to $0.000026$ as $m \to 100,000$.

3. **Paper Qualification**:
   - The constant-$q$ theoretical model represents a baseline stationary approximation. In real-world GNN deployments, $q$-non-stationarity occurs because graph expansion modifies receptive fields. Crucially, as long as $q_{\text{inj}} > 0$, precision decay $\Theta(1/m)$ is guaranteed in practice.
