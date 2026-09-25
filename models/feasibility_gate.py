"""
Hard Feasibility Gate for Provenance Graph Tamper Detection.

Scientific & Architectural Guarantee:
    A detector's precision under base-rate dilution is robust iff its flagged set has
    zero probability mass under the benign distribution (zero false positive rate).

    The Feasibility Gate enforces a HARD zero-FPR guarantee on all benign activity that
    satisfies the 11 HARD invariant set:
        s(e) = mask(e) * f(e)

    where mask(e) = 1.0 if edge e violates at least one HARD invariant, and 0.0 otherwise.

Architectural Constraints & Principles:
    1. Binary Mask (Not Learned): mask(e) is a hard binary scalar {0.0, 1.0}, computed as a
       plain constant OUTSIDE any autograd graph. Multiplication is the FINAL operation.
       No learned parameters appear downstream of the mask.
    2. Edge-Level Scoring Only: Score s(e) is edge-local. No graph-level or subgraph-level
       aggregate score is used.
    3. Message Passing Note: Message passing in GNN base models (e.g., GraphSAGE) MAY consume
       feasible (unmasked) edges without violating the zero-FPR guarantee on masked edges
       (because mask(e) * f(e) = 0.0 exactly regardless of message passing). However, message
       passing DOES break score locality for ranking under base-rate dilution.
    4. Training Loss Isolation: Training loss is restricted exclusively to unmasked edges
       (where mask(e) == 1.0) so gradients cannot propagate through zero-masked predictions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn

from src.detection.rule_engine import RuleEngine, default_rule_engine
from src.eval.evaluator import Evaluator
from src.graph_construction.schema import ProvenanceGraph


CONFIG_PATH = Path(__file__).parent.parent / "config" / "invariant_partition.json"


def load_invariant_config() -> Dict[str, List[str]]:
    """Loads canonical rule order, hard rules, and soft rules from config."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    # Default fallback if config file is missing
    return {
        "canonical_rule_order": [
            "DuplicateEdgeRule",
            "DuplicateEventRule",
            "SpawnConsistencyRule",
            "ExecutionConsistencyRule",
            "ReadWriteConsistencyRule",
            "NetworkConsistencyRule",
            "DeleteConsistencyRule",
            "SelfLoopRule",
            "MissingNodeRule",
            "TimestampRule",
            "UnspawnedProcessRule",
            "SequenceGapRule",
            "ParentChildTemporalRule",
            "ProcessActivityTemporalRule",
            "SequenceMonotonicityRule",
        ],
        "hard_rules": [
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
        ],
        "soft_rules": [
            "DuplicateEventRule",
            "ReadWriteConsistencyRule",
            "SequenceMonotonicityRule",
            "UnspawnedProcessRule",
        ],
    }


def compute_violation_vector(
    graph: ProvenanceGraph,
    engine: Optional[RuleEngine] = None,
) -> Dict[str, np.ndarray]:
    """
    Computes a 15-dimensional binary violation vector v_all(e) for each edge in graph.

    Ordered by canonical_rule_order from config/invariant_partition.json.

    Args:
        graph: Input ProvenanceGraph.
        engine: RuleEngine instance (defaults to default_rule_engine()).

    Returns:
        Dict mapping edge_id -> binary np.ndarray of shape (15,).
    """
    if engine is None:
        engine = default_rule_engine()

    cfg = load_invariant_config()
    canonical_order = cfg["canonical_rule_order"]

    # Run rule engine
    rule_results = engine.run(graph)
    results_by_rule = {rr.rule: rr for rr in rule_results}

    # Map rule -> set of flagged edge_ids
    flagged_by_rule: Dict[str, set[str]] = {}
    for rule_name in canonical_order:
        rr = results_by_rule.get(rule_name)
        if rr is not None:
            flagged = {v.edge_id for v in rr.violations if v.edge_id is not None}
        else:
            flagged = set()
        flagged_by_rule[rule_name] = flagged

    # Construct 15-dim violation vector for every edge
    violation_dict: Dict[str, np.ndarray] = {}
    for edge in graph.edges:
        v = np.zeros(len(canonical_order), dtype=np.float32)
        for i, rule_name in enumerate(canonical_order):
            if edge.edge_id in flagged_by_rule[rule_name]:
                v[i] = 1.0
        violation_dict[edge.edge_id] = v

    return violation_dict


def split_violation_vector(
    v_all: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Splits a 15-dimensional violation vector into v_hard (11 dims) and v_soft (4 dims).

    Args:
        v_all: Binary np.ndarray of shape (15,).

    Returns:
        Tuple of (v_hard, v_soft).
    """
    cfg = load_invariant_config()
    canonical_order = cfg["canonical_rule_order"]
    hard_rules = set(cfg["hard_rules"])
    soft_rules = set(cfg["soft_rules"])

    hard_indices = [i for i, r in enumerate(canonical_order) if r in hard_rules]
    soft_indices = [i for i, r in enumerate(canonical_order) if r in soft_rules]

    v_hard = v_all[hard_indices]
    v_soft = v_all[soft_indices]
    return v_hard, v_soft


def compute_hard_mask(
    graph: ProvenanceGraph,
    engine: Optional[RuleEngine] = None,
) -> Dict[str, float]:
    """
    Computes hard feasibility mask(e) for each edge in graph:
        mask(e) = 1.0 if v_hard(e).any() else 0.0

    Computed as a plain constant dict OUTSIDE any autograd graph.

    Args:
        graph: Input ProvenanceGraph.
        engine: RuleEngine instance.

    Returns:
        Dict mapping edge_id -> float (1.0 or 0.0).
    """
    violations = compute_violation_vector(graph, engine)
    mask_dict: Dict[str, float] = {}

    for eid, v_all in violations.items():
        v_hard, _ = split_violation_vector(v_all)
        mask_dict[eid] = 1.0 if np.any(v_hard > 0) else 0.0

    return mask_dict


class GatedDetector(nn.Module):
    """
    GatedDetector Wrapper enforcing s(e) = mask(e) * f(e).

    The mask is computed OUTSIDE any autograd graph as a plain constant tensor,
    and multiplication is the FINAL operation. No learned parameter appears
    downstream of it.
    """

    def __init__(self, base_model: nn.Module | Any):
        super().__init__()
        self.base_model = base_model

    def forward(
        self,
        scores: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Enforces s(e) = mask(e) * f(e).

        Args:
            scores: Base model anomaly score predictions f(e).
            mask: Binary mask constant tensor with requires_grad=False.

        Returns:
            Gated scores s(e) = mask * scores.
        """
        # Ensure mask is detached and non-differentiable
        mask_const = mask.detach()
        return mask_const * scores

    def score_edges(self, graph: ProvenanceGraph) -> Dict[str, float]:
        """
        Computes gated anomaly scores dict[edge_id, float] for a graph.

        Args:
            graph: ProvenanceGraph instance.

        Returns:
            Dict mapping edge_id -> score float in [0, 1].
        """
        # Step 1: Compute hard binary mask constant OUTSIDE autograd
        mask_dict = compute_hard_mask(graph)

        # Step 2: Compute base model scores f(e)
        if hasattr(self.base_model, "score_edges"):
            f_scores = self.base_model.score_edges(graph)
        elif callable(self.base_model):
            f_scores = self.base_model(graph)
        else:
            raise TypeError("base_model must have score_edges() method or be callable")

        # Step 3: Final multiplication s(e) = mask(e) * f(e)
        gated_scores: Dict[str, float] = {}
        for edge in graph.edges:
            eid = edge.edge_id
            m_val = mask_dict.get(eid, 0.0)
            f_val = f_scores.get(eid, 0.0)
            gated_scores[eid] = float(m_val * f_val)

        return gated_scores


def compute_masked_loss(
    loss_fn: nn.Module | Any,
    predictions: torch.Tensor,
    targets: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    """
    Computes training loss restricted exclusively to unmasked edges (where mask == 1.0).

    Args:
        loss_fn: Loss function (e.g. nn.BCELoss(reduction='none')).
        predictions: Model prediction tensor s(e).
        targets: Ground-truth target tensor y(e).
        mask: Binary mask tensor mask(e).

    Returns:
        Scalar loss tensor computed over unmasked edges.
    """
    mask_bool = (mask > 0.5)
    if not torch.any(mask_bool):
        return torch.tensor(0.0, device=predictions.device, requires_grad=True)

    unmasked_preds = predictions[mask_bool]
    unmasked_targets = targets[mask_bool]

    raw_loss = loss_fn(unmasked_preds, unmasked_targets)
    return torch.mean(raw_loss)
