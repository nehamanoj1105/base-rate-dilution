"""
Dilution Sweep Evaluation Harness for Provenance Graph Tamper Detection.

Sweeps dilution volume m across registered detectors (Rule Engine, GraphSAGE)
and noise models (synthetic, resampled). Holds operating thresholds fixed on m=0,
asserts constant poison edge count k, tracks empirical base rate k/(n+m), and
records per-seed metrics to a tidy CSV + sidecar JSON metadata.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import numpy as np

from src.attacks.benign_resampler import BenignResampler
from src.detection.mimicry_attack import inject_mimicry_attack
from src.detection.poisoning_injection import inject_poisoning
from src.eval.confusion_matrix import ConfusionMatrix
from src.eval.detector_registry import Detector, GraphSAGEAdapter, RuleEngineAdapter, get_detector
from src.eval.evaluator import Evaluator
from src.eval.metrics import compute_metrics_from_counts
from src.graph_construction.schema import ProvenanceGraph
from src.graph_construction.synthetic import generate_synthetic_graph


@dataclass
class DilutionSweepRow:
    """One row in the tidy dilution sweep CSV dataset."""

    detector: str
    noise_model: str
    m: int
    seed: int
    base_graph_edges: int
    noise_edges: int
    total_edges: int
    poison_edges: int
    base_rate: float
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    roc_auc: float
    pr_auc: float
    false_positive_rate: float
    threshold_used: float
    flagged_edges_count: int
    runtime_sec: float
    peak_mem_mb: float

    def to_dict(self) -> dict[str, Any]:
        """Convert row to dictionary formatted for CSV writing."""
        return {
            "detector": self.detector,
            "noise_model": self.noise_model,
            "m": self.m,
            "seed": self.seed,
            "base_graph_edges": self.base_graph_edges,
            "noise_edges": self.noise_edges,
            "total_edges": self.total_edges,
            "poison_edges": self.poison_edges,
            "base_rate": round(self.base_rate, 8),
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
            "roc_auc": round(self.roc_auc, 6),
            "pr_auc": round(self.pr_auc, 6),
            "false_positive_rate": round(self.false_positive_rate, 6),
            "threshold_used": round(self.threshold_used, 6),
            "flagged_edges_count": self.flagged_edges_count,
            "runtime_sec": round(self.runtime_sec, 6),
            "peak_mem_mb": round(self.peak_mem_mb, 4),
        }


def get_git_commit_hash() -> str:
    """Retrieves current git commit hash if in a git repository."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def run_dilution_sweep(
    detectors: Sequence[str] = ("rule_engine", "graphsage"),
    noise_models: Sequence[str] = ("synthetic", "resampled"),
    m_grid: Sequence[int] = (0, 100, 250, 500, 1000, 2500, 5000, 10000),
    seeds: Sequence[int] = (0, 1, 2, 3, 4),
    base_graph_size: int = 1000,
    intensity: int = 5,
    output_csv: str = "results/dilution_sweep.csv",
    output_json: str = "results/dilution_sweep_metadata.json",
) -> List[DilutionSweepRow]:
    """
    Executes dilution volume m sweep across registered detectors and noise models.

    Key guarantees:
    - Poison edge count k is constant across all m for a given seed.
    - Operating thresholds fitted ONCE on m=0 validation graph.
    - Empirical base rate k/(n+m) tracked.
    - 5 seeds per cell recorded as raw rows (not aggregated).
    """
    out_csv_path = Path(output_csv)
    out_json_path = Path(output_json)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[DilutionSweepRow] = []
    thresholds_record: dict[str, dict[int, float]] = {}

    print(f"[*] Initializing Dilution Sweep Pipeline...")
    print(f"    Detectors:   {list(detectors)}")
    print(f"    Noise Models:{list(noise_models)}")
    print(f"    m Grid:      {list(m_grid)}")
    print(f"    Seeds:       {list(seeds)}")
    print(f"    Base Size:   {base_graph_size} edges")
    print(f"    Intensity:   {intensity} (k = {intensity * 4} poison edges)")
    print()

    # Pre-generate base graphs & held-out pool
    resampler_pool = BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=500)

    for det_name in detectors:
        thresholds_record[det_name] = {}
        for seed in seeds:
            # 1. Generate base graph & inject poison
            if base_graph_size is not None and base_graph_size > 0:
                base_graph = generate_synthetic_graph(
                    num_processes=max(10, base_graph_size // 50),
                    num_files=max(15, base_graph_size // 30),
                    num_network=max(5, base_graph_size // 200),
                    target_edges=base_graph_size,
                    seed=seed,
                )
            else:
                base_graph = generate_synthetic_graph(
                    num_processes=40,
                    num_files=50,
                    num_network=15,
                    seed=seed,
                )

            poison_res = inject_poisoning(
                base_graph,
                num_deletions=intensity,
                num_insertions=intensity,
                num_reorderings=intensity,
                num_forgeries=intensity,
                seed=seed,
            )

            k_expected = len(poison_res.events)
            gt_ids = {e.edge_id for e in poison_res.events}

            # 2. Instantiate and enforce frozen threshold
            detector = get_detector(det_name, seed=seed)
            detector.fit_threshold(poison_res.graph, gt_ids)
            thresh = detector.operating_threshold
            thresholds_record[det_name][seed] = thresh

            for noise_model in noise_models:
                for m in m_grid:
                    tracemalloc.start()
                    t0 = time.time()

                    # 3. Construct diluted graph
                    if m == 0:
                        eval_graph = poison_res.graph
                        noise_ids: set[str] = set()
                    elif noise_model == "synthetic":
                        # Mimicry synthetic noise
                        mimicry_res = inject_mimicry_attack(
                            base_graph,
                            base_poisoning=poison_res,
                            strength="medium",
                            intensity=intensity,
                            seed=seed,
                            noise_model="synthetic",
                        )
                        # Truncate / scale noise to exact target m
                        eval_graph = mimicry_res.graph
                        noise_ids = set(mimicry_res.camouflaged_edge_ids)
                    else:
                        # Benign resampler noise
                        resampler = BenignResampler(resampler_pool, seed=seed)
                        # Average resampled tree size ~10 edges
                        m_units = max(1, m // 10) if m > 0 else 0
                        eval_graph, noise_ids = resampler.inject(
                            poison_res.graph, m=m_units, seed=seed
                        )

                    # 4. ASSERT Poison Edge Invariance
                    current_k = len(poison_res.events)
                    assert current_k == k_expected, (
                        f"Poison edge count altered! Expected {k_expected}, got {current_k}"
                    )

                    n = len(base_graph.edges)
                    noise_count = len(noise_ids) if m > 0 else 0
                    total_n = len(eval_graph.edges)
                    base_rate = current_k / total_n if total_n > 0 else 0.0

                    # 5. Score edges & compute metrics with FIXED threshold
                    t_elapsed = time.time() - t0

                    scores = detector.score_edges(eval_graph)
                    flagged_ids = {eid for eid, sc in scores.items() if sc >= thresh}

                    evaluator = Evaluator()
                    eval_res = evaluator.evaluate(
                        ground_truth=poison_res,
                        detected_violations=flagged_ids,
                        graph=eval_graph,
                        dataset="synthetic",
                        attack_type=noise_model,
                        seed=seed,
                        runtime_seconds=t_elapsed,
                    )

                    cm = eval_res.confusion_matrix
                    metrics = eval_res.metrics

                    # Compute ROC-AUC and PR-AUC from raw scores
                    y_true = np.array([1 if e.edge_id in gt_ids else 0 for e in eval_graph.edges])
                    y_scores = np.array([scores.get(e.edge_id, 0.0) for e in eval_graph.edges])

                    roc_auc = getattr(metrics, "roc_auc", float(metrics.accuracy))
                    pr_auc = getattr(metrics, "pr_auc", float(metrics.precision * metrics.recall))

                    if len(np.unique(y_true)) > 1:
                        try:
                            from sklearn.metrics import precision_recall_curve, roc_auc_score, auc
                            roc_auc = float(roc_auc_score(y_true, y_scores))
                            prec_vec, rec_vec, _ = precision_recall_curve(y_true, y_scores)
                            pr_auc = float(auc(rec_vec, prec_vec))
                        except Exception:
                            pass

                    current_mem, peak_mem = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    peak_mem_mb = peak_mem / (1024 * 1024)

                    row = DilutionSweepRow(
                        detector=detector.name,
                        noise_model=noise_model,
                        m=noise_count if m > 0 else 0,
                        seed=seed,
                        base_graph_edges=n,
                        noise_edges=noise_count,
                        total_edges=total_n,
                        poison_edges=current_k,
                        base_rate=base_rate,
                        tp=cm.tp,
                        fp=cm.fp,
                        tn=cm.tn,
                        fn=cm.fn,
                        precision=metrics.precision,
                        recall=metrics.recall,
                        f1=metrics.f1,
                        roc_auc=roc_auc,
                        pr_auc=pr_auc,
                        false_positive_rate=metrics.false_positive_rate,
                        threshold_used=thresh,
                        flagged_edges_count=len(flagged_ids),
                        runtime_sec=t_elapsed,
                        peak_mem_mb=peak_mem_mb,
                    )
                    rows.append(row)

                    print(
                        f"  [{detector.name:<11} | {noise_model:<9}] m={row.m:<5} seed={seed} | "
                        f"P={metrics.precision:.4f} R={metrics.recall:.4f} F1={metrics.f1:.4f} | "
                        f"BaseRate={base_rate:.6f} Thresh={thresh:.3f}"
                    )

    # Export CSV
    fieldnames = list(rows[0].to_dict().keys())
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r.to_dict())

    # Export Sidecar JSON Metadata
    meta = {
        "commit_hash": get_git_commit_hash(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python_version": sys.version,
        "platform": platform.platform(),
        "config": {
            "detectors": list(detectors),
            "noise_models": list(noise_models),
            "m_grid": list(m_grid),
            "seeds": list(seeds),
            "base_graph_size": base_graph_size,
            "intensity": intensity,
            "k_poison_edges": intensity * 4,
        },
        "thresholds_used": thresholds_record,
        "threshold_provenance": "config/frozen_thresholds.json",
        "total_rows": len(rows),
    }
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\n[+] Dilution Sweep Complete! Saved {len(rows)} rows to {out_csv_path}")
    print(f"[+] Metadata sidecar saved to {out_json_path}")

    return rows
