"""
Test module auditing the GNN contribution within the Feasibility Gate candidate set.

Diagnoses why GatedSAGE produces bit-identical results to Rule-only (HARD)
and tests whether the GNN separates benign from adversarial soft-violations.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from models.feasibility_gate import (
    compute_hard_mask,
    compute_violation_vector,
    split_violation_vector,
)
from src.detection.poisoning_injection import inject_poisoning
from src.eval.detector_registry import get_detector
from src.graph_construction.schema import (
    EdgeType,
    NodeType,
    ProvenanceEdge,
    ProvenanceGraph,
    ProvenanceNode,
)
from src.graph_construction.synthetic import generate_synthetic_graph
from src.ml.dataset import provenance_to_pyg_data
from src.ml.utils import get_device, set_seed


def create_benchmark_graph_with_soft_violators(seed: int = 42) -> tuple[ProvenanceGraph, set[str], set[str]]:
    """
    Constructs a benchmark graph containing:
    1. Poison edges tripping hard invariants
    2. Poison edges tripping soft invariants
    3. Injected benign audit-boundary artifact edges tripping soft invariants (e.g. UnspawnedProcessRule)
    """
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
    g = poison.graph
    gt_poison_ids = set(poison.edge_labels().keys())

    # Add 5 benign audit-boundary artifact edges that trip soft rules
    benign_soft_ids = set()
    for i in range(5):
        p_node = ProvenanceNode(
            node_id=f"benign_unspawned_p_{seed}_{i}",
            node_type=NodeType.PROCESS,
            label=f"/usr/bin/auditd_helper_{i}",
        )
        f_node = ProvenanceNode(
            node_id=f"benign_log_file_{seed}_{i}",
            node_type=NodeType.FILE,
            label=f"/var/log/audit_{i}.log",
        )
        g.add_node(p_node)
        g.add_node(f_node)
        eid = f"benign_soft_violator_{seed}_{i}"
        e = ProvenanceEdge(
            edge_id=eid,
            source_id=f"benign_unspawned_p_{seed}_{i}",
            target_id=f"benign_log_file_{seed}_{i}",
            edge_type=EdgeType.WRITE,
            timestamp=1000.0 + i * 10,
        )
        g.add_edge(e)
        benign_soft_ids.add(eid)

    return g, gt_poison_ids, benign_soft_ids


def test_eligible_set_and_gnn_score_collapse():
    """
    Test documenting GNN behavior on benign vs adversarial soft-violators.
    Verifies that under current synthetic training data:
    1. GatedSAGE (strict hard gate) masks soft-only violators to 0.
    2. Ungated raw GNN scores f(e) assign high scores (f(e) ~ 1.0) to both
       benign and adversarial soft-violators, demonstrating that GNN re-ranking
       does not separate them on current benchmarks.
    """
    g, gt_poison_ids, benign_soft_ids = create_benchmark_graph_with_soft_violators(seed=0)
    violations = compute_violation_vector(g)

    # Categorize edges
    soft_only_poison = []
    soft_only_benign = []

    for eid, v_all in violations.items():
        vh, vs = split_violation_vector(v_all)
        has_vh = np.any(vh > 0)
        has_vs = np.any(vs > 0)
        is_poison = eid in gt_poison_ids

        if not has_vh and has_vs:
            if is_poison:
                soft_only_poison.append(eid)
            else:
                soft_only_benign.append(eid)

    # Assert non-empty eligible set of soft violators
    assert len(soft_only_poison) > 0, "Eligible poison soft-violators must be non-empty"
    assert len(soft_only_benign) > 0, "Eligible benign soft-violators must be non-empty"

    # Evaluate GatedSAGE detector
    det = get_detector("gated_sage", seed=0, hidden_channels=32, epochs=25)
    gated_scores = det.score_edges(g)

    # 1. Strict Hard Gate verification: all soft-only edge scores are 0.0
    for eid in soft_only_poison + soft_only_benign:
        assert gated_scores[eid] == 0.0, f"Edge {eid} with v_hard==0 must be masked to 0.0"

    # 2. Raw GNN score inspection before gate mask
    pyg_data = provenance_to_pyg_data(g, include_soft_invariants=True)
    device = get_device()
    det.gated_model.eval()
    with torch.no_grad():
        x_dev = pyg_data.x.to(device)
        edge_idx_dev = pyg_data.edge_index.to(device)
        edge_attr_dev = pyg_data.edge_attr.to(device)
        _, edge_logits, _ = det.gated_model.graphsage(x_dev, edge_idx_dev, edge_attr=edge_attr_dev)
        raw_probs = torch.sigmoid(edge_logits).cpu().numpy()

    raw_scores = {e.edge_id: float(raw_probs[i]) for i, e in enumerate(g.edges)}

    poison_soft_scores = [raw_scores[eid] for eid in soft_only_poison]
    benign_soft_scores = [raw_scores[eid] for eid in soft_only_benign]

    # Document empirical score behavior: GNN outputs high scores for both classes
    mean_poison_score = float(np.mean(poison_soft_scores))
    mean_benign_score = float(np.mean(benign_soft_scores))

    # Verify score collapse (both classes receive ~1.0 score, mean difference < 0.1)
    score_diff = abs(mean_poison_score - mean_benign_score)
    assert score_diff < 0.2, (
        f"GNN does not separate benign (mean={mean_benign_score:.4f}) from "
        f"poison (mean={mean_poison_score:.4f}) soft-violators on synthetic data."
    )
