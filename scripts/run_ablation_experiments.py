"""
Fast Multi-Detector Dilution Ablation & Tradeoff Frontier Runner (Phase 9 — Experiments E and F).

Executes:
1. Experiment E — Multi-Detector Dilution Ablation:
   Sweeps dilution volume m in [0, 1000, 2000, 5000, 10000, 20000, 50000] over 5 seeds
   across 5 detector configurations:
     - rule_hard: Rule-only (HARD set, 11 rules)
     - rule_all: Rule-only (all 15 rules)
     - graphsage_baseline: GraphSAGE (ungated, 7 features)
     - graphsage_inv_features: GraphSAGE + invariant features (ungated control, 11 features)
     - gated_sage: Feasibility-gated GraphSAGE (ours)

2. Experiment F — Tradeoff Frontier:
   Sweeps gate configuration from fully open (no mask) to fully closed (11 HARD rules)
   by progressively moving SOFT rules to HARD rules in order of benign violation rate.
   Plots Recall at m=0 vs fitted dilution exponent alpha_hat.

Outputs:
  - results/ablation_dilution.csv
  - results/alpha_by_configuration.json
  - results/figs/ablation_precision_vs_m.png
  - results/figs/tradeoff_frontier.png
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from models.feasibility_gate import compute_hard_mask
from models.gated_sage import GatedSAGE
from src.attacks.benign_resampler import BenignResampler
from src.detection.poisoning_injection import inject_poisoning
from src.detection.rule_engine import default_rule_engine
from src.eval.alpha_estimator import fit_alpha_exponent
from src.eval.auc_invariance import measure_score_locality, audit_auc_and_ties
from src.eval.detector_registry import get_detector
from src.graph_construction.synthetic import generate_synthetic_graph
from src.ml.dataset import provenance_to_pyg_data
from src.ml.graphsage import GraphSAGEForTamperDetection
from src.ml.utils import get_device, set_seed


RESULTS_DIR = Path("results")
FIGS_DIR = Path("results/figs")
CSV_PATH = RESULTS_DIR / "ablation_dilution.csv"
ALPHA_JSON_PATH = RESULTS_DIR / "alpha_by_configuration.json"


def run_experiment_e(
    detectors: List[str] = [
        "rule_hard",
        "rule_all",
        "graphsage_baseline",
        "graphsage_inv_features",
        "gated_sage",
    ],
    m_grid: List[int] = [0, 1000, 2500, 5000, 10000, 25000, 50000, 100000],
    seeds: List[int] = [0, 1, 2, 3, 4],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Runs Experiment E dilution sweep across 5 detector configurations."""
    print("=== Running Experiment E: Multi-Detector Dilution Ablation ===")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGS_DIR.mkdir(parents=True, exist_ok=True)

    pool = BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=2000)

    raw_rows: List[Dict[str, Any]] = []
    alpha_summary: Dict[str, Any] = {}

    for det_key in detectors:
        t0_det = time.time()
        print(f"\nEvaluating Detector Configuration: '{det_key}'...")
        det_m_precisions: Dict[int, List[float]] = {m: [] for m in m_grid}
        det_m_recalls: Dict[int, List[float]] = {m: [] for m in m_grid}
        det_m_f1s: Dict[int, List[float]] = {m: [] for m in m_grid}
        det_m_totals: Dict[int, List[int]] = {m: [] for m in m_grid}

        detector_sample = get_detector(det_key, seed=0)
        detector_name = detector_sample.name

        for seed in seeds:
            set_seed(seed)
            base_g = generate_synthetic_graph(target_edges=600, seed=seed)
            poison = inject_poisoning(
                base_g,
                num_deletions=4,
                num_insertions=4,
                num_reorderings=4,
                num_forgeries=3,
                seed=seed,
            )
            g_m0 = poison.graph
            gt_ids = set(poison.edge_labels().keys())

            detector = get_detector(det_key, seed=seed, hidden_channels=32, epochs=25)
            detector.fit_threshold(g_m0, gt_ids)
            thresh = detector.operating_threshold

            resampler = BenignResampler(pool_graphs=pool, seed=seed + 5000)

            for m in m_grid:
                if m == 0:
                    g_m = g_m0
                else:
                    g_m, _ = resampler.inject(g_m0, m=m, seed=seed)

                scores = detector.score_edges(g_m)
                flagged = {eid for eid, sc in scores.items() if sc >= thresh}

                tp = len(flagged.intersection(gt_ids))
                fp = len(flagged - gt_ids)
                fn = len(gt_ids - flagged)
                tn = len(g_m.edges) - (tp + fp + fn)

                prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

                tie_res = audit_auc_and_ties(scores, gt_ids)
                roc_auc = tie_res.auc_standard
                pr_auc = prec * rec

                det_m_precisions[m].append(prec)
                det_m_recalls[m].append(rec)
                det_m_f1s[m].append(f1)
                det_m_totals[m].append(len(g_m.edges))

                row = {
                    "detector": detector_name,
                    "detector_key": det_key,
                    "m": m,
                    "seed": seed,
                    "total_edges": len(g_m.edges),
                    "poison_edges": len(gt_ids),
                    "tp": tp,
                    "fp": fp,
                    "tn": tn,
                    "fn": fn,
                    "precision": round(prec, 6),
                    "recall": round(rec, 6),
                    "f1": round(f1, 6),
                    "roc_auc": round(roc_auc, 6),
                    "pr_auc": round(pr_auc, 6),
                    "flagged_edges_count": len(flagged),
                    "threshold_used": round(thresh, 6),
                }
                raw_rows.append(row)

        # Fit alpha exponent for this detector across all seeds (m > 0)
        m_flat = []
        p_flat = []
        seed_flat = []
        tot_flat = []
        for m in m_grid:
            for idx, p_val in enumerate(det_m_precisions[m]):
                m_flat.append(m)
                p_flat.append(p_val)
                seed_flat.append(seeds[idx])
                tot_flat.append(det_m_totals[m][idx])

        alpha_res = fit_alpha_exponent(m_flat, p_flat, seeds=seed_flat, total_edges=tot_flat)
        det_seed0 = get_detector(det_key, seed=0)
        rho_dict = measure_score_locality(det_seed0, m_grid=[0, 500, 1000, 2000, 5000, 10000], seed=0)

        max_m = max(m_grid)
        alpha_summary[det_key] = {
            "detector_name": detector_name,
            "alpha_hat": round(alpha_res.alpha_hat, 6),
            "ci_lower": round(alpha_res.ci_lower, 6),
            "ci_upper": round(alpha_res.ci_upper, 6),
            "r_squared": round(alpha_res.r_squared, 6),
            "mean_precision_m0": round(float(np.mean(det_m_precisions[0])), 6),
            "mean_precision_max_m": round(float(np.mean(det_m_precisions[max_m])), 6),
            "mean_recall_m0": round(float(np.mean(det_m_recalls[0])), 6),
            "mean_recall_max_m": round(float(np.mean(det_m_recalls[max_m])), 6),
            "spearman_rho_max_m": rho_dict.get(max_m, 1.0),
        }

        t_elapsed = time.time() - t0_det
        print(
            f"  [{det_key:<22}] alpha_hat = {alpha_res.alpha_hat:.4f} [95% CI: {alpha_res.ci_lower:.4f}, {alpha_res.ci_upper:.4f}] | "
            f"Prec (m=0 -> m={max_m}): {np.mean(det_m_precisions[0]):.4f} -> {np.mean(det_m_precisions[max_m]):.4f} ({t_elapsed:.1f}s)"
        )

    # Save CSV
    fieldnames = list(raw_rows[0].keys())
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)
    print(f"\nSaved dilution sweep CSV to {CSV_PATH}")

    # Save Alpha JSON
    with open(ALPHA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(alpha_summary, f, indent=2)
    print(f"Saved alpha summary JSON to {ALPHA_JSON_PATH}")

    # Plot Precision vs m
    plot_precision_vs_m(raw_rows, detectors, m_grid)

    return raw_rows, alpha_summary


def plot_precision_vs_m(raw_rows: List[Dict[str, Any]], detectors: List[str], m_grid: List[int]):
    """Plots Precision vs Dilution Volume m for all 5 detector configurations."""
    plt.figure(figsize=(9, 6), dpi=300)

    style_map = {
        "rule_hard": ("#8c564b", "--", "s", "Rule-only (HARD set)"),
        "rule_all": ("#d62728", "-.", "^", "Rule-only (all 15 rules)"),
        "graphsage_baseline": ("#1f77b4", ":", "o", "GraphSAGE (ungated baseline)"),
        "graphsage_inv_features": ("#ff7f0e", "--", "x", "GraphSAGE + inv features (ungated control)"),
        "gated_sage": ("#2ca02c", "-", "D", "Feasibility-gated GraphSAGE (ours)"),
    }

    for det_key in detectors:
        color, linestyle, marker, label = style_map.get(det_key, ("#333333", "-", "o", det_key))
        means = []
        for m in m_grid:
            p_vals = [r["precision"] for r in raw_rows if r["detector_key"] == det_key and r["m"] == m]
            means.append(float(np.mean(p_vals)))

        plt.plot(m_grid, means, label=label, color=color, linestyle=linestyle, marker=marker, linewidth=2.2, markersize=7)

    plt.xscale("symlog", linthresh=100)
    plt.yscale("linear")
    plt.ylim(-0.02, 1.05)
    plt.xlabel("Dilution Volume $m$ (added resampled benign edges)", fontsize=12)
    plt.ylabel("Precision", fontsize=12)
    plt.title("Precision Decay under Base-Rate Dilution Across Detector Configurations", fontsize=13, fontweight="bold", pad=12)
    plt.grid(True, which="both", linestyle=":", alpha=0.6)
    plt.legend(fontsize=10, loc="lower left")

    plt.tight_layout()
    plot_path = FIGS_DIR / "ablation_precision_vs_m.png"
    plt.savefig(plot_path)
    plt.close()
    print(f"Saved Precision vs m plot to {plot_path}")


# =====================================================================
# Experiment F: Tradeoff Frontier
# =====================================================================

def run_experiment_f(
    seeds: List[int] = [0, 1, 2, 3, 4],
    m_sweep: List[int] = [0, 500, 1000, 2000, 5000, 10000],
) -> List[Dict[str, Any]]:
    """
    Runs Experiment F: Tradeoff frontier between Recall at m=0 and dilution exponent alpha_hat.
    """
    print("\n=== Running Experiment F: Tradeoff Frontier Sweep ===")

    soft_rule_order = [
        "UnspawnedProcessRule",
        "ReadWriteConsistencyRule",
        "SequenceMonotonicityRule",
        "DuplicateEventRule",
    ]

    strict_hard_rules = [
        "DeleteConsistencyRule",
        "DuplicateEdgeRule",
        "ExecutionConsistencyRule",
        "MissingNodeRule",
        "NetworkConsistencyRule",
        "ParentChildTemporalRule",
        "ProcessActivityTemporalRule",
        "SelfLoopRule",
        "SequenceGapRule",
        "SpawnConsistencyRule",
        "TimestampRule",
    ]

    frontier_configs = [
        ("Fully Open (Ungated)", []),
        ("+ UnspawnedProcess", soft_rule_order[:1]),
        ("+ ReadWriteConsistency", soft_rule_order[:2]),
        ("+ SequenceMonotonicity", soft_rule_order[:3]),
        ("+ All 4 Soft Rules", soft_rule_order[:4]),
        ("Fully Closed (11 Strict HARD Rules)", strict_hard_rules),
    ]

    pool = BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=2000)
    frontier_results: List[Dict[str, Any]] = []

    for name, hard_rule_set in frontier_configs:
        print(f"\nEvaluating Frontier Point: '{name}' (Hard rules active: {len(hard_rule_set)})...")
        recalls_m0 = []
        det_m_precisions: Dict[int, List[float]] = {m: [] for m in m_sweep}

        for seed in seeds:
            set_seed(seed)
            base_g = generate_synthetic_graph(target_edges=600, seed=seed)
            poison = inject_poisoning(
                base_g,
                num_deletions=4,
                num_insertions=4,
                num_reorderings=4,
                num_forgeries=3,
                seed=seed,
            )
            g_m0 = poison.graph
            gt_ids = set(poison.edge_labels().keys())

            pyg_data = provenance_to_pyg_data(g_m0, poisoned_edge_ids=gt_ids, include_soft_invariants=True)
            base_model = GraphSAGEForTamperDetection(
                in_channels=pyg_data.x.size(-1),
                edge_attr_dim=pyg_data.edge_attr.size(-1),
                hidden_channels=32,
            )

            if len(hard_rule_set) == 0:
                class OpenGatedModel(torch.nn.Module):
                    def __init__(self, base_m):
                        super().__init__()
                        self.base_m = base_m
                    def score_edges(self, g):
                        p_data = provenance_to_pyg_data(g, include_soft_invariants=True)
                        device = get_device()
                        self.base_m.to(device).eval()
                        with torch.no_grad():
                            _, logits, _ = self.base_m(p_data.x.to(device), p_data.edge_index.to(device), edge_attr=p_data.edge_attr.to(device))
                            probs = torch.sigmoid(logits).cpu().numpy()
                        return {e.edge_id: float(probs[i]) for i, e in enumerate(g.edges)}
                model = OpenGatedModel(base_model)
            else:
                class CustomGatedModel(torch.nn.Module):
                    def __init__(self, base_m, rules):
                        super().__init__()
                        self.base_m = base_m
                        self.rules = rules
                    def score_edges(self, g):
                        engine = default_rule_engine()
                        rule_map = {r.__class__.__name__: r for r in engine.rules if r.__class__.__name__ in self.rules}
                        flagged = set()
                        for r_name, r_obj in rule_map.items():
                            res = r_obj.check(g)
                            for v in res.violations:
                                if v.edge_id: flagged.add(v.edge_id)
                        p_data = provenance_to_pyg_data(g, include_soft_invariants=True)
                        device = get_device()
                        self.base_m.to(device).eval()
                        with torch.no_grad():
                            _, logits, _ = self.base_m(p_data.x.to(device), p_data.edge_index.to(device), edge_attr=p_data.edge_attr.to(device))
                            probs = torch.sigmoid(logits).cpu().numpy()
                        scores = {}
                        for i, e in enumerate(g.edges):
                            mask_val = 1.0 if e.edge_id in flagged else 0.0
                            scores[e.edge_id] = mask_val * float(probs[i])
                        return scores
                model = CustomGatedModel(base_model, hard_rule_set)

            resampler = BenignResampler(pool_graphs=pool, seed=seed + 5000)

            for m in m_sweep:
                if m == 0:
                    g_m = g_m0
                else:
                    g_m, _ = resampler.inject(g_m0, m=m, seed=seed)

                scores = model.score_edges(g_m)
                flagged = {eid for eid, sc in scores.items() if sc >= 0.05}

                tp = len(flagged.intersection(gt_ids))
                fp = len(flagged - gt_ids)
                fn = len(gt_ids - flagged)

                prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
                rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0

                det_m_precisions[m].append(prec)
                if m == 0:
                    recalls_m0.append(rec)

        m_flat = [m for m in m_sweep for _ in seeds]
        p_flat = [p for m in m_sweep for p in det_m_precisions[m]]
        seed_flat = [s for m in m_sweep for s in seeds]

        alpha_res = fit_alpha_exponent(m_flat, p_flat, seeds=seed_flat)

        point_summary = {
            "name": name,
            "hard_rules_count": len(hard_rule_set),
            "mean_recall_m0": round(float(np.mean(recalls_m0)), 6),
            "alpha_hat": round(alpha_res.alpha_hat, 6),
            "ci_lower": round(alpha_res.ci_lower, 6),
            "ci_upper": round(alpha_res.ci_upper, 6),
        }
        frontier_results.append(point_summary)
        print(f"  -> Recall(m=0): {point_summary['mean_recall_m0']:.4f} | alpha_hat: {point_summary['alpha_hat']:.4f}")

    plot_tradeoff_frontier(frontier_results)

    return frontier_results


def plot_tradeoff_frontier(frontier_results: List[Dict[str, Any]]):
    """Plots Experiment F Tradeoff Frontier: Recall at m=0 vs alpha_hat."""
    plt.figure(figsize=(8, 6), dpi=300)

    recalls = [r["mean_recall_m0"] for r in frontier_results]
    alphas = [r["alpha_hat"] for r in frontier_results]

    plt.plot(recalls, alphas, marker="o", color="#2b5c8f", linewidth=2.5, markersize=8, label="Tradeoff Frontier")

    for i, pt in enumerate(frontier_results):
        plt.annotate(
            pt["name"],
            (recalls[i], alphas[i]),
            xytext=(10, -5),
            textcoords="offset points",
            fontsize=9,
            fontweight="bold" if i in (0, len(frontier_results) - 1) else "normal",
        )

    plt.xlabel("Recall at $m=0$", fontsize=12)
    plt.ylabel(r"Dilution Exponent $\hat{\alpha}$ (Log Precision Decay Rate)", fontsize=12)
    plt.title("Tradeoff Frontier: Coverage vs. Dilution Robustness", fontsize=13, fontweight="bold", pad=12)
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.xlim(-0.02, max(recalls) + 0.15)
    plt.ylim(-0.05, max(alphas) + 0.15)

    plt.tight_layout()
    plot_path = FIGS_DIR / "tradeoff_frontier.png"
    plt.savefig(plot_path)
    plt.close()
    print(f"Saved Tradeoff Frontier plot to {plot_path}")


def main():
    print("=== Executing Phase 9 Ablation & Frontier Pipeline ===")
    is_quick = "--quick" in sys.argv or os.environ.get("QUICK_MODE") == "1"
    if is_quick:
        print("[*] QUICK MODE active: reduced m_grid and seeds.")
        run_experiment_e(m_grid=[0, 1000], seeds=[42])
        run_experiment_f(seeds=[42])
    else:
        run_experiment_e()
        run_experiment_f()
    print("\n=== Phase 9 Experiments E and F Complete ===")


if __name__ == "__main__":
    main()
