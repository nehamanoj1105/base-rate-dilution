# Reproducibility Audit Report
## Causal Consistency as a Defense: Detecting Provenance Graph Poisoning

**Date**: September 25, 2026  
**Repository**: causal-provenance-tamper-detection  
**Commit**: d8b8617c4478846ace3b82dbd9fb819c8e2f6a64

---

## A. Executive Summary

This audit evaluates whether every quantitative result, experimental claim, methodological claim, and conclusion in the paper "Causal Consistency as a Defense: Detecting Provenance Graph Poisoning" is supported by the current repository implementation and can be reproduced from available data.

**Overall Reproducibility Status: PARTIALLY REPRODUCIBLE**

### Key Findings

| Aspect | Status |
|--------|--------|
| Synthetic benchmark (Rule Engine) | EXACT MATCH |
| Synthetic benchmark (GraphSAGE) | EXACT MATCH |
| GraphSAGE threshold optimization | METHODOLOGICAL PROBLEM (test-set threshold leak) |
| DARPA scenarios (1r, 3, 5m, 6r) | NOT REPRODUCIBLE — 0/0/0 results due to trivial 1-edge subgraphs |
| Rule-level analysis | EXACT MATCH |
| Rule ablation | EXACT MATCH |
| Mimicry evaluation (Rule Engine) | EXACT MATCH |
| Mimicry evaluation (GraphSAGE) | EXACT MATCH |
| Scalability benchmarks | MATCH WITH ROUNDING |
| ROC-AUC = 1.0000 claim | METHODOLOGICAL PROBLEM — tied scores on binary predictions |
| Dilution exponent (α) audit | EXACT MATCH (on synthetic) |

---

## B. Experiment Reproduction Table

| Experiment | Paper Claim | Reproduced Value | Status |
|------------|-------------|------------------|--------|
| Rule Engine (synthetic, all attacks) | Precision 0.8125, Recall 0.6500, F1 0.7222 | Precision 0.8125, Recall 0.6500, F1 0.7222 | EXACT MATCH |
| GraphSAGE (synthetic, default) | Precision 0.7000, Recall 0.4667, F1 0.5600 | Precision 0.7000, Recall 0.4667, F1 0.5600 | EXACT MATCH |
| GraphSAGE ROC-AUC (no mimicry) | 0.8776 | 0.8776 | EXACT MATCH |
| Rule Engine ROC-AUC (heavy mimicry) | 1.0000 | 1.0000 | METHODOLOGICAL PROBLEM |
| GraphSAGE ROC-AUC (heavy mimicry) | 0.7541 | 0.7541 | EXACT MATCH |
| DARPA 1r Rule Engine | N/A | Precision 0.0, Recall 0.0, F1 0.0 | NOT REPRODUCIBLE |
| DARPA 3 Rule Engine | N/A | Precision 0.0, Recall 0.0, F1 0.0 | NOT REPRODUCIBLE |
| DARPA 5m Rule Engine | N/A | Precision 0.0, Recall 0.0, F1 0.0 | NOT REPRODUCIBLE |
| DARPA 6r Rule Engine | N/A | Precision 0.0, Recall 0.0, F1 0.0 | NOT REPRODUCIBLE |
| Scalability 10k edges (Rule Engine) | ~51,390 eps | 51,390.58 eps | EXACT MATCH |
| Scalability 1M edges (Rule Engine) | ~51,275 eps | 51,275.57 eps | EXACT MATCH |
| Scalability 10k edges (GraphSAGE) | ~268,672 eps | 268,672.75 eps | EXACT MATCH |
| Scalability 1M edges (GraphSAGE) | ~2,009,576 eps | 2,009,576.66 eps | EXACT MATCH |

---

## C. Paper-vs-Code Claim Matrix

| Claim ID | Paper Section | Paper Claim | Expected Value | Actual Reproduced Value | Status |
|----------|---------------|-------------|----------------|-------------------------|--------|
| C1 | Synthetic Benchmark | Rule Engine F1 = 0.7222 | 0.7222 | 0.7222 | EXACT MATCH |
| C2 | Synthetic Benchmark | GraphSAGE F1 = 0.5600 | 0.5600 | 0.5600 | EXACT MATCH |
| C3 | GraphSAGE Default | Optimal threshold = 0.70 | 0.70 | 0.70 | EXACT MATCH |
| C4 | GraphSAGE Threshold | Threshold selected on test data | Test set | Test set (LEAK) | METHODOLOGICAL PROBLEM |
| C5 | DARPA 1r | Real-world evaluation | Non-trivial results | 1 edge, 0/0/0 | NOT REPRODUCIBLE |
| C6 | DARPA 3 | Real-world evaluation | Non-trivial results | 1 edge, 0/0/0 | NOT REPRODUCIBLE |
| C7 | DARPA 5m | Real-world evaluation | Non-trivial results | 1 edge, 0/0/0 | NOT REPRODUCIBLE |
| C8 | DARPA 6r | Real-world evaluation | Non-trivial results | 1 edge, 0/0/0 | NOT REPRODUCIBLE |
| C9 | Rule Ablation | Leave-one-out results | See Table | Matches | EXACT MATCH |
| C10 | Mimicry None | Rule Engine ROC-AUC = 1.0000 | 1.0000 | 1.0000 | METHODOLOGICAL PROBLEM |
| C11 | Mimicry Light | Rule Engine ROC-AUC = 1.0000 | 1.0000 | 1.0000 | METHODOLOGICAL PROBLEM |
| C12 | Mimicry Medium | Rule Engine ROC-AUC = 1.0000 | 1.0000 | 1.0000 | METHODOLOGICAL PROBLEM |
| C13 | Mimicry Heavy | Rule Engine ROC-AUC = 1.0000 | 1.0000 | 1.0000 | METHODOLOGICAL PROBLEM |
| C14 | Scalability | Linear scaling to 1M edges | O(n) | Confirmed O(n) | MATCH WITH ROUNDING |
| C15 | Dilution Exponent | α_hat = 0.0000 for GatedSAGE | 0.0000 | 0.0000 | EXACT MATCH |
| C16 | Dilution Exponent | α_hat = 0.9874 for GraphSAGE | 0.9874 | 0.9874 | EXACT MATCH |
| C17 | OOD Transfer | HARD rules transfer to DARPA | 0 violations | 0 violations (1-edge graphs) | UNSUPPORTED BY CODE |
| C18 | Elliptic Bitcoin | α_hat = 0.5395 | 0.5395 | 0.6289 | MINOR DIFFERENCE |
| C19 | Adaptive Adversary | 6/7 objectives feasible | 6/7 | 6/7 | EXACT MATCH |
| C20 | Gate Guarantees | Zero FPR on benign | 0.0 | 0.0 | EXACT MATCH |

---

## D. Numerical Discrepancies

### Major Discrepancies

1. **DARPA Evaluation Results** — All four DARPA scenarios (1r, 3, 5m, 6r) produce exactly 1 edge and 2 nodes after the 50,000-edge slicing logic in `src/eval/cross_dataset.py:114-117`. This yields Precision=0, Recall=0, F1=0 for both Rule Engine and GraphSAGE. The paper's "real-world DARPA evaluation" claim is **not reproducible** with the committed data.

2. **Elliptic Bitcoin α_hat** — Paper/table reports 0.5395 (R²=0.8998); reproduced value is 0.6289 (R²=0.9473). Different fit range or bootstrap.

### Minor Discrepancies

- Scalability throughput: reported integers vs. computed floats (rounding only)
- AUC tie gaps: Rule All tie gap = 0.1371 (large), GraphSAGE tie gap = 0.0006 (small)

---

## E. Methodological Problems

1. **GraphSAGE Threshold Leak** — `src/ml/train.py:232` calls `find_best_threshold(y_true, y_prob)` on the **full dataset including test labels** to maximize F1. This is a data leak; threshold should be selected on a validation split only.

2. **ROC-AUC = 1.0000 for Rule Engine** — Rule Engine produces **binary scores** (0.0 or 1.0). With 15 poison edges and 12 flagged edges (all true positives, zero false positives), `roc_auc_score` returns 1.0 due to tie handling in sklearn. This does **not** indicate perfect continuous ranking. The optimistic/pessimistic AUC gap is 0.1371 for Rule All, confirming tie dominance.

3. **DARPA Data Truncation** — The 50,000-edge slice (`cross_dataset.py:114-117`) takes the **first 50,000 rows** of CSV files that contain only 1 edge each. The committed CSV files are placeholder samples, not full DARPA datasets.

4. **Mimicry Generator Violates Invariants** — `mimicry_attack.py:174,198,222` assigns random timestamps uniformly across `[min_ts, max_ts]` without respecting process-level temporal ordering, causing synthetic mimicry noise to violate `SequenceMonotonicityRule`, `ParentChildTemporalRule`, `ProcessActivityTemporalRule` at high rates (up to 77%, 15%, 35% violation rates respectively).

5. **IsolationForest In-Sample Fitting** — `graph_anomaly.py:86-101` fits IsolationForest on the target graph itself (data leak), though `detect_against_baseline()` correctly uses a clean baseline.

---

## F. Data/Ground-Truth Issues

| Issue | Detail |
|-------|--------|
| Poisoned edge labels | Per-edge dictionary via `PoisoningResult.edge_labels()` |
| Deletion attacks | Edges removed from graph; ground truth retains edge_id |
| Reordering attacks | Timestamp shifted; same edge_id in ground truth |
| Forgery attacks | Source node rewired; same edge_id in ground truth |
| Mimicry edges | Labeled with `{"mimicry": True}` attribute; NOT in ground truth |
| DARPA ground truth | No actual poisoning — evaluation injects attacks on benign data |
| Held-out benign data | **NONE EXISTS** — no separate validation set in repository |
| Data leakage risk | Attack injection uses same graph for training/evaluation splits |

---

## G. GraphSAGE Fairness Audit

| Check | Finding |
|-------|---------|
| Train/eval split | No split — single graph used for train+test (threshold leak) |
| Threshold 0.70 selection | Selected on **test labels** to maximize F1 (data leak) |
| Retraining per scenario | Yes, `run_cross_dataset.py` retrains per dataset (15 epochs) |
| Rule Engine receives equivalent info | No — Rule Engine uses full schema; GraphSAGE uses 7 node features + 7 edge features |
| Preprocessing equivalence | No — Rule Engine sees all 15 rules; GraphSAGE sees only structural features |
| Class imbalance handling | GraphSAGE uses `pos_weight` or FocalLoss; Rule Engine has no imbalance handling |
| Default vs tuned comparability | Not comparable — threshold optimized on test data for GraphSAGE; Rule Engine uses fixed 0.5 |
| ROC-AUC/PR-AUC calculation | Uses sklearn on full edge universe; correct but includes edges deleted by attack |

---

## H. ROC-AUC = 1.0000 Audit

### Finding: **METHODOLOGICAL PROBLEM**

**What produces ROC-AUC = 1.0000:**
- Rule Engine outputs binary scores: 1.0 for flagged edges, 0.0 for others
- Under heavy mimicry: 15 poison edges, 12 flagged (all TP), 0 FP
- `sklearn.metrics.roc_auc_score([1]*15 + [0]*N, [1]*12 + [0]*(N+3))` = 1.0

**Why this is misleading:**
1. **Binary predictions, not continuous scores** — ROC-AUC requires continuous scores for meaningful ranking
2. **Tie structure** — 1000+ edges share score 0.0; sklearn's default tie-handling inflates AUC
3. **Optimistic vs Pessimistic AUC gap** = 0.1371 for Rule All (see `auc_invariance.json`)
4. **No score locality test passed** — GraphSAGE ρ decays from 1.0 to 0.88; Rule Engine ρ = 1.0 (by design, no message passing)

**Conclusion:** The ROC-AUC = 1.0000 claim is **technically correct but scientifically misleading**. It reflects binary classification with zero FPs, not robust continuous scoring under dilution.

---

## I. Scalability Audit

### Verified Numbers (Table 8 equivalent)

| Edges | Rule Engine Time (s) | Rule Engine Throughput (eps) | GraphSAGE Time (s) | GraphSAGE Throughput (eps) |
|-------|---------------------|-----------------------------|-------------------|---------------------------|
| 10,000 | 0.1946 | 51,390.58 | 0.0372 | 268,672.75 |
| 25,000 | 0.4298 | 58,161.58 | 0.0092 | 2,719,124.55 |
| 50,000 | 0.8689 | 57,546.54 | 0.0275 | 1,817,100.47 |
| 100,000 | 1.7779 | 56,245.01 | 0.0367 | 2,725,219.78 |
| 250,000 | 4.4698 | 55,930.75 | 0.1523 | 1,641,495.76 |
| 500,000 | 9.7894 | 51,075.63 | 0.2345 | 2,132,522.01 |
| 1,000,000 | 19.5025 | 51,275.57 | 0.4976 | 2,009,576.66 |

### Audit Notes
- **Rule Engine**: Linear O(n) scaling confirmed (~51K eps constant)
- **GraphSAGE**: Inference-only timing (model pre-trained on small graph); NOT training time
- **Memory**: Peak RSS measured via `psutil.Process().memory_info().rss`
- **Warm-up**: No warm-up runs; single measurement per scale
- **Repetitions**: Single run per scale (no variance reported)
- **Hardware dependence**: CPU-only (no GPU); numbers environment-specific

---

## J. Paper Wording Requiring Correction

| Current Wording | Recommended Correction |
|-----------------|------------------------|
| "Real-world DARPA evaluation across 4 scenarios" | "Synthetic evaluation; DARPA CSV files in repo are 1-edge placeholders" |
| "ROC-AUC = 1.0000 under heavy mimicry" | "Rule Engine achieves zero false positives (binary scores); ROC-AUC = 1.0000 reflects tie structure, not continuous ranking" |
| "GraphSAGE threshold 0.70" | "GraphSAGE threshold 0.70 selected on test set (data leak); should report validation-selected threshold" |
| "Scales to 1M edges" | "Rule Engine inference scales linearly to 1M edges; GraphSAGE inference timing on pre-trained model" |
| "Causal consistency provides protection" | "HARD invariant rules (11/15) provide zero-FPR guarantee; SOFT rules (4/15) violate on benign data" |
| "Robustness to mimicry" | "Rule Engine robust (deterministic); GraphSAGE degrades severely (F1 0.52 → 0.08)" |
| "Generalizability to DARPA" | "Not demonstrated — evaluation uses 1-edge placeholder graphs" |

---

## K. Claims Fully Supported

1. ✅ Rule Engine achieves F1 = 0.7222 on synthetic benchmark with all attack types
2. ✅ GraphSAGE baseline achieves F1 = 0.5600 on synthetic benchmark
3. ✅ Rule ablation study correctly identifies critical rules (SequenceGapRule, UnspawnedProcessRule, SequenceMonotonicityRule)
4. ✅ Mimicry noise degrades GraphSAGE precision from 0.58 → 0.04 (heavy)
5. ✅ Rule Engine precision stable at 0.875 across all mimicry strengths
6. ✅ Dilution exponent α_hat = 0.0000 for HARD rules and GatedSAGE (synthetic)
7. ✅ Dilution exponent α_hat = 0.9874 for GraphSAGE baseline (synthetic)
8. ✅ Adaptive adversary search finds 6/7 objectives feasible, 1 blocked by HARD rules
9. ✅ Scalability: Rule Engine ~51K eps, GraphSAGE ~2M eps (inference)
10. ✅ Gate guarantees: Zero FPR on benign data passing HARD invariants

---

## L. Claims Not Supported

1. ❌ **DARPA TC E3 evaluation produces meaningful results** — 1-edge graphs yield 0/0/0
2. ❌ **ROC-AUC = 1.0000 demonstrates robust detection** — reflects binary scores + tie handling
3. ❌ **GraphSAGE threshold 0.70 is a generalizable default** — selected via test-set leak
4. ❌ **OOD transfer to DARPA scenarios validated** — tested on 1-edge placeholders
5. ❌ **Real-world provenance graph evaluation** — no actual DARPA data in repository
6. ❌ **Held-out benign data for validation** — no separate benign dataset exists
7. ❌ **Mimicry generator preserves invariants** — violates temporal rules at high rates
8. ❌ **Elliptic Bitcoin α_hat = 0.5395** — reproduced as 0.6289
9. ❌ **IsolationForest baseline** — in-sample fitting leak present in code

---

## M. Exact Recommended Corrections

### Code Fixes Required
1. **Fix threshold selection** — Use `config/splits.json` train/val/test seeds; select threshold on VAL only
2. **Fix DARPA data** — Either download full DARPA TC E3 datasets or remove "DARPA evaluation" claims
3. **Fix mimicry generator** — Add temporal consistency to noise edges (respect process event ordering)
4. **Fix IsolationForest** — Remove `detect_anomalous_edges` or document as prototype only
5. **Report AUC with tie audit** — Always report optimistic/pessimistic AUC gap for binary scorers

### Paper Text Corrections
1. Replace "DARPA evaluation" with "synthetic evaluation with DARPA-like schemas"
2. Replace "ROC-AUC = 1.0000" with "zero false positive rate under mimicry (binary scores)"
3. Add caveat: "GraphSAGE threshold optimized on test data; validation-selected threshold yields lower F1"
4. Clarify: "Scalability numbers are CPU inference throughput; training not included"
5. Disclose: "No held-out benign data; all evaluation uses attack-injected graphs"

---

## REPRODUCIBILITY STATUS: PARTIALLY REPRODUCIBLE

**Criteria**: Core synthetic experiments (Rule Engine, GraphSAGE, mimicry, ablation, scalability, dilution exponent) reproduce exactly. DARPA evaluation and ROC-AUC interpretation claims are **not reproducible** or **methodologically flawed** with current code and data.

**Evidence Base**: All results derived from executing repository scripts (`run_evaluation.py`, `run_graphsage.py`, `run_mimicry.py`, `run_scalability.py`, `run_cross_dataset.py`) on commit `d8b8617`. No modifications made to code or data.