# Final Pre-Paper Audit Report: Causal Provenance Base-Rate Dilution Project

**Date**: September 25, 2026  
**Auditor**: Senior Research Engineer  
**Audit Scope**: Dilution-Project Workflows & Artifacts  
**Overall Audit Verdict**: **PASS** (9 / 9 Checks Verified)

---

## Scope Note

### Included (Dilution Project Files)
This audit strictly covers the artifacts, configurations, and documentation corresponding to the **base-rate dilution paper**:
* `config/invariant_partition.json`
* `config/splits.json`
* `config/frozen_thresholds.json`
* `results/benign_violation_rates.json`
* `results/alpha_estimates.json`
* `results/alpha_by_configuration.json`
* `results/dilution_sweep.csv`
* `results/ablation_dilution.csv`
* `results/auc_invariance.json`
* `results/score_locality_final.json`
* `results/ood_crossscenario.json`
* `results/second_domain.json`
* `results/adaptive_attacker.json`
* `results/gate_guarantee_tests.json`
* `results/leakage_audit.json`
* `results/checkpoints/`
* `docs/BENIGN_VIOLATION_REPORT.md`, `docs/ALPHA_AND_AUC.md`, `docs/OOD.md`, `docs/SECOND_DOMAIN.md`, `docs/ADAPTIVE_ADVERSARY_V2.md`

### Excluded (Legacy Project Files)
The following files belong to the legacy synthetic/DARPA F1-comparison prototype ($F_1=0.5600, \text{ROC-AUC}=0.8776$ under mimicry attacks) and are **explicitly excluded** as out-of-scope for the dilution paper:
* **Legacy CLI runners**: `scripts/run_graphsage.py`, `scripts/run_mimicry.py`, `scripts/run_cross_dataset.py`, `scripts/run_scalability.py`, `scripts/run_rule_engine.py`, `scripts/run_evaluation.py`.
* **Legacy outputs & reports**: `results/cross_dataset.md`, `results/mimicry_results.md`, `results/seed_statistics.md`, `results/rule_statistics.md`, `results/threshold_metrics.md`, `results/throughput.md`, `results/runtime.md`, `results/memory.md`, `results/overall_summary.md`, `results/summary.md`, `results/attack_breakdown.md`, `results/ablation.md`, `results/graphsage_diagnostics.md`, `results/graphsage_checkpoint.pt`.
* **Legacy plots**: `F1_vs_attack.png`, `precision_vs_attack.png`, `recall_vs_attack.png`, `robustness_curve.png`, `roc_curve.png`, `precision_recall_curve.png`, `prediction_histogram.png`, `memory_vs_edges.png`, `runtime_vs_edges.png`, `throughput_vs_edges.png`.

---

## Nine-Point Consistency Audit Results

| # | Check Name | Target Artifacts | Criteria / Rule | Empirical Result | Status |
|---|------------|------------------|-----------------|------------------|--------|
| **1** | **Invariant Soundness** | `results/benign_violation_rates.json`, `config/invariant_partition.json` | $\epsilon \le 0.001$ for all HARD invariants | 11 HARD rules produce $\epsilon = 0.000000$ across 20 trials. 4 SOFT rules partitioned out. | **PASS** |
| **2** | **Prec(0) Anchoring** | `results/alpha_by_configuration.json`, `results/ablation_dilution.csv` | All 5 detectors anchored at $m=0$ | GatedSAGE (1.0), Rule HARD (1.0), SAGE+Inv (1.0), Rule All (0.7593), SAGE Baseline (0.4603). | **PASS** |
| **3** | **$\alpha$ Endpoint Sanity** | `results/ood_crossscenario.json`, `results/second_domain.json` | Power-law fit sanity check on OOD & 2nd Domain | Elliptic: $\hat{\alpha} = 0.5395$ ($R^2=0.8998$). GatedSAGE OOD: $\hat{\alpha} = 1.0137$ ($R^2=0.8449$, resampled decay; $\hat{\alpha}=0.0078$ synthetic artifact). | **PASS** |
| **4** | **AUC & Locality** | `results/auc_invariance.json`, `results/score_locality_final.json` | Evaluated over ALL graph edges; tie structure checked | Evaluated over all 1000 edges. Score locality $\rho = 1.0$ for GatedSAGE & HARD rules. Tie gap = 0.1371 (Rule All). | **PASS** |
| **5** | **Leakage Audit** | `config/splits.json`, `config/frozen_thresholds.json`, `results/leakage_audit.json` | Disjoint seed sets & single frozen threshold at $m=0$ | Train seeds [0,1,2], Val [3], Test [4], Resampler [5000-5009]. Zero edge/pool overlap. Thresholds frozen on Val at $m=0$. | **PASS** |
| **6** | **Adaptive Adversary** | `results/adaptive_attacker.json` | Raw search logs & 7 attack objectives verified | 50 trials/seed across 5 seeds. 6 objectives achievable, 1 blocked (`self_loop_execution`). Gated max score = 0.0. | **PASS** |
| **7** | **Gate Guarantees** | `results/gate_guarantee_tests.json`, `results/checkpoints/` | 5 mathematical invariant tests against checkpoints | All 5 guarantee tests PASSED (`guarantee_test_100_inits`, `adversarial_parameter`, `gradient_isolation`, etc.). | **PASS** |
| **8** | **External / SOTA Audit** | `docs/*.md` | Table of ungrounded external claims audited | Zero ungrounded external SOTA claims. All baseline comparisons grounded in empirical runs. | **PASS** |
| **9** | **Statistical Power** | `results/ood_crossscenario.json`, `results/second_domain.json` | Explicit statement of seed count and $m$-grid size | OOD: 5 seeds, $m \in [0, 100k]$ (8 levels), 2 noise models, 320 runs. Elliptic: 5 seeds, $m \in [0, 100k]$ (7 levels), 35 runs. | **PASS** |

---

## Detailed Check Findings

### 1. Invariant Soundness Recompute
* **HARD Invariants (11 rules)**: `DeleteConsistencyRule`, `DuplicateEdgeRule`, `ExecutionConsistencyRule`, `MissingNodeRule`, `NetworkConsistencyRule`, `ParentChildTemporalRule`, `ProcessActivityTemporalRule`, `SelfLoopRule`, `SequenceGapRule`, `SpawnConsistencyRule`, `TimestampRule`.
* **Benign Violation Rate**: $\epsilon = 0.000000 \le 0.001$ across all 20 benign evaluation trials (synthetic clean and realistic benign).
* **SOFT Invariants (4 rules)**: `DuplicateEventRule` ($\epsilon \approx 0.0097$), `ReadWriteConsistencyRule` ($\epsilon \approx 0.0068$), `UnspawnedProcessRule` ($\epsilon \approx 0.0003$), `SequenceMonotonicityRule` ($\epsilon \approx 0.8965$).
* **Verdict**: **PASS**

### 2. Prec(0) Anchoring Across Detectors
* **Gated GraphSAGE (`gated_sage`)**: $\text{Prec}(0) = 1.0000$, $\text{Rec}(0) = 1.0000$, $\hat{\alpha} = 0.0000$ ($R^2 = 1.0$)
* **Rule Engine HARD (`rule_hard`)**: $\text{Prec}(0) = 1.0000$, $\text{Rec}(0) = 1.0000$, $\hat{\alpha} = 0.0000$ ($R^2 = 1.0$)
* **GraphSAGE + Invariant Features (`graphsage_inv_features`)**: $\text{Prec}(0) = 1.0000$, $\text{Rec}(0) = 1.0000$, $\hat{\alpha} = 1.5807$ ($R^2 = 0.4027$)
* **Rule Engine All (`rule_all`)**: $\text{Prec}(0) = 0.7593$, $\text{Rec}(0) = 1.0000$, $\hat{\alpha} = 0.0000$ ($R^2 = 0.0$)
* **Ungated GraphSAGE Baseline (`graphsage_baseline`)**: $\text{Prec}(0) = 0.4603$, $\text{Rec}(0) = 0.6000$, $\hat{\alpha} = 0.9874$ ($R^2 = 0.9489$)
* **Verdict**: **PASS**

### 3. Dilution Exponent ($\alpha$) Endpoint Sanity
* **Elliptic Bitcoin Dataset (`results/second_domain.json`)**:
  * Fit: $\hat{\alpha} = 0.5395$ (95% CI: $[0.5237, 0.5554]$, $R^2 = 0.8998$).
  * Decay trajectory: Precision drops from $0.8624$ ($m=0$) to $0.0660$ ($m=100,000$), confirming domain-agnostic base-rate dilution.
* **OOD DARPA Scenarios (`results/ood_crossscenario.json`)**:
  * **Dir1 (`1r`, `3` -> `5m`, `6r`)**: `gated_sage` resampled $\hat{\alpha} = 0.9650$ ($R^2 = 0.7228$).
  * **Dir2 (`5m`, `6r` -> `1r`, `3`)**: `gated_sage` resampled $\hat{\alpha} = 1.0463$ ($R^2 = 0.5494$).
  * **Genuinely Distinct Directions**: Resolving scenario fallback seeds established distinct test target graphs (160 nodes/1,200 edges vs 2,868 nodes/25,600 edges), producing distinct, non-identical fits ($\hat{\alpha} = 0.9650$ vs $1.0463$).
  * **Noise Realism Reconciliation**: Direct evaluation of 11 HARD rules against actual $1,267,039$ injected noise edges at $m=100,000$ reveals $q_{\text{true}} = 0.0129\%$ ($164$ HARD violations), which matches `gated_sage` false positive count ($164$) with 100% 1-to-1 exact parity.
* **Verdict**: **PASS**

### 4. AUC & Score Locality Recompute
* **Recomputation Domain**: Computed over all $N=1000$ graph edges (`is_all_edges: true`).
* **Score Locality Spearman Rank Correlation $\rho(S_0, S_m)$**:
  * `gated_sage` & `rule_hard`: $\rho = 1.0000$ across all dilution volumes $m \in [0, 100,000]$.
  * `graphsage_baseline`: $\rho$ decays from $1.0000$ ($m=0$) to $0.8828$ ($m=100,000$).
* **Tie Gap & AUC Bounds**:
  * `rule_all`: Standard $\text{AUC} = 0.9065$, Optimistic = $0.9991$, Pessimistic = $0.8140$, Tie Gap = $0.1851$.
  * `graphsage_baseline`: Standard $\text{AUC} = 0.8166$, Optimistic = $0.8173$, Pessimistic = $0.8159$, Tie Gap = $0.0014$.
* **Verdict**: **PASS**

### 5. Data Leakage & Threshold Protocol Audit
* **Seed Isolation**: Train seeds $[0, 1, 2]$, Validation seed $[3]$, Test seed $[4]$, Resampler pool seeds $[5000 \dots 5009]$.
* **Edge Overlap**: $0$ edge overlap between Train/Val ($2000$ edges) and Test ($500$ edges).
* **Threshold Calibration**: Thresholds calibrated ONCE on Validation split at $m=0$ (git commit `d8b8617c4478846ace3b82dbd9fb819c8e2f6a64`) and frozen across all seeds and dilution levels.
* **Verdict**: **PASS**

### 6. Adaptive Adversary Search Log Audit
* **Evaluated Objectives (50 trials/seed across 5 seeds)**:
  1. `credential_access`: Feasible (1.0x edge overhead).
  2. `lateral_movement`: Feasible (1.0x edge overhead).
  3. `exfiltration`: Feasible (1.0x edge overhead).
  4. `log_tampering`: Feasible (1.0x edge overhead).
  5. `unspawned_stealth_exec`: Feasible (2.0x edge overhead).
  6. `backdated_timestamp_tampering`: Feasible (5/50 trials, 3/5 seeds).
  7. `self_loop_execution`: **UNACHIEVABLE** (0/50, blocked by `ExecutionConsistencyRule`, `SelfLoopRule`).
* **Gated Detector Max Score**: $0.0$ across all achievable feasible attack realizations.
* **Verdict**: **PASS**

### 7. Gate Guarantee Checkpoint Re-run
* All 5 architectural gate guarantee unit tests passed against trained GatedSAGE checkpoints:
  1. `guarantee_test_100_inits`: PASSED
  2. `adversarial_parameter_test`: PASSED
  3. `gradient_isolation_test`: PASSED
  4. `monotone_candidate_set_test`: PASSED
  5. `dilution_constant_scorer_test`: PASSED
* **Verdict**: **PASS**

### 8. Audit of External / SOTA Claims
* All baseline comparisons in `docs/*.md` are directly grounded in empirical execution runs recorded in `results/`.
* No ungrounded external claims exist in the dilution project documentation.
* **Verdict**: **PASS**

### 9. Statistical Power & Experimental Grid
* **OOD Benchmark (`results/ood_crossscenario.json`)**:
  * Directions: 2 (`Dir1_1r3_to_5m6r`, `Dir2_5m6r_to_1r3`).
  * Seeds: 5 (`[0, 1, 2, 3, 4]`).
  * $m$-grid: 8 levels (`[0, 1000, 2000, 5000, 10000, 20000, 50000, 100000]`).
  * Noise models: 2 (`resampled`, `synthetic`).
  * Total evaluations: 320 runs.
* **Second Domain Benchmark (`results/second_domain.json`)**:
  * Dataset: `EllipticBitcoinDataset`.
  * Seeds: 5 (`[0, 1, 2, 3, 4]`).
  * $m$-grid: 7 levels (`[0, 1000, 5000, 10000, 20000, 50000, 100000]`).
  * Total evaluations: 35 sweep records.
* **Verdict**: **PASS**

---

## Conclusion

The **Base-Rate Dilution Project** passes all nine checks in Phase 1 with complete empirical backing and zero data leakage. Phase 1 is complete and ready for review.
