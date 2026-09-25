"""
Canonical evaluation fixture for all dilution, alpha, and AUC audit consumers.

This module is the single source of truth for the synthetic audit graph,
poisoning injection, positive labels, detector calibration, dilution noise,
and detector outputs.  The alpha and AUC consumers must call these helpers
rather than reconstructing graphs independently.

Positive labels are the non-deletion poisoning events.  Deletion events are
attacks but are not edges in the evaluated graph and therefore cannot be
reported as detector TPs.  This matches the historical alpha audit's
k=4*intensity positive-edge convention and makes the confusion-matrix
universe explicit.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np
from scipy.stats import spearmanr

from src.attacks.benign_resampler import BenignResampler
from src.detection.mimicry_attack import inject_mimicry_attack
from src.detection.poisoning_injection import PoisoningResult, inject_poisoning
from src.eval.detector_registry import Detector, get_detector
from src.graph_construction.schema import ProvenanceGraph
from src.graph_construction.synthetic import generate_synthetic_graph
from src.ml.utils import set_seed


CANONICAL_TARGET_EDGES = 600
CANONICAL_INTENSITY = 5
CANONICAL_SEEDS = (0, 1, 2, 3, 4)
CANONICAL_M_GRID = (0, 1000, 2500, 5000, 10000, 25000, 50000, 100000)


@dataclass(frozen=True)
class CanonicalFixture:
    seed: int
    base_graph: ProvenanceGraph
    poisoning: PoisoningResult
    ground_truth_ids: Set[str]

    @property
    def graph(self) -> ProvenanceGraph:
        return self.poisoning.graph

    @property
    def deleted_edge_ids(self) -> Set[str]:
        return {
            event.edge_id
            for event in self.poisoning.events
            if event.poisoning_type.value == "deletion"
        }


@dataclass(frozen=True)
class CanonicalDetectorState:
    detector_key: str
    detector: Detector
    fixture: CanonicalFixture


def build_canonical_fixture(
    seed: int,
    target_edges: int = CANONICAL_TARGET_EDGES,
    intensity: int = CANONICAL_INTENSITY,
) -> CanonicalFixture:
    """Build the one canonical graph and positive-label set for ``seed``."""
    set_seed(seed)
    base_graph = generate_synthetic_graph(
        target_edges=target_edges,
        seed=seed,
    )
    poisoning = inject_poisoning(
        base_graph,
        num_deletions=intensity,
        num_insertions=intensity,
        num_reorderings=intensity,
        num_forgeries=intensity,
        seed=seed,
    )
    positive_ids = {
        event.edge_id
        for event in poisoning.events
        if event.poisoning_type.value != "deletion"
    }
    return CanonicalFixture(
        seed=seed,
        base_graph=base_graph,
        poisoning=poisoning,
        ground_truth_ids=positive_ids,
    )


def get_canonical_eval_fixture(
    seed: int,
    target_edges: int = CANONICAL_TARGET_EDGES,
    intensity: int = CANONICAL_INTENSITY,
) -> Tuple[ProvenanceGraph, PoisoningResult, Set[str]]:
    """Backward-compatible tuple facade for the canonical fixture."""
    fixture = build_canonical_fixture(seed, target_edges, intensity)
    return fixture.base_graph, fixture.poisoning, fixture.ground_truth_ids


def build_diluted_graph(
    fixture: CanonicalFixture,
    m: int,
    noise_model: str = "resampled",
    seed: int | None = None,
    pool: Sequence[ProvenanceGraph] | None = None,
) -> Tuple[ProvenanceGraph, Set[str]]:
    """Return one canonical dilution graph and the IDs of added noise edges."""
    if m <= 0:
        return fixture.graph, set()
    if noise_model == "resampled":
        if pool is None:
            pool = BenignResampler.create_default_pool(
                num_graphs=10, edges_per_graph=2000
            )
        # A subgraph is the resampler's unit of m.  The historical AUC audit
        # used this conversion; retaining it keeps experiment semantics stable.
        units = max(1, m // 24)
        resampler = BenignResampler(pool_graphs=list(pool), seed=seed)
        return resampler.inject(fixture.graph, m=units, seed=seed)
    if noise_model == "synthetic":
        result = inject_mimicry_attack(
            fixture.graph,
            base_poisoning=fixture.poisoning,
            strength="medium",
            intensity=CANONICAL_INTENSITY,
            seed=seed,
            noise_model="synthetic",
        )
        return result.graph, set(result.camouflaged_edge_ids)
    raise ValueError(f"unknown noise model: {noise_model}")


def calibrate_canonical_detector(
    detector_key: str,
    fixture: CanonicalFixture,
    hidden_channels: int = 32,
    epochs: int = 25,
) -> CanonicalDetectorState:
    """Fit one detector once on the canonical m=0 graph and positive labels."""
    detector = get_detector(
        detector_key,
        seed=fixture.seed,
        hidden_channels=hidden_channels,
        epochs=epochs,
    )
    detector.fit_threshold(fixture.graph, fixture.ground_truth_ids)
    return CanonicalDetectorState(detector_key, detector, fixture)


def get_calibrated_detector(
    det_key: str,
    seed: int,
    val_graph: ProvenanceGraph,
    val_gt_ids: Set[str],
    hidden_channels: int = 32,
    epochs: int = 25,
) -> Detector:
    """Backward-compatible calibration facade used by older callers."""
    fixture = build_canonical_fixture(seed)
    detector = get_detector(
        det_key,
        seed=seed,
        hidden_channels=hidden_channels,
        epochs=epochs,
    )
    detector.fit_threshold(val_graph, val_gt_ids)
    return detector


def score_and_label(
    state: CanonicalDetectorState,
    graph: ProvenanceGraph,
    positive_ids: Set[str],
) -> Dict[str, object]:
    """Score one graph and compute the shared exact confusion counts."""
    scores = state.detector.score_edges(graph)
    edge_ids = [edge.edge_id for edge in graph.edges]
    threshold = state.detector.operating_threshold
    flagged = {eid for eid in edge_ids if scores.get(eid, 0.0) >= threshold}
    tp = len(flagged & positive_ids)
    fp = len(flagged - positive_ids)
    fn = len(positive_ids - flagged)
    tn = len(set(edge_ids) - positive_ids - flagged)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "scores": scores,
        "flagged_ids": flagged,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "total_edges": len(edge_ids),
        "positive_count": len(positive_ids),
        "threshold": threshold,
    }


def run_canonical_detector_sweep(
    detector_keys: Sequence[str],
    seeds: Sequence[int] = CANONICAL_SEEDS,
    m_grid: Sequence[int] = CANONICAL_M_GRID,
    noise_model: str = "resampled",
    hidden_channels: int = 32,
    epochs: int = 25,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[int, float]]]:
    """Run all detectors over one shared fixture sweep.

    The returned rows and locality curves are suitable for both alpha fitting
    and AUC auditing.  No consumer is permitted to rebuild a competing graph.
    """
    pool = BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=2000)
    rows: List[Dict[str, object]] = []
    locality: Dict[str, Dict[int, List[Tuple[int, float]]]] = {}

    for detector_key in detector_keys:
        locality[detector_key] = {}
        for seed in seeds:
            fixture = build_canonical_fixture(seed)
            state = calibrate_canonical_detector(
                detector_key, fixture, hidden_channels, epochs
            )
            baseline = score_and_label(state, fixture.graph, fixture.ground_truth_ids)
            base_scores = baseline["scores"]
            base_ids = [edge.edge_id for edge in fixture.graph.edges]
            for m in m_grid:
                graph, noise_ids = build_diluted_graph(
                    fixture, int(m), noise_model, seed=seed, pool=pool
                )
                result = score_and_label(state, graph, fixture.ground_truth_ids)
                row = {
                    "detector": state.detector.name,
                    "detector_key": detector_key,
                    "noise_model": noise_model,
                    "m": int(m),
                    "seed": seed,
                    "base_graph_edges": len(fixture.base_graph.edges),
                    "noise_edges": len(noise_ids),
                    "total_edges": result["total_edges"],
                    "poison_edges": len(fixture.ground_truth_ids),
                    "base_rate": len(fixture.ground_truth_ids) / max(1, result["total_edges"]),
                    "tp": result["tp"],
                    "fp": result["fp"],
                    "tn": result["tn"],
                    "fn": result["fn"],
                    "precision": result["precision"],
                    "recall": result["recall"],
                    "f1": result["f1"],
                    "roc_auc": 0.0,
                    "pr_auc": 0.0,
                    "auc_optimistic": 0.0,
                    "auc_pessimistic": 0.0,
                    "auc_tie_gap": 0.0,
                    "false_positive_rate": result["fp"] / max(1, result["total_edges"] - len(fixture.ground_truth_ids)),
                    "threshold_used": result["threshold"],
                    "flagged_edges_count": len(result["flagged_ids"]),
                    "runtime_sec": 0.0,
                    "peak_mem_mb": 0.0,
                    "poisoned_edge_ids": sorted(fixture.ground_truth_ids),
                    "prediction_ids": sorted(result["flagged_ids"]),
                }
                from sklearn.metrics import precision_recall_curve, roc_auc_score
                y_true = np.array([
                    1 if eid in fixture.ground_truth_ids else 0
                    for eid in [edge.edge_id for edge in graph.edges]
                ])
                y_score = np.array([
                    result["scores"].get(eid, 0.0)
                    for eid in [edge.edge_id for edge in graph.edges]
                ])
                if len(np.unique(y_true)) > 1:
                    row["roc_auc"] = float(roc_auc_score(y_true, y_score))
                    pr, rc, _ = precision_recall_curve(y_true, y_score)
                    row["pr_auc"] = float(np.trapezoid(rc, pr))
                    from src.eval.auc_invariance import audit_auc_and_ties
                    tie = audit_auc_and_ties(
                        result["scores"], fixture.ground_truth_ids, result["threshold"]
                    )
                    row["auc_optimistic"] = tie.auc_optimistic
                    row["auc_pessimistic"] = tie.auc_pessimistic
                    row["auc_tie_gap"] = tie.auc_tie_gap
                rows.append(row)

                base_vec = np.array([base_scores.get(eid, 0.0) for eid in base_ids])
                diluted_vec = np.array([
                    result["scores"].get(eid, 0.0) for eid in base_ids
                ])
                if len(np.unique(base_vec)) == 1 and len(np.unique(diluted_vec)) == 1:
                    rho = 1.0 if np.array_equal(base_vec, diluted_vec) else 0.0
                else:
                    stat = spearmanr(base_vec, diluted_vec).statistic
                    rho = 1.0 if np.isnan(stat) else float(stat)
                locality[detector_key].setdefault(int(m), []).append((seed, rho))

    locality_final = {
        key: {m: float(np.mean([r for _, r in vals])) for m, vals in levels.items()}
        for key, levels in locality.items()
    }
    return rows, locality_final


def fixture_provenance() -> Dict[str, object]:
    """Machine-readable provenance for validation and paper packaging."""
    return {
        "fixture_module": "src.eval.canonical_fixture",
        "builder": "build_canonical_fixture",
        "graph_generator": "src.graph_construction.synthetic.generate_synthetic_graph",
        "poisoning": "src.detection.poisoning_injection.inject_poisoning",
        "positive_label_rule": "non-deletion poisoning events only",
        "target_edges": CANONICAL_TARGET_EDGES,
        "intensity": CANONICAL_INTENSITY,
        "poison_positive_edges": 3 * CANONICAL_INTENSITY,
        "seeds": list(CANONICAL_SEEDS),
        "m_grid": list(CANONICAL_M_GRID),
        "detectors": [
            "rule_hard",
            "rule_all",
            "graphsage_baseline",
            "graphsage_inv_features",
            "gated_sage",
        ],
        "resampling_pool": "BenignResampler.create_default_pool(num_graphs=10, edges_per_graph=2000)",
        "resampling_conversion": "m_units=max(1, m//24)",
        "reason": "Alpha and AUC consumers must score the same graph, labels, detector state, and outputs.",
    }
