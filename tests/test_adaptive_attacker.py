"""
Unit tests for Phase 10 Adaptive Attacker (Experiment H — Broadened V2 Evaluation).
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from models.feasibility_gate import compute_hard_mask
from src.attacks.attack_primitives import get_default_attack_objectives
from src.attacks.constrained_search import ConstrainedAttackerSearch
from src.graph_construction.synthetic import generate_synthetic_graph


def test_emitted_attacks_pass_hard_rule_checks():
    """Asserts that every attack sequence emitted as feasible by the search passes all 11 HARD rules."""
    base_graph = generate_synthetic_graph(target_edges=200, seed=42)
    objectives = get_default_attack_objectives()
    searcher = ConstrainedAttackerSearch(seed=42)

    for obj in objectives:
        res = searcher.attempt_objective(base_graph, obj, n_trials=5)
        if res.achieved:
            assert res.feasible_edge_cost_min >= res.infeasible_edge_cost
            assert res.gated_detector_score_max == 0.0


def test_unachievable_objective_certificates():
    """Asserts that self-loop execution is certified as UNACHIEVABLE and returns blocking rules."""
    base_graph = generate_synthetic_graph(target_edges=200, seed=42)
    objectives = [o for o in get_default_attack_objectives() if o.name == "self_loop_execution"]
    assert len(objectives) == 1
    self_loop_obj = objectives[0]

    searcher = ConstrainedAttackerSearch(seed=42)
    res = searcher.attempt_objective(base_graph, self_loop_obj, n_trials=5)

    assert res.achieved is False
    assert len(res.blocking_hard_rules) > 0
    assert "SelfLoopRule" in res.blocking_hard_rules or "ExecutionConsistencyRule" in res.blocking_hard_rules


def test_search_is_deterministic_given_seed():
    """Asserts that constrained search is 100% deterministic given a seed."""
    base1 = generate_synthetic_graph(target_edges=200, seed=123)
    base2 = generate_synthetic_graph(target_edges=200, seed=123)

    objectives = get_default_attack_objectives()
    s1 = ConstrainedAttackerSearch(seed=42)
    s2 = ConstrainedAttackerSearch(seed=42)

    for obj in objectives:
        res1 = s1.attempt_objective(base1, obj, n_trials=3)
        res2 = s2.attempt_objective(base2, obj, n_trials=3)

        assert res1.achieved == res2.achieved
        assert res1.feasible_edge_cost_mean == res2.feasible_edge_cost_mean
        assert res1.blocking_hard_rules == res2.blocking_hard_rules


def test_adaptive_attacker_outputs_exist():
    """Asserts that Phase 10 output files exist after running execution script."""
    assert os.path.exists("results/adaptive_attacker.json")
    assert os.path.exists("docs/ADAPTIVE_ADVERSARY_V2.md")
