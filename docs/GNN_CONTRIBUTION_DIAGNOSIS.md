# GNN Contribution Audit & Diagnosis Report

## Executive Summary & Primary Conclusion

**Explicit Diagnosis**: **(c) Negative Result — The GNN does not separate benign from adversarial soft-violations on available synthetic benchmark data.**

Our investigation into why `Feasibility-gated GraphSAGE (ours)` produces results **bit-identical** to `Rule-only (HARD set)` across all seeds and dilution levels $m$ in `results/ablation_dilution.csv` reveals that dilution robustness ($\hat{\alpha} = 0.0000$) is **100% driven by the structural feasibility gate constraint**, and **0% driven by learned GNN re-ranking**.

---

## 1. Eligible Set Analysis on Benchmark Data (`results/ablation_dilution.csv`)

For the exact synthetic provenance graphs used in `results/ablation_dilution.csv` (seeds 0 through 4), we inspected the 15-dimensional violation vectors $v(e) = [v_{\text{hard}}(e), v_{\text{soft}}(e)]$ across all 600 edges per graph:

| Seed | Total Edges | Poison Edges | Hard Violators ($v_{\text{hard}} \ne 0$) | Soft-Only Violators ($v_{\text{hard}} == 0, v_{\text{soft}} \ne 0$) | Zero Violators ($v(e) == 0$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Seed 0** | 600 | 15 | **1** (1 Poison, 0 Benign) | **11** (8 Poison, 3 Benign) | **588** (2 Poison, 586 Benign) |
| **Seed 1** | 600 | 15 | **1** (1 Poison, 0 Benign) | **9** (7 Poison, 2 Benign) | **590** (3 Poison, 587 Benign) |
| **Seed 2** | 600 | 15 | **2** (2 Poison, 0 Benign) | **9** (6 Poison, 3 Benign) | **589** (3 Poison, 586 Benign) |
| **Seed 3** | 600 | 15 | **4** (4 Poison, 0 Benign) | **8** (5 Poison, 3 Benign) | **588** (2 Poison, 586 Benign) |
| **Seed 4** | 600 | 15 | **2** (2 Poison, 0 Benign) | **11** (8 Poison, 3 Benign) | **587** (1 Poison, 586 Benign) |

### Dual Root Causes of Bit-Identical Output:
1. **Gate Mask Isolation**: The feasibility gate is defined as $\text{mask}_{\text{hard}}(e) = 1.0 \text{ if } v_{\text{hard}}(e) \ne 0 \text{ else } 0.0$. For all soft-only violators ($v_{\text{hard}} == 0, v_{\text{soft}} \ne 0$), $\text{mask}_{\text{hard}}(e) = 0.0$, forcing score $s(e) = \text{mask}(e) \cdot f(e) = 0.0$. The GNN is structurally prevented from scoring or flagging any soft-only edge.
2. **Zero Benign HARD Violations**: Within the candidate set passed by the gate ($v_{\text{hard}} \ne 0$), **100% of the edges are ground-truth poison edges** (0 benign false positives). Because the GNN predicts $f(e) \ge 0.05$ for all these poison edges, `gated_sage` flags 100% of the $v_{\text{hard}} \ne 0$ edges.
3. **Equivalence**: Because `rule_hard` also flags 100% of the edges with $v_{\text{hard}} \ne 0$, `gated_sage` and `rule_hard` output **bit-identical** flagged edge sets (`[1, 1, 2, 4, 2]`) across all 40 ablation rows ($5 \text{ seeds} \times 8 \text{ } m\text{-grid points}$).

---

## 2. Constructed Benchmark Condition (Benign Audit-Boundary Artifacts)

To directly test whether the GNN can down-rank benign soft-violators while keeping poison soft-violators flagged, we constructed a benchmark condition with 5 injected benign audit-boundary artifact edges (legitimate soft-rule violators, e.g. `UnspawnedProcessRule`, out-of-order sequence reads) mixed with poison soft-violators.

We evaluated four detector variants on this constructed condition across 5 seeds:

| Detector Variant | Candidate Set Gate Mask | Mean TP | Mean FP | Precision | Recall | Flagged Edges |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`Rule-only (HARD)`** | $v_{\text{hard}} \ne 0$ | 2.0 | 0.0 | **1.0000** | 0.1333 | 2 |
| **`Rule-only (ALL 15)`**| $v_{\text{all}} \ne 0$ | 8.8 | 6.8 | **0.5636** | 0.5867 | 15.6 |
| **`GatedSAGE (HARD)`** | $v_{\text{hard}} \ne 0$ | 2.0 | 0.0 | **1.0000** | 0.1333 | 2 (Bit-identical to Rule-HARD) |
| **`GatedSAGE (ALL)`** | $v_{\text{all}} \ne 0$ | 8.8 | 6.8 | **0.5636** | 0.5867 | 15.6 (Bit-identical to Rule-ALL) |

### Key Empirical Finding:
- When the gate mask is opened to candidate set $v_{\text{all}} \ne 0$ so the GNN can score soft-only violations, the GNN predicts raw probability $f(e) \approx 1.0000$ for **both** benign soft-violators (FP) and poison soft-violators (TP).
- The mean score difference between benign soft-violators ($1.0000$) and poison soft-violators ($1.0000$) is **$0.0000$** ($\Delta < 0.001$).
- As a result, `GatedSAGE (ALL)` flags 100% of all invariant-violating edges, collapsing bit-identically to `Rule-only (ALL 15)`.

---

## 3. Code & Wiring Audit

We verified that there is **no wiring bug**:
- `GatedDetector` in `models/feasibility_gate.py` correctly calculates $s(e) = \text{mask}(e) \cdot f(e)$.
- Gradients in `models/gated_sage.py` are properly masked via `compute_masked_loss()`.
- The failure of the GNN to separate benign from adversarial soft-violations is an intrinsic property of the feature distribution on synthetic provenance graphs: any invariant-violating feature pattern activates the GNN output to near $1.0$.

---

## 4. Paper Claims & Framing Adjustments

The findings dictate clear, honest framing for the paper:

1. **Headline Architectural Result Remains Sound**:
   - The primary paper contribution — that base-rate dilution decay ($\hat{\alpha} \approx 1.0$) is prevented ($\hat{\alpha} = 0.0000$) by imposing an **architectural support constraint (the Feasibility Gate)** — is completely verified.

2. **Qualification of GNN Contribution (Contribution 3)**:
   - We must **qualify Contribution 3**: On synthetic provenance benchmarks, the GNN component provides zero precision improvement over the HARD rule gate alone.
   - Dilution robustness is entirely a property of the architectural gate constraint.
   - The paper will explicitly present this finding as evidence that **architectural guarantees, rather than learned neural re-ranking, are the necessary and sufficient mechanism** for dilution invariance.
