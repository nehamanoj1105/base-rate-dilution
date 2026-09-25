"""
AUC Invariance Audit & Score Locality Test for Provenance Graph Tamper Detection.

Scientific Context:
    ROC-AUC invariance under dilution is often cited as proof of detector robustness.
    However, ROC-AUC invariance is NOT a property of the base-rate dilution threat model alone.
    It critically requires SCORE LOCALITY — the property that adding background edges does not
    alter the relative ranking of pre-existing edges.

    This module provides:
      1. Tie Structure & Dual AUC Audit: Recomputes ROC-AUC over ALL edges, auditing score ties
         and reporting BOTH Optimistic AUC (ties sorted TP before FP) and Pessimistic AUC
         (ties sorted FP before TP).
      2. Score Locality Test: Measures Spearman rank correlation rho(S_0, S_m) of base edge
         scores between m=0 and each dilution volume m.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Set, Tuple, Union

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from src.attacks.benign_resampler import BenignResampler
from src.detection.mimicry_attack import inject_mimicry_attack
from src.detection.poisoning_injection import inject_poisoning
from src.eval.detector_registry import Detector
from src.graph_construction.schema import ProvenanceGraph
from src.graph_construction.synthetic import generate_synthetic_graph


@dataclass
class TieStructureResult:
    """Audit of tie structure and dual ROC-AUC estimates."""

    total_edges: int
    num_positives: int
    num_negatives: int
    modal_score: float
    modal_score_count: int
    modal_score_fraction: float
    largest_tied_block_size: int
    auc_standard: float
    auc_optimistic: float
    auc_pessimistic: float
    auc_tie_gap: float
    is_all_edges: bool = True

    def to_dict(self) -> Dict[str, Union[float, int, bool]]:
        """Converts result to dictionary."""
        return {
            "total_edges": self.total_edges,
            "num_positives": self.num_positives,
            "num_negatives": self.num_negatives,
            "modal_score": round(float(self.modal_score), 6),
            "modal_score_count": self.modal_score_count,
            "modal_score_fraction": round(float(self.modal_score_fraction), 6),
            "largest_tied_block_size": self.largest_tied_block_size,
            "auc_standard": round(float(self.auc_standard), 6),
            "auc_optimistic": round(float(self.auc_optimistic), 6),
            "auc_pessimistic": round(float(self.auc_pessimistic), 6),
            "auc_tie_gap": round(float(self.auc_tie_gap), 6),
            "is_all_edges": self.is_all_edges,
        }


def compute_optimistic_pessimistic_auc(
    y_true: np.ndarray, y_score: np.ndarray
) -> Tuple[float, float]:
    """
    Computes Optimistic and Pessimistic ROC-AUC under explicit tie resolution.

    - Optimistic: Positive edges (TPs) sorted before Negative edges (FPs) for tied scores.
    - Pessimistic: Negative edges (FPs) sorted before Positive edges (TPs) for tied scores.

    Returns:
        Tuple of (auc_optimistic, auc_pessimistic).
    """
    n_pos = np.sum(y_true == 1)
    n_neg = np.sum(y_true == 0)

    if n_pos == 0 or n_neg == 0:
        return 0.5, 0.5

    # Optimistic: sort by (-score, -label)
    opt_idx = np.lexsort((-y_true, -y_score))
    y_true_opt = y_true[opt_idx]
    
    # Trapezoidal AUC calculation for optimistic ordering
    tps_opt = np.cumsum(y_true_opt == 1)
    fps_opt = np.cumsum(y_true_opt == 0)
    tpr_opt = np.concatenate(([0.0], tps_opt / float(n_pos)))
    fpr_opt = np.concatenate(([0.0], fps_opt / float(n_neg)))
    auc_optimistic = float(np.trapezoid(tpr_opt, fpr_opt))

    # Pessimistic: sort by (-score, label)
    pess_idx = np.lexsort((y_true, -y_score))
    y_true_pess = y_true[pess_idx]

    # Trapezoidal AUC calculation for pessimistic ordering
    tps_pess = np.cumsum(y_true_pess == 1)
    fps_pess = np.cumsum(y_true_pess == 0)
    tpr_pess = np.concatenate(([0.0], tps_pess / float(n_pos)))
    fpr_pess = np.concatenate(([0.0], fps_pess / float(n_neg)))
    auc_pessimistic = float(np.trapezoid(tpr_pess, fpr_pess))

    return auc_optimistic, auc_pessimistic


def audit_auc_and_ties(
    scores: Dict[str, float], ground_truth_ids: Set[str]
) -> TieStructureResult:
    """
    Audits tie structure and computes standard, optimistic, and pessimistic ROC-AUC
    over ALL edges in the graph.

    Args:
        scores: Dict mapping edge_id to anomaly score float.
        ground_truth_ids: Set of positive ground truth edge_ids.

    Returns:
        TieStructureResult dataclass containing full audit details.
    """
    edge_ids = list(scores.keys())
    total_edges = len(edge_ids)

    if total_edges == 0:
        return TieStructureResult(
            total_edges=0,
            num_positives=0,
            num_negatives=0,
            modal_score=0.0,
            modal_score_count=0,
            modal_score_fraction=0.0,
            largest_tied_block_size=0,
            auc_standard=0.5,
            auc_optimistic=0.5,
            auc_pessimistic=0.5,
            auc_tie_gap=0.0,
            is_all_edges=True,
        )

    y_score = np.array([scores[eid] for eid in edge_ids], dtype=float)
    y_true = np.array([1 if eid in ground_truth_ids else 0 for eid in edge_ids], dtype=int)

    num_pos = int(np.sum(y_true == 1))
    num_neg = int(np.sum(y_true == 0))

    # Tie analysis
    unique_scores, counts = np.unique(y_score, return_counts=True)
    max_count_idx = int(np.argmax(counts))
    modal_score = float(unique_scores[max_count_idx])
    modal_score_count = int(counts[max_count_idx])
    modal_score_fraction = float(modal_score_count / total_edges)
    largest_tied_block_size = int(np.max(counts))

    # Standard AUC
    if num_pos > 0 and num_neg > 0:
        try:
            auc_std = float(roc_auc_score(y_true, y_score))
        except ValueError:
            auc_std = 0.5
        auc_opt, auc_pess = compute_optimistic_pessimistic_auc(y_true, y_score)
    else:
        auc_std, auc_opt, auc_pess = 0.5, 0.5, 0.5

    return TieStructureResult(
        total_edges=total_edges,
        num_positives=num_pos,
        num_negatives=num_neg,
        modal_score=modal_score,
        modal_score_count=modal_score_count,
        modal_score_fraction=modal_score_fraction,
        largest_tied_block_size=largest_tied_block_size,
        auc_standard=auc_std,
        auc_optimistic=auc_opt,
        auc_pessimistic=auc_pess,
        auc_tie_gap=auc_opt - auc_pess,
        is_all_edges=True,
    )


def measure_score_locality(
    detector: Detector,
    m_grid: Sequence[int],
    noise_model: str = "resampled",
    seed: int = 42,
    base_graph_size: int = 1000,
    poison_events: int = 20,
    pool: Optional[List[ProvenanceGraph]] = None,
) -> Dict[int, float]:
    """
    Measures Spearman rank correlation rho(S_0, S_m) for scores of m=0 edges across m.

    Score locality test:
      - For local per-edge scoring rules (Rule Engine), rho = 1.0 exactly.
      - For GNNs with message passing (GraphSAGE), rho < 1.0 due to neighborhood expansion.

    Args:
        detector: Detector instance (RuleEngineAdapter or GraphSAGEAdapter).
        m_grid: Sequence of dilution volumes m.
        noise_model: "synthetic" or "resampled".
        seed: Random seed.
        base_graph_size: Size of base synthetic graph.
        poison_events: Number of poison events.
        pool: Optional pre-constructed benign pool graphs.

    Returns:
        Dict mapping m -> Spearman rank correlation rho float.
    """
    if pool is None:
        pool = BenignResampler.create_default_pool(num_graphs=2, edges_per_graph=max(m_grid) + 500)
    resampler = BenignResampler(pool_graphs=pool, seed=seed)

    # Generate m=0 baseline graph
    base_graph = generate_synthetic_graph(target_edges=base_graph_size, seed=seed)
    n_each = max(1, poison_events // 4)
    poison_res = inject_poisoning(
        base_graph,
        num_deletions=n_each,
        num_insertions=n_each,
        num_reorderings=n_each,
        num_forgeries=n_each,
        seed=seed,
    )
    g_m0 = poison_res.graph
    gt_ids = set(poison_res.edge_labels().keys())

    # Fit detector threshold on m=0
    detector.fit_threshold(g_m0, gt_ids)

    # Baseline scores for all edges at m=0
    s0_dict = detector.score_edges(g_m0)
    base_edge_ids = [e.edge_id for e in g_m0.edges]
    s0_vec = np.array([s0_dict.get(eid, 0.0) for eid in base_edge_ids], dtype=float)

    results: Dict[int, float] = {}
    current_g = g_m0
    current_m = 0

    for m in m_grid:
        if m == 0:
            results[0] = 1.0
            continue

        print(f"    Evaluating m={m}...", flush=True)

        if noise_model == "synthetic":
            g_m = inject_mimicry_attack(g_m0, num_fake_edges=m, seed=seed)
        else:
            delta_m = m - current_m
            current_g, _ = resampler.inject(current_g, m=delta_m, seed=seed + current_m)
            current_m = m
            g_m = current_g

        sm_dict = detector.score_edges(g_m)
        sm_vec = np.array([sm_dict.get(eid, 0.0) for eid in base_edge_ids], dtype=float)

        # Compute Spearman rank correlation
        if len(np.unique(s0_vec)) == 1 and len(np.unique(sm_vec)) == 1:
            rho = 1.0 if np.array_equal(s0_vec, sm_vec) else 0.0
        else:
            res = spearmanr(s0_vec, sm_vec)
            rho = float(res.statistic) if not np.isnan(res.statistic) else 1.0

        results[int(m)] = round(rho, 6)
        print(f"    m={m} -> rho={results[int(m)]}", flush=True)

    return results
