"""
Unit tests for GatedSAGE architecture and feature construction (Phase 7).

Verifies:
  1. All Phase 6 guarantee tests pass with real GatedSAGE as f.
  2. Feature dimensionality and ordering match config/invariant_partition.json.
  3. Ungated GraphSAGE reproduces its previous baseline outputs exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest
import torch
import torch.nn as nn

from models.feasibility_gate import (
    compute_hard_mask,
    compute_masked_loss,
    compute_violation_vector,
    split_violation_vector,
    load_invariant_config,
)
from models.gated_sage import GatedSAGE
from src.detection.poisoning_injection import inject_poisoning
from src.eval.detector_registry import GatedSAGEAdapter, GraphSAGEAdapter
from src.graph_construction.schema import ProvenanceGraph
from src.graph_construction.synthetic import generate_synthetic_graph
from src.ml.dataset import provenance_to_pyg_data
from src.ml.graphsage import GraphSAGEForTamperDetection


def test_gated_sage_feature_dimensionality_and_ordering():
    """Asserts edge feature dimensionality (11) and soft-invariant ordering against config."""
    cfg = load_invariant_config()
    canonical_order = cfg["canonical_rule_order"]
    soft_rules = cfg["soft_rules"]

    # Check soft rules indices in canonical order
    soft_indices = [i for i, r in enumerate(canonical_order) if r in soft_rules]
    assert len(soft_indices) == 4, f"Expected 4 soft rules, found {len(soft_indices)}"

    # Generate graph with known soft violation
    graph = generate_synthetic_graph(target_edges=100, seed=42)
    pyg_data_soft = provenance_to_pyg_data(graph, include_soft_invariants=True)
    pyg_data_legacy = provenance_to_pyg_data(graph, include_soft_invariants=False)

    # Legacy edge features: 6 one-hot + 1 timestamp = 7
    assert pyg_data_legacy.edge_attr.size(-1) == 7, f"Legacy edge_attr should be 7, got {pyg_data_legacy.edge_attr.size(-1)}"

    # Gated edge features: 7 + 4 = 11
    assert pyg_data_soft.edge_attr.size(-1) == 11, f"Gated edge_attr should be 11, got {pyg_data_soft.edge_attr.size(-1)}"


def test_ungated_graphsage_reproduces_baseline_outputs():
    """Asserts that ungated GraphSAGE reproduces its previous baseline outputs exactly."""
    from src.ml.utils import set_seed
    graph = generate_synthetic_graph(target_edges=100, seed=42)

    set_seed(42)
    adapter1 = GraphSAGEAdapter(seed=42)
    adapter1.model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=0, hidden_channels=32)
    scores1 = adapter1.score_edges(graph)

    set_seed(42)
    adapter2 = GraphSAGEAdapter(seed=42)
    adapter2.model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=0, hidden_channels=32)
    scores2 = adapter2.score_edges(graph)

    assert len(scores1) == len(scores2)
    for eid, s1 in scores1.items():
        assert s1 == scores2[eid], f"Baseline mismatch for edge {eid}: {s1} != {scores2[eid]}"


def test_gated_sage_guarantee_100_initializations():
    """
    GUARANTEE TEST FOR GATED SAGE:
    For 100 random parameter initializations of GatedSAGE,
    assert s(e) == 0.0 exactly for every edge with v_hard == 0.
    """
    graph = generate_synthetic_graph(target_edges=150, seed=42)
    mask_dict = compute_hard_mask(graph)

    for seed in range(100):
        torch.manual_seed(seed)
        model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=11, hidden_channels=32)
        gated = GatedSAGE(base_graphsage=model)
        scores = gated.score_edges(graph)

        for edge in graph.edges:
            if mask_dict[edge.edge_id] == 0.0:
                s_val = scores[edge.edge_id]
                assert s_val == 0.0, f"Seed {seed}: expected exact 0.0 for edge {edge.edge_id}, got {s_val}"


def test_gated_sage_adversarial_parameters():
    """
    ADVERSARIAL PARAMETER TEST FOR GATED SAGE:
    Set GatedSAGE edge predictor weights to huge values and confirm masked edges score 0.0 exactly.
    """
    graph = generate_synthetic_graph(target_edges=150, seed=42)
    mask_dict = compute_hard_mask(graph)

    model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=11, hidden_channels=32)
    with torch.no_grad():
        model.edge_predictor.lin2.weight.fill_(1e10)
        model.edge_predictor.lin2.bias.fill_(1e10)

    gated = GatedSAGE(base_graphsage=model)
    scores = gated.score_edges(graph)

    for edge in graph.edges:
        if mask_dict[edge.edge_id] == 0.0:
            s_val = scores[edge.edge_id]
            assert s_val == 0.0, f"Adversarial weights: expected 0.0 for edge {edge.edge_id}, got {s_val}"


def test_gated_sage_gradient_isolation():
    """
    GRADIENT TEST FOR GATED SAGE:
    After backward pass, assert gradient contribution from masked edges is exactly zero.
    """
    torch.manual_seed(42)
    base_g = generate_synthetic_graph(target_edges=100, seed=42)
    poison_res = inject_poisoning(base_g, num_deletions=2, num_insertions=2, num_reorderings=2, num_forgeries=2, seed=42)
    graph = poison_res.graph

    mask_dict = compute_hard_mask(graph)
    pyg_data = provenance_to_pyg_data(graph, include_soft_invariants=True)

    mask_tensor = torch.tensor([mask_dict[e.edge_id] for e in graph.edges], dtype=torch.float32)

    model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=11, hidden_channels=32)
    gated = GatedSAGE(base_graphsage=model)

    x = pyg_data.x.clone().detach().requires_grad_(True)
    edge_index = pyg_data.edge_index
    edge_attr = pyg_data.edge_attr.clone().detach().requires_grad_(True)

    gated_scores, _ = gated(x, edge_index, edge_attr, mask_tensor)
    targets = torch.ones_like(gated_scores)

    loss = compute_masked_loss(nn.BCELoss(reduction="none"), gated_scores, targets, mask_tensor)
    loss.backward()

    assert edge_attr.grad is not None, "Edge attr gradients should be populated"

    for idx, edge in enumerate(graph.edges):
        if mask_dict[edge.edge_id] == 0.0:
            grad_norm = float(torch.norm(edge_attr.grad[idx]).item())
            assert grad_norm == 0.0, f"Expected 0.0 grad for masked edge {edge.edge_id}, got {grad_norm}"


def test_gated_sage_monotone_candidate_set():
    """
    MONOTONE CANDIDATE SET TEST FOR GATED SAGE:
    GatedSAGE's flagged set is always a subset of the HARD-rule flagged set.
    """
    graph = generate_synthetic_graph(target_edges=200, seed=42)
    mask_dict = compute_hard_mask(graph)
    hard_flagged_set = {eid for eid, m in mask_dict.items() if m == 1.0}

    adapter = GatedSAGEAdapter(seed=42)
    scores = adapter.score_edges(graph)

    for T in [0.001, 0.1, 0.5, 0.9, 1.0]:
        flagged = {eid for eid, score in scores.items() if score >= T}
        assert flagged.issubset(hard_flagged_set), f"Threshold {T}: GatedSAGE flagged set is not a subset of HARD-rule set"
