"""
Unit tests for split leakage audit, training reproducibility, and trained checkpoint guarantees (Phase 8).
"""

from __future__ import annotations

import os
from pathlib import Path
import numpy as np
import pytest
import torch

from models.feasibility_gate import compute_hard_mask
from models.gated_sage import GatedSAGE
from scripts.run_gated_training import train_single_seed_gated
from src.eval.leakage_audit import audit_leakage
from src.graph_construction.synthetic import generate_synthetic_graph
from src.ml.graphsage import GraphSAGEForTamperDetection
from src.ml.utils import set_seed


CHECKPOINT_DIR = Path("results/checkpoints")


def test_leakage_audit_passes():
    """Asserts that strict leakage audit passes cleanly with zero violations."""
    audit_res = audit_leakage()
    assert audit_res["all_checks_passed"] is True
    assert os.path.exists("results/leakage_audit.json")


def test_training_reproducibility():
    """Asserts that training is 100% reproducible given a fixed seed."""
    model1, thresh1, val1 = train_single_seed_gated(seed=42, epochs=5)
    model2, thresh2, val2 = train_single_seed_gated(seed=42, epochs=5)

    assert thresh1 == thresh2, f"Threshold mismatch: {thresh1} != {thresh2}"

    params1 = dict(model1.named_parameters())
    params2 = dict(model2.named_parameters())

    for name in params1:
        p1 = params1[name]
        p2 = params2[name]
        assert torch.equal(p1, p2), f"Parameter mismatch for layer {name}"


def test_guarantee_tests_pass_on_trained_checkpoints():
    """Asserts that mathematical guarantee tests (s(e) == 0.0) still pass on trained checkpoints."""
    # Ensure checkpoint 0 exists
    ckpt_path = CHECKPOINT_DIR / "gated_sage_seed_0.pt"
    if not ckpt_path.exists():
        model, thresh, _ = train_single_seed_gated(seed=0, epochs=5)
    else:
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        base_model = GraphSAGEForTamperDetection(in_channels=7, edge_attr_dim=11, hidden_channels=32)
        model = GatedSAGE(base_graphsage=base_model)
        model.load_state_dict(ckpt["model_state_dict"])

    graph = generate_synthetic_graph(target_edges=200, seed=42)
    mask_dict = compute_hard_mask(graph)
    scores = model.score_edges(graph)

    for edge in graph.edges:
        if mask_dict[edge.edge_id] == 0.0:
            s_val = scores[edge.edge_id]
            assert s_val == 0.0, f"Trained checkpoint: expected exact 0.0 for edge {edge.edge_id}, got {s_val}"
